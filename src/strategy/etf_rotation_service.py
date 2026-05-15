"""Live, refreshing ETF rotation service.

This wraps the pure ``daily_etf_signal.generate_plan`` pipeline behind a
thread-safe service object that:

1. Caches the most recently produced plan with full provenance.
2. Knows when CN A-share markets are open (per the configured trading
   hours) so callers can ask for a refresh and get a cheap cached answer
   outside trading hours.
3. Applies a *rebalance debounce*: when a refresh produces only tiny
   weight deltas vs. the last accepted plan, the cached plan is left in
   place to avoid suggestion churn.
4. Records every refresh attempt to the audit log so dashboards / oncall
   can reconstruct what the strategy was saying at any past moment.

The service is **read-only with respect to brokers** — it merely keeps
the manual trade plan fresh. Order submission stays in the user's hands.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from scripts import daily_etf_signal
from src.data.etf_price_history import fetch_etf_history
from src.data.etf_rotation import EtfHolding, EtfQuote
from src.strategy.etf_rotation_config_loader import (
    StrategyConfig,
    load_strategy_config,
)

logger = logging.getLogger(__name__)


@dataclass
class CachedPlan:
    """One refresh outcome — plan + metadata about how/when it was built."""

    plan: Dict[str, Any]
    refreshed_at: datetime
    quote_source: str
    debounced: bool = False
    debounce_max_delta: Optional[float] = None
    reasons: List[str] = field(default_factory=list)


@dataclass
class RefreshOutcome:
    """Per-refresh telemetry returned by ``EtfRotationService.refresh()``."""

    refreshed: bool
    cached: CachedPlan
    skipped_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers (trading-hours, weight diff)
# ---------------------------------------------------------------------------


def _parse_hhmm(text: str) -> Tuple[int, int]:
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {text!r}")
    return int(parts[0]), int(parts[1])


def is_within_trading_hours(
    now: datetime,
    sessions: Sequence[Sequence[str]],
    tz_name: str,
) -> bool:
    """Return True when ``now`` (any tz) is inside one of the given sessions.

    ``sessions`` is a list of ``[start, end]`` HH:MM pairs interpreted in
    the named timezone, e.g. ``[["09:30", "11:30"], ["13:00", "15:00"]]``.
    """

    if not sessions:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    if local.weekday() >= 5:  # CN A-shares: Mon-Fri only
        return False
    minutes_now = local.hour * 60 + local.minute
    for session in sessions:
        if len(session) != 2:
            continue
        start_h, start_m = _parse_hhmm(session[0])
        end_h, end_m = _parse_hhmm(session[1])
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start <= minutes_now <= end:
            return True
    return False


def max_weight_delta(prev: Mapping[str, float], curr: Mapping[str, float]) -> float:
    """L-inf distance between two weight maps, treating missing keys as 0."""

    keys = set(prev) | set(curr)
    if not keys:
        return 0.0
    return max(abs(float(curr.get(k, 0.0)) - float(prev.get(k, 0.0))) for k in keys)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


HoldingsLoader = Callable[[], Tuple[List[EtfHolding], bool]]
QuotesFetcher = Callable[[Sequence[str], bool], Tuple[Dict[str, EtfQuote], Dict[str, Any]]]
HistoryFetcher = Callable[..., pd.DataFrame]


class EtfRotationService:
    """Thread-safe live rotation service.

    Construct one instance per application (FastAPI lifespan, CLI daemon,
    background thread) and call ``refresh()`` from the scheduler or
    ``get_cached_plan()`` from request handlers.
    """

    def __init__(
        self,
        *,
        strategy_config: Optional[StrategyConfig] = None,
        holdings_loader: Optional[HoldingsLoader] = None,
        quotes_fetcher: Optional[QuotesFetcher] = None,
        history_fetcher: Optional[HistoryFetcher] = None,
        audit_log_path: Optional[Path] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._strategy_config = strategy_config or load_strategy_config()
        self._holdings_loader = holdings_loader or daily_etf_signal.load_configured_holdings
        self._quotes_fetcher = quotes_fetcher or self._default_quotes_fetcher
        self._history_fetcher = history_fetcher or fetch_etf_history
        self._audit_log_path = audit_log_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: Optional[CachedPlan] = None
        self._lock = threading.Lock()

    @staticmethod
    def _default_quotes_fetcher(
        codes: Sequence[str], use_cache: bool
    ) -> Tuple[Dict[str, EtfQuote], Dict[str, Any]]:
        return daily_etf_signal.fetch_live_quotes(list(codes), use_cache=use_cache)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_cached_plan(self) -> Optional[CachedPlan]:
        """Return the most recent plan (or None if no refresh has happened)."""

        with self._lock:
            return self._cache

    def is_trading_hours(self, now: Optional[datetime] = None) -> bool:
        sessions = self._strategy_config.refresh.get("trading_hours") or []
        tz_name = self._strategy_config.refresh.get("timezone", "Asia/Shanghai")
        return is_within_trading_hours(now or self._clock(), sessions, tz_name)

    def refresh(
        self,
        *,
        use_live_history: bool = True,
        use_live_quotes: bool = True,
        use_cache: bool = True,
        force: bool = False,
    ) -> RefreshOutcome:
        """Re-run the plan; respect trading hours and debounce thresholds.

        ``force=True`` bypasses the trading-hours skip — use when the user
        clicks "refresh now" outside market hours.
        """

        with self._lock:
            now = self._clock()
            if not force and not self.is_trading_hours(now) and self._cache is not None:
                return RefreshOutcome(
                    refreshed=False,
                    cached=self._cache,
                    skipped_reason="outside_trading_hours",
                )

            new_plan, quote_source = self._build_plan(
                use_live_history=use_live_history,
                use_live_quotes=use_live_quotes,
                use_cache=use_cache,
                now=now,
            )

            debounce_delta: Optional[float] = None
            if self._cache is not None and not force:
                threshold = float(
                    self._strategy_config.refresh.get("rebalance_debounce_weight", 0.0)
                )
                debounce_delta = max_weight_delta(
                    self._cache.plan.get("adjusted_weights", {}),
                    new_plan.get("adjusted_weights", {}),
                )
                if debounce_delta <= threshold:
                    self._cache = CachedPlan(
                        plan=self._cache.plan,
                        refreshed_at=now,
                        quote_source=quote_source,
                        debounced=True,
                        debounce_max_delta=debounce_delta,
                        reasons=["rebalance_debounce_active"],
                    )
                    daily_etf_signal.append_audit_entry(
                        new_plan,
                        path=self._audit_log_path,
                        run_at=now,
                        quote_source=f"service:debounced:{quote_source}",
                    )
                    return RefreshOutcome(
                        refreshed=False,
                        cached=self._cache,
                        skipped_reason="below_debounce_threshold",
                    )

            cached = CachedPlan(
                plan=new_plan,
                refreshed_at=now,
                quote_source=quote_source,
                debounced=False,
                debounce_max_delta=debounce_delta,
            )
            self._cache = cached
            daily_etf_signal.append_audit_entry(
                new_plan,
                path=self._audit_log_path,
                run_at=now,
                quote_source=f"service:{quote_source}",
            )
            return RefreshOutcome(refreshed=True, cached=cached)

    def invalidate(self) -> None:
        """Drop the cached plan (next refresh always recomputes)."""

        with self._lock:
            self._cache = None

    def reload_strategy_config(self) -> StrategyConfig:
        """Re-read the strategy.json file. The next refresh will use it."""

        with self._lock:
            self._strategy_config = load_strategy_config()
            return self._strategy_config

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _build_plan(
        self,
        *,
        use_live_history: bool,
        use_live_quotes: bool,
        use_cache: bool,
        now: datetime,
    ) -> Tuple[Dict[str, Any], str]:
        base_holdings, holdings_is_configured = self._holdings_loader()
        codes = [h.code for h in base_holdings]
        live_quotes: Dict[str, EtfQuote] = {}
        if use_live_quotes and codes:
            live_quotes, _status = self._quotes_fetcher(codes, use_cache)

        holdings = (
            daily_etf_signal.apply_quotes_to_holdings(base_holdings, live_quotes)
            if live_quotes
            else base_holdings
        )

        quote_map: Optional[Dict[str, EtfQuote]] = None
        quotes_as_of = None
        if live_quotes:
            quote_map = daily_etf_signal.load_default_quotes(holdings)
            quote_map.update(live_quotes)
            quotes_as_of = max(
                (q.timestamp for q in live_quotes.values() if q.timestamp), default=None
            )

        price_matrix = None
        price_matrix_as_of = None
        if use_live_history and codes:
            fetched = self._history_fetcher(codes)
            if fetched is not None and not fetched.empty:
                price_matrix = fetched
                last_dt = fetched.index.max()
                price_matrix_as_of = (
                    last_dt.isoformat()
                    if isinstance(last_dt, pd.Timestamp)
                    else str(last_dt)
                )

        plan = daily_etf_signal.generate_plan(
            holdings=holdings if holdings_is_configured else None,
            quotes=quote_map,
            price_matrix=price_matrix,
            strategy_config=self._strategy_config,
            quotes_as_of=quotes_as_of,
            price_matrix_as_of=price_matrix_as_of,
            now=now,
        )

        if live_quotes and price_matrix is not None:
            quote_source = "live"
        elif live_quotes:
            quote_source = "live_quotes_synthetic_history"
        elif price_matrix is not None:
            quote_source = "live_history_synthetic_quotes"
        else:
            quote_source = "synthetic"
        plan["quote_source"] = quote_source
        return plan, quote_source


__all__ = [
    "CachedPlan",
    "EtfRotationService",
    "RefreshOutcome",
    "is_within_trading_hours",
    "max_weight_delta",
]
