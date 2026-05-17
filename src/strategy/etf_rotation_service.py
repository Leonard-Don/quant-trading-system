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

from dataclasses import replace as dc_replace

from scripts import daily_etf_signal
from src.data.etf_premium_monitor import EtfPremiumMonitor
from src.data.etf_price_history import fetch_etf_history
from src.data.etf_rotation import EtfHolding, EtfQuote
from src.strategy.etf_mean_reversion_strategy import (
    EtfMeanReversionConfig,
    EtfMeanReversionRotationConfig,
    EtfMeanReversionStrategy,
)
from src.strategy.etf_regime_detector import (
    RegimeDecision,
    build_detector_config,
    classify_regime,
)
from src.strategy.etf_rotation_config_loader import (
    StrategyConfig,
    load_strategy_config,
)
from src.strategy.etf_rotation_strategy import EtfRotationStrategy
from src.strategy.etf_strategy_blend import (
    EtfStrategyBlend,
    EtfStrategyBlendConfig,
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
        premium_monitor: Optional[EtfPremiumMonitor] = None,
        audit_log_path: Optional[Path] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._strategy_config = strategy_config or load_strategy_config()
        self._holdings_loader = holdings_loader or daily_etf_signal.load_configured_holdings
        self._quotes_fetcher = quotes_fetcher or self._default_quotes_fetcher
        self._history_fetcher = history_fetcher or fetch_etf_history
        self._premium_monitor = premium_monitor
        self._audit_log_path = audit_log_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: Optional[CachedPlan] = None
        self._lock = threading.Lock()
        # Last regime label drives the bull/bear hysteresis on the next call.
        self._last_regime: Optional[str] = None
        # Most recent blender (when ensemble is enabled) for post-hoc inspection.
        self._last_blender: Optional[EtfStrategyBlend] = None

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
        enable_policy_signal_factor: Optional[bool] = None,
    ) -> RefreshOutcome:
        """Re-run the plan; respect trading hours and debounce thresholds.

        ``force=True`` bypasses the trading-hours skip — use when the user
        clicks "refresh now" outside market hours.

        ``enable_policy_signal_factor`` overrides the config's
        ``strategy.policy_signal_factor_enabled`` for this single refresh
        (``None`` honours the config). Surfaced so the dashboard "preview
        with policy on" button can flip the factor without persisting it.
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
                enable_policy_signal_factor=enable_policy_signal_factor,
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
        """Re-read the strategy.json file. The next refresh will use it.

        Also propagates the (possibly changed) universe to the premium
        monitor so newly-added ETFs start getting NAV pulls and removed
        ones get evicted from the monitor cache. The next refresh will
        rebuild the plan with the new config — and may flip regime as a
        side-effect since the regime classifier reads from the same file.
        """

        with self._lock:
            self._strategy_config = load_strategy_config()
            if self._premium_monitor is not None:
                codes = [a["code"] for a in self._strategy_config.universe if a.get("code")]
                try:
                    self._premium_monitor.set_codes(codes)
                except Exception as exc:  # noqa: BLE001 — never block reload
                    logger.warning("Premium monitor universe refresh failed: %s", exc)
            return self._strategy_config

    def _build_strategy(
        self,
        *,
        active_strategy_config: StrategyConfig,
        holdings: List[EtfHolding],
        regime_label: str,
        ensemble_meta: Dict[str, Any],
    ):
        """Construct the strategy used for this refresh.

        * Pure trend when ``ensemble.enabled`` is False (legacy behaviour).
        * ``EtfStrategyBlend`` over (trend, mean-reversion) when enabled,
          using the regime label to pick the blend weight.
        """

        trend_strategy = EtfRotationStrategy(
            daily_etf_signal.build_strategy_config(holdings, active_strategy_config)
        )

        ensemble_cfg = active_strategy_config.ensemble or {}
        if not ensemble_cfg.get("enabled", False):
            ensemble_meta.update({"enabled": False})
            return trend_strategy

        # Build the MR strategy. Reuse the asset list / caps from the
        # trend strategy so they're guaranteed in sync.
        mr_raw_scoring = ensemble_cfg.get("mean_reversion") or {}
        mr_scoring_fields = {
            f.name for f in EtfMeanReversionConfig.__dataclass_fields__.values()  # type: ignore[attr-defined]
        }
        mr_scoring_kwargs = {
            k: v for k, v in mr_raw_scoring.items() if k in mr_scoring_fields
        }
        mr_scoring = EtfMeanReversionConfig(**mr_scoring_kwargs)
        mr_rotation_cfg = EtfMeanReversionRotationConfig(
            assets=list(trend_strategy.config.assets),
            gross_cap=float(trend_strategy.config.gross_cap),
            warmup_days=int(trend_strategy.config.warmup_days),
            scoring=mr_scoring,
            min_score_to_hold=float(
                mr_raw_scoring.get("min_score_to_hold", 25.0)
            ),
            min_score_full_hold=float(
                mr_raw_scoring.get("min_score_full_hold", 40.0)
            ),
        )
        mr_strategy = EtfMeanReversionStrategy(mr_rotation_cfg)

        blend_cfg = EtfStrategyBlendConfig(
            enabled=True,
            regime_blend_weights=dict(
                ensemble_cfg.get("regime_blend_weights") or {}
            ),
            alpha_floor=float(ensemble_cfg.get("alpha_floor", 0.20)),
            alpha_ceiling=float(ensemble_cfg.get("alpha_ceiling", 1.00)),
        )
        blender = EtfStrategyBlend(
            trend_strategy=trend_strategy,
            mr_strategy=mr_strategy,
            config=blend_cfg,
            regime=regime_label,
        )

        # Stash a reference so we can read its alpha post-evaluate when
        # surfacing ensemble metadata in the plan output.
        self._last_blender = blender
        ensemble_meta.update({
            "enabled": True,
            "regime": regime_label,
            "alpha_trend": blender.current_alpha(),
            "alpha_mean_reversion": 1.0 - blender.current_alpha(),
            "regime_blend_weights": dict(blend_cfg.regime_blend_weights),
        })
        return blender

    def _classify_regime(self, price_matrix: Optional[pd.DataFrame]) -> Optional[RegimeDecision]:
        """Run the regime classifier on the proxy column of the price matrix.

        Returns ``None`` when regime detection is disabled in strategy.json
        or the proxy code isn't present in the supplied history.
        """

        regime_cfg = self._strategy_config.regime
        if not regime_cfg or not regime_cfg.get("enabled", True):
            return None
        if price_matrix is None or price_matrix.empty:
            return None
        detector_cfg = build_detector_config(regime_cfg)
        if detector_cfg.proxy_code not in price_matrix.columns:
            logger.debug(
                "regime detector: proxy %s not in price matrix columns %s",
                detector_cfg.proxy_code, list(price_matrix.columns),
            )
            return None
        decision = classify_regime(
            price_matrix[detector_cfg.proxy_code],
            config=detector_cfg,
            previous_regime=self._last_regime,
        )
        self._last_regime = decision.regime
        return decision

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
        enable_policy_signal_factor: Optional[bool] = None,
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

        # Premium overlay enrichment: splice NAV onto the live quotes so
        # risk rules see ``quote.premium``, then build EtfOverlay objects
        # so the strategy's scoring layer also sees premium points.
        overlays = None
        if self._premium_monitor is not None and quote_map:
            for code, quote in quote_map.items():
                enrichment = self._premium_monitor.enrichment_for_quote(code)
                if not enrichment:
                    continue
                if quote.estimated_nav is None:
                    quote.estimated_nav = enrichment.get("estimated_nav")
                if quote.prev_nav is None:
                    quote.prev_nav = enrichment.get("prev_nav")
            market_prices = {
                code: quote.current_price for code, quote in quote_map.items()
            }
            premium_cfg = self._strategy_config.premium or {}
            auto_block = premium_cfg.get("auto_block_threshold")
            overlays = self._premium_monitor.build_overlays(
                market_prices,
                auto_block_threshold=(
                    float(auto_block) if auto_block is not None else None
                ),
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

        # Broad-market regime adjustment: classify the proxy index and
        # potentially derate gross_cap + raise min_score_to_hold AND swap
        # in regime-conditional scoring overrides (bear markets get
        # different scoring weights from bull markets).
        active_strategy_config = self._strategy_config
        regime_decision = self._classify_regime(price_matrix)
        regime_scoring_active: Dict[str, Any] = {}
        if regime_decision is not None and regime_decision.regime != "unknown":
            adjusted_strategy_params = dict(active_strategy_config.strategy)
            base_gross_cap = float(adjusted_strategy_params.get("gross_cap", 0.90))
            base_min_score = float(adjusted_strategy_params.get("min_score_to_hold", 25.0))
            adjusted_strategy_params["gross_cap"] = max(
                0.05,
                min(1.0, base_gross_cap * regime_decision.gross_cap_multiplier),
            )
            adjusted_strategy_params["min_score_to_hold"] = (
                base_min_score + regime_decision.min_score_to_hold_offset
            )
            # Keep min_score_full_hold above the new min_score_to_hold.
            base_full_hold = float(adjusted_strategy_params.get("min_score_full_hold", 35.0))
            adjusted_strategy_params["min_score_full_hold"] = max(
                adjusted_strategy_params["min_score_to_hold"] + 1.0,
                base_full_hold + regime_decision.min_score_to_hold_offset,
            )
            # Regime-conditional scoring overrides
            scoring_overrides_map = (
                self._strategy_config.regime.get("scoring_overrides") or {}
            )
            override = scoring_overrides_map.get(regime_decision.regime) or {}
            adjusted_scoring = dict(active_strategy_config.scoring)
            adjusted_scoring.update(override)
            regime_scoring_active = dict(override)

            active_strategy_config = dc_replace(
                active_strategy_config,
                strategy=adjusted_strategy_params,
                scoring=adjusted_scoring,
            )

        if enable_policy_signal_factor is not None:
            adjusted_strategy_params = dict(active_strategy_config.strategy)
            adjusted_strategy_params["policy_signal_factor_enabled"] = bool(
                enable_policy_signal_factor
            )
            active_strategy_config = dc_replace(
                active_strategy_config,
                strategy=adjusted_strategy_params,
            )

        # Build the strategy: pure trend by default, or a blender when the
        # ensemble is enabled in strategy.json. The blender's regime label
        # comes from the same classifier as gross-cap adjustment.
        ensemble_meta: Dict[str, Any] = {"enabled": False}
        strategy_override = self._build_strategy(
            active_strategy_config=active_strategy_config,
            holdings=holdings,
            regime_label=regime_decision.regime if regime_decision else "unknown",
            ensemble_meta=ensemble_meta,
        )

        plan = daily_etf_signal.generate_plan(
            holdings=holdings if holdings_is_configured else None,
            quotes=quote_map,
            overlays=overlays or None,
            price_matrix=price_matrix,
            strategy_config=active_strategy_config,
            strategy_override=strategy_override,
            quotes_as_of=quotes_as_of,
            price_matrix_as_of=price_matrix_as_of,
            now=now,
            enable_policy_signal_factor=enable_policy_signal_factor,
        )

        if regime_decision is not None:
            plan["regime"] = regime_decision.to_dict()
            plan["regime"]["scoring_overrides_applied"] = regime_scoring_active

        plan["ensemble"] = ensemble_meta

        if live_quotes and price_matrix is not None:
            quote_source = "live"
        elif live_quotes:
            quote_source = "live_quotes_synthetic_history"
        elif price_matrix is not None:
            quote_source = "live_history_synthetic_quotes"
        else:
            quote_source = "synthetic"
        plan["quote_source"] = quote_source

        if self._premium_monitor is not None:
            plan["premium_monitor_status"] = self._premium_monitor.status()
        return plan, quote_source


__all__ = [
    "CachedPlan",
    "EtfRotationService",
    "RefreshOutcome",
    "is_within_trading_hours",
    "max_weight_delta",
]
