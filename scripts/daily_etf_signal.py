#!/usr/bin/env python3
"""Daily ETF rotation manual trade plan.

This script combines:

* ``src.strategy.etf_rotation_strategy`` — produces raw target weights from
  a price matrix.
* ``src.risk.etf_portfolio_rules`` — applies portfolio-level guardrails.
* ``src.data.etf_rotation`` — sizes the manual buy/sell/hold suggestions.

It is intentionally **broker-agnostic and non-trading**. The output is a
plan a human reviews and executes manually — no order is submitted, no
broker API is touched.

Holdings provenance
-------------------
``load_default_holdings()`` returns a **fully anonymised five-ETF example
seed** — round share counts, public market prices, ``cost_price ==
current_price`` so no P&L is encoded. Real positions belong outside the
repo: set ``ETF_HOLDINGS_PATH`` (or drop a file at
``~/.config/etf-rotation/holdings.json``) and ``load_configured_holdings``
will pick them up. The CLI and the API endpoint both go through that
helper, so the example seed only fires when nothing else is configured.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_price_history import fetch_etf_history  # noqa: E402
from src.data.etf_rotation import (  # noqa: E402
    DEFAULT_UNIVERSE,
    EtfHolding,
    EtfQuote,
    EtfUniverseItem,
    build_trade_suggestions,
    calculate_current_weights,
)
from src.data.source_health import build_source_registry  # noqa: E402
from src.risk.etf_portfolio_rules import (  # noqa: E402
    EtfRiskRuleConfig,
    apply_etf_portfolio_risk_rules,
)
from src.strategy.etf_rotation_config_loader import (  # noqa: E402
    StrategyConfig,
    load_strategy_config,
)
from src.strategy.etf_rotation_strategy import (  # noqa: E402
    DEFAULT_REBALANCE_THRESHOLD,
    EtfAssetConfig,
    EtfOverlay,
    EtfRotationConfig,
    EtfRotationStrategy,
    EtfScoringConfig,
)

logger = logging.getLogger(__name__)

MANUAL_BANNER = "手动调仓计划：请人工复核后执行；不连接券商接口，也不会自动下单。"

HOLDINGS_PATH_ENV = "ETF_HOLDINGS_PATH"
DEFAULT_HOLDINGS_PATH = Path.home() / ".config" / "etf-rotation" / "holdings.json"

AUDIT_LOG_PATH_ENV = "ETF_AUDIT_LOG_PATH"
DEFAULT_AUDIT_LOG_PATH = Path.home() / ".config" / "etf-rotation" / "audit.jsonl"


# ---------------------------------------------------------------------------
# Example seed + configured-holdings loader
# ---------------------------------------------------------------------------


def load_default_holdings() -> List[EtfHolding]:
    """Return the example five-ETF seed used for tests and documentation.

    Values are intentionally generic (round share counts, ``cost_price ==
    current_price`` so no P&L is encoded). Real positions should be loaded
    via :func:`load_configured_holdings` from a private JSON file.
    """

    return [
        EtfHolding(
            code="159985", name="豆粕ETF华夏", shares=1000,
            cost_price=2.16, current_price=2.16,
        ),
        EtfHolding(
            code="512400", name="有色金属ETF南方", shares=1000,
            cost_price=2.21, current_price=2.21,
        ),
        EtfHolding(
            code="510300", name="沪深300ETF华泰柏瑞", shares=1000,
            cost_price=5.02, current_price=5.02,
        ),
        EtfHolding(
            code="518680", name="金ETF富国", shares=1000,
            cost_price=10.26, current_price=10.26,
        ),
        EtfHolding(
            code="513130", name="恒生科技ETF华泰柏瑞", shares=1000,
            cost_price=0.64, current_price=0.64,
        ),
    ]


def _resolve_holdings_path() -> Optional[Path]:
    """Return the active holdings JSON path or None if no configured file exists.

    Resolution order:
    1. ``ETF_HOLDINGS_PATH`` environment variable, if set.
    2. ``~/.config/etf-rotation/holdings.json`` if present.
    """

    env_path = os.environ.get(HOLDINGS_PATH_ENV)
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return candidate
        logger.warning(
            "ETF_HOLDINGS_PATH=%s is set but the file does not exist; "
            "falling back to the example seed.",
            env_path,
        )

    if DEFAULT_HOLDINGS_PATH.is_file():
        return DEFAULT_HOLDINGS_PATH
    return None


def load_configured_holdings() -> Tuple[List[EtfHolding], bool]:
    """Load holdings from a private config file, falling back to the example.

    Returns a tuple of ``(holdings, is_configured)``. ``is_configured`` is
    True when the holdings came from a real JSON file (the source-health
    registry should then mark them as ``ready`` rather than ``synthetic``).
    """

    path = _resolve_holdings_path()
    if path is None:
        return load_default_holdings(), False
    try:
        return load_holdings_from_json(path), True
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error(
            "Failed to load configured holdings from %s (%s); "
            "falling back to the example seed.",
            path,
            exc,
        )
        return load_default_holdings(), False


def load_default_quotes(holdings: Sequence[EtfHolding]) -> Dict[str, EtfQuote]:
    """Synthesize quotes from holdings when no quote file is supplied."""

    return {
        h.code: EtfQuote(
            code=h.code,
            name=h.name,
            current_price=h.current_price,
            prev_close=h.current_price,
        )
        for h in holdings
    }


def apply_quotes_to_holdings(
    holdings: Sequence[EtfHolding],
    quotes: Mapping[str, EtfQuote],
) -> List[EtfHolding]:
    """Return holdings repriced with any positive live quote prices.

    Share counts and cost basis remain unchanged; only ``current_price`` is
    refreshed so current weights / total asset / trade sizing reflect the
    latest quote snapshot.
    """

    updated: List[EtfHolding] = []
    for holding in holdings:
        quote = quotes.get(holding.code)
        live_price = quote.current_price if quote else None
        current_price = (
            float(live_price)
            if live_price is not None and live_price > 0
            else holding.current_price
        )
        updated.append(
            EtfHolding(
                code=holding.code,
                name=holding.name,
                shares=holding.shares,
                cost_price=holding.cost_price,
                current_price=current_price,
            )
        )
    return updated


def _quotes_to_snapshot(quotes: Mapping[str, EtfQuote]) -> Dict[str, Dict[str, Any]]:
    """Expose quote fields used by dashboards without broker/order data."""

    snapshot: Dict[str, Dict[str, Any]] = {}
    for code, quote in sorted(quotes.items()):
        snapshot[code] = {
            "code": quote.code,
            "name": quote.name,
            "current_price": quote.current_price,
            "prev_close": quote.prev_close,
            "change_pct": quote.change_pct,
            "premium": quote.premium,
            "estimated_nav": quote.estimated_nav,
            "prev_nav": quote.prev_nav,
            "open_price": quote.open_price,
            "high": quote.high,
            "low": quote.low,
            "volume": quote.volume,
            "amount": quote.amount,
            "date": quote.date,
            "time": quote.time,
            "timestamp": quote.timestamp,
            "source": quote.source,
        }
    return snapshot


def _asset_config_from_strategy_config(strategy_config: StrategyConfig) -> Dict[str, Dict[str, Any]]:
    """Project the universe into the legacy ``{code: spec}`` shape."""

    return {
        asset["code"]: {
            "name": asset.get("name", ""),
            "category": asset.get("category", ""),
            "max_weight": float(asset.get("max_weight", 0.30)),
            "base_weight": float(asset.get("base_weight", 0.0)),
        }
        for asset in strategy_config.universe
        if asset.get("code")
    }


# ---------------------------------------------------------------------------
# Live quote helpers (shared by CLI + API endpoint)
# ---------------------------------------------------------------------------


_UNIVERSE_BY_CODE = {item.code: item for item in DEFAULT_UNIVERSE}


def _realtime_symbol_for_code(code: str) -> str:
    """Map a 6-digit code to the realtime_manager's symbol format.

    Uses the DEFAULT_UNIVERSE metadata when available; falls back to the
    standard convention (5/6/11* → SS, otherwise SZ) for unknown codes.
    """

    item = _UNIVERSE_BY_CODE.get(code)
    if item is not None:
        suffix = "SS" if item.exchange == "sh" else "SZ"
        return f"{code}.{suffix}"
    suffix = "SS" if code[:1] in {"5", "6"} or code.startswith("11") else "SZ"
    return f"{code}.{suffix}"


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _iso_timestamp(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _quote_from_realtime_payload(code: str, payload: Mapping[str, Any]) -> Optional[EtfQuote]:
    """Convert a ``realtime_manager.get_quotes_dict`` payload to an ``EtfQuote``.

    Returns ``None`` when the payload lacks a positive price (the trade
    sizing path treats missing prices as "hold").
    """

    price = _float_or_none(payload.get("price"))
    if price is None or price <= 0:
        return None
    item = _UNIVERSE_BY_CODE.get(code)
    name = (
        payload.get("short_name")
        or payload.get("long_name")
        or payload.get("display_name")
        or payload.get("name")
        or (item.name if item else code)
    )
    return EtfQuote(
        code=code,
        name=str(name),
        current_price=price,
        prev_close=_float_or_none(payload.get("previous_close", payload.get("prev_close"))),
        open_price=_float_or_none(payload.get("open")),
        high=_float_or_none(payload.get("high")),
        low=_float_or_none(payload.get("low")),
        volume=_float_or_none(payload.get("volume")),
        amount=_float_or_none(payload.get("amount")),
        timestamp=_iso_timestamp(payload.get("timestamp")),
        source=str(payload.get("source") or "realtime_manager"),
    )


def fetch_live_quotes(
    codes: Sequence[str],
    *,
    use_cache: bool = True,
) -> Tuple[Dict[str, EtfQuote], Dict[str, Any]]:
    """Fetch realtime ETF quotes via the project's ``realtime_manager``.

    Returns ``({code: EtfQuote}, status_dict)``. The status carries
    request/resolved counts, the symbols asked for, and an ``error`` key
    when the underlying provider raises. The CLI and the API endpoint
    both go through this helper so they share quote semantics.
    """

    if not codes:
        return {}, {"requested": 0, "resolved": 0, "missing": 0, "use_cache": use_cache}

    try:
        from src.data.realtime_manager import realtime_manager  # local import: heavy
    except ImportError as exc:
        logger.warning("realtime_manager unavailable: %s", exc)
        return {}, {
            "requested": len(codes),
            "resolved": 0,
            "missing": len(codes),
            "use_cache": use_cache,
            "error": f"realtime_manager_import_failed: {exc}",
        }

    symbol_to_code = {_realtime_symbol_for_code(code): code for code in codes}
    symbols = list(symbol_to_code)

    try:
        payloads = realtime_manager.get_quotes_dict(symbols, use_cache=use_cache)
    except (TimeoutError, ConnectionError, OSError, ValueError, KeyError) as exc:
        logger.warning("ETF live quote fetch failed: %s", exc)
        return {}, {
            "requested": len(symbols),
            "resolved": 0,
            "missing": len(symbols),
            "use_cache": use_cache,
            "error": str(exc),
        }

    quotes: Dict[str, EtfQuote] = {}
    for symbol, code in symbol_to_code.items():
        payload = payloads.get(symbol) or payloads.get(symbol.upper()) or {}
        quote = _quote_from_realtime_payload(code, payload)
        if quote is not None:
            quotes[code] = quote

    return quotes, {
        "requested": len(symbols),
        "resolved": len(quotes),
        "missing": max(len(symbols) - len(quotes), 0),
        "use_cache": use_cache,
        "symbols": symbols,
    }


# ---------------------------------------------------------------------------
# Strategy + risk plumbing
# ---------------------------------------------------------------------------


def build_strategy_config(
    holdings: Sequence[EtfHolding],
    strategy_config: Optional[StrategyConfig] = None,
) -> EtfRotationConfig:
    """Build an ``EtfRotationConfig`` from the loader-resolved configuration.

    ``strategy_config`` is loaded lazily when not supplied, so most callers
    can stay one-arg. Pass an explicit ``StrategyConfig`` to override
    the universe / scoring / strategy params for a single run (tests do
    this).
    """

    cfg = strategy_config if strategy_config is not None else load_strategy_config()
    asset_specs = _asset_config_from_strategy_config(cfg)

    assets: List[EtfAssetConfig] = []
    for holding in holdings:
        spec = asset_specs.get(holding.code, {})
        if not spec:
            logger.warning(
                "ETF rotation: holding %s has no entry in the strategy "
                "universe; using fallback caps (max=0.30, base=0.10). "
                "Add it to %s to fix.",
                holding.code, cfg.source_path or "your strategy.json",
            )
        assets.append(
            EtfAssetConfig(
                symbol=holding.code,
                name=spec.get("name", holding.name),
                category=spec.get("category", ""),
                min_weight=0.0,
                max_weight=float(spec.get("max_weight", 0.30)),
                base_weight=float(spec.get("base_weight", 0.10)),
            )
        )

    scoring_fields = EtfScoringConfig.__dataclass_fields__  # type: ignore[attr-defined]
    scoring = EtfScoringConfig(
        **{k: v for k, v in cfg.scoring.items() if k in scoring_fields}
    )

    strategy_params = cfg.strategy
    return EtfRotationConfig(
        assets=assets,
        gross_cap=float(strategy_params.get("gross_cap", 0.90)),
        warmup_days=int(strategy_params.get("warmup_days", 60)),
        annualized_vol_target=strategy_params.get("annualized_vol_target"),
        min_score_to_hold=float(strategy_params.get("min_score_to_hold", 25.0)),
        min_score_full_hold=float(strategy_params.get("min_score_full_hold", 35.0)),
        enable_vol_targeting=bool(strategy_params.get("enable_vol_targeting", False)),
        scoring=scoring,
        scoring_mode=str(strategy_params.get("scoring_mode", "absolute")),
    )


def build_risk_config(strategy_config: Optional[StrategyConfig] = None) -> EtfRiskRuleConfig:
    """Build an ``EtfRiskRuleConfig`` from the loader-resolved configuration."""

    cfg = strategy_config if strategy_config is not None else load_strategy_config()
    rr = cfg.risk_rules
    return EtfRiskRuleConfig(
        max_single_weight=float(rr.get("max_single_weight", 0.30)),
        commodity_resource_bucket_cap=float(rr.get("commodity_resource_bucket_cap", 0.55)),
        min_cash_weight=float(rr.get("min_cash_weight", 0.10)),
        qdii_premium_veto=float(rr.get("qdii_premium_veto", 0.02)),
        hard_premium_veto=float(rr.get("hard_premium_veto", 0.05)),
        drawdown_cut_threshold=float(rr.get("drawdown_cut_threshold", 0.08)),
        drawdown_gross_exposure_multiplier=float(
            rr.get("drawdown_gross_exposure_multiplier", 0.75)
        ),
        cash_symbol=str(rr.get("cash_symbol", "CASH")),
    )


def synthesize_price_matrix(
    quotes: Mapping[str, EtfQuote],
    *,
    days: int = 120,
    seed: int = 20260513,
    end_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Build a deterministic price history when no live history is supplied.

    Each ETF receives a gentle uptrend from ``current_price * 0.90`` to
    ``current_price`` plus a low-amplitude noise component seeded per code.
    Results stay deterministic for a given ``(seed, end_date)`` pair —
    pass an explicit ``end_date`` in tests for byte-identical output, and
    leave it ``None`` in production so the synthetic history advances with
    the calendar instead of getting stuck at a hardcoded date.
    """

    if days < 60:
        raise ValueError("days must be >= 60 so the 60-day warmup fires")

    if end_date is None:
        end_date = pd.Timestamp.today().normalize()
    dates = pd.bdate_range(end=end_date, periods=days)
    matrix: Dict[str, pd.Series] = {}

    for offset, (code, quote) in enumerate(quotes.items()):
        end_price = quote.current_price or 1.0
        start_price = end_price * 0.90
        baseline = np.linspace(start_price, end_price, days)
        rng = np.random.default_rng(seed + offset)
        noise = rng.normal(0.0, end_price * 0.002, days)
        series = baseline + np.cumsum(noise) * 0.05
        matrix[code] = pd.Series(series, index=dates)

    return pd.DataFrame(matrix)


def _quotes_to_premium_map(quotes: Mapping[str, EtfQuote]) -> Dict[str, float]:
    """Extract premium percentages from quotes where NAV is known."""

    premiums: Dict[str, float] = {}
    for code, quote in quotes.items():
        premium = quote.premium
        if premium is not None:
            premiums[code] = premium
    return premiums


def _apply_position_stop_losses(
    *,
    holdings: Sequence[EtfHolding],
    target_weights: Dict[str, float],
    threshold: Optional[float],
) -> Dict[str, Dict[str, Any]]:
    """Force-sell any holding whose unrealised P&L breaches the stop.

    Mutates ``target_weights`` in place: each triggered code gets its
    target_weight clamped to ``0`` so the suggestion layer emits a
    full-position sell. Returns a per-code report dict for audit/UI.

    The threshold is the *negative* loss bound (e.g. ``-0.15`` for 15%).
    Passing ``None`` or a non-negative value disables the stop entirely.
    """

    if threshold is None:
        return {}
    try:
        bound = float(threshold)
    except (TypeError, ValueError):
        return {}
    if bound >= 0:
        return {}

    triggered: Dict[str, Dict[str, Any]] = {}
    for holding in holdings:
        if holding.cost_price is None or holding.cost_price <= 0:
            continue
        loss = (holding.current_price - holding.cost_price) / holding.cost_price
        if loss > bound + 1e-12:
            continue
        # Forces the position to zero; the cash floor / bucket cap will
        # absorb the freed weight. Below-threshold positions stay zeroed
        # even if the scoring layer wanted to *increase* exposure.
        triggered[holding.code] = {
            "loss_pct": float(loss),
            "threshold": bound,
            "cost_price": float(holding.cost_price),
            "current_price": float(holding.current_price),
            "previous_target_weight": float(target_weights.get(holding.code, 0.0)),
        }
        target_weights[holding.code] = 0.0
    return triggered


_AsOf = Optional[Union[str, datetime]]


def generate_plan(
    holdings: Optional[Sequence[EtfHolding]] = None,
    quotes: Optional[Mapping[str, EtfQuote]] = None,
    *,
    overlays: Optional[Mapping[str, EtfOverlay]] = None,
    price_matrix: Optional[pd.DataFrame] = None,
    risk_config: Optional[EtfRiskRuleConfig] = None,
    strategy_config: Optional[StrategyConfig] = None,
    threshold_weight: float = DEFAULT_REBALANCE_THRESHOLD,
    lot_size: int = 100,
    holdings_as_of: _AsOf = None,
    quotes_as_of: _AsOf = None,
    price_matrix_as_of: _AsOf = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Produce a full manual trade plan for the supplied holdings.

    The ``*_as_of`` parameters communicate the **sample** time of each input,
    distinct from the plan-build time. Pass them when you know the upstream
    snapshot timestamp (broker query time, quote feed tick time, history end
    date) so the source-health registry can report accurate freshness instead
    of stamping every supplied frame with ``datetime.now()``.

    ``strategy_config`` lets callers inject a pre-loaded ``StrategyConfig``
    (avoiding repeated JSON parsing in service / refresh contexts). When
    omitted, the loader resolves the active config from env / default path.
    """

    holdings_supplied = holdings is not None
    quotes_supplied = quotes is not None
    price_matrix_supplied = price_matrix is not None

    holdings = list(holdings) if holdings_supplied else load_default_holdings()
    quote_map = dict(quotes) if quotes_supplied else load_default_quotes(holdings)

    total_asset = sum(h.market_value for h in holdings)
    current_weights = calculate_current_weights(holdings, total_asset)

    active_config = strategy_config if strategy_config is not None else load_strategy_config()
    strategy = EtfRotationStrategy(build_strategy_config(holdings, active_config))
    if price_matrix is None:
        price_matrix = synthesize_price_matrix(quote_map)

    signals = strategy.evaluate(
        price_matrix,
        overlays=dict(overlays) if overlays else None,
        current_weights=current_weights,
    )
    target_weights = {sig.symbol: sig.target_weight for sig in signals}
    # Make sure every held symbol appears in the target map (zero if the
    # strategy refused to score it — keeps the rule engine consistent).
    for holding in holdings:
        target_weights.setdefault(holding.code, 0.0)

    # Per-position protective stop — applied BEFORE risk rules so the
    # freed weight can be redirected to cash by the cash floor / bucket
    # cap pipeline. This is intentionally placed outside the scoring
    # layer because the scoring layer's trend filter (latest < ma60)
    # can lag 30+ days; a hard P&L stop is the simplest reliable
    # backstop on real-money positions.
    stop_loss_triggered = _apply_position_stop_losses(
        holdings=holdings,
        target_weights=target_weights,
        threshold=active_config.strategy.get("stop_loss_threshold"),
    )

    effective_risk_config = risk_config if risk_config is not None else build_risk_config(active_config)
    decision = apply_etf_portfolio_risk_rules(
        proposed_weights=target_weights,
        current_weights=current_weights,
        asset_metadata=active_config.asset_metadata(),
        premium_percentages=_quotes_to_premium_map(quote_map),
        config=effective_risk_config,
    )

    # ``adjusted_weights`` may contain a synthesised CASH entry — exclude
    # it from the ETF-level sizing pass, but keep it in the JSON payload.
    adjusted_for_trades = {
        code: weight
        for code, weight in decision.adjusted_weights.items()
        if code != "CASH"
    }

    suggestions = build_trade_suggestions(
        current_holdings=holdings,
        target_weights=adjusted_for_trades,
        quotes=quote_map,
        total_asset=total_asset,
        lot_size=lot_size,
        threshold_weight=threshold_weight,
    )

    source_health = _build_source_health_payload(
        holdings_supplied=holdings_supplied,
        quotes_supplied=quotes_supplied,
        price_matrix_supplied=price_matrix_supplied,
        holdings_as_of=holdings_as_of,
        quotes_as_of=quotes_as_of,
        price_matrix_as_of=price_matrix_as_of,
        now=now,
    )

    overlay_payload = {
        code: {
            "premium": float(o.premium) if o.premium is not None else None,
            "max_weight": float(o.max_weight) if o.max_weight is not None else None,
            "block_new_buys": bool(o.block_new_buys),
            "reason": o.reason or None,
        }
        for code, o in (overlays or {}).items()
    }

    # Per-ETF signal breakdown — exposed so the audit log can later
    # back-fill forward returns and compute the strategy's Information
    # Coefficient. Captured BEFORE risk rules / stop-loss override so
    # the IC measures the *scoring layer's* edge, not the post-rule
    # output. ``raw_target_weight`` preserves what the scoring layer
    # wanted before stop-loss/risk rules ate into it.
    score_breakdown = {
        sig.symbol: {
            "score": float(sig.score),
            "trend_score": float(sig.trend_score),
            "momentum_score": float(sig.momentum_score),
            "risk_score": float(sig.risk_score),
            "premium_score": float(sig.premium_score),
            "raw_target_weight": float(sig.target_weight),
            "latest_price": float(sig.latest_price),
            "return5": float(sig.return5),
            "return20": float(sig.return20),
            "return60": float(sig.return60),
            "drawdown60": float(sig.drawdown60),
            "volatility60": float(sig.volatility60),
        }
        for sig in signals
    }

    return {
        "manual_only": True,
        "auto_ordering": False,
        "banner": MANUAL_BANNER,
        "total_asset": float(total_asset),
        "current_weights": {k: float(v) for k, v in current_weights.items()},
        "target_weights": {k: float(v) for k, v in target_weights.items()},
        "adjusted_weights": {k: float(v) for k, v in decision.adjusted_weights.items()},
        "suggestions": [
            {
                "code": s.code,
                "name": s.name,
                "action": s.action,
                "shares": int(s.shares),
                "estimated_amount": float(s.estimated_amount),
                "current_weight": float(s.current_weight),
                "target_weight": float(s.target_weight),
                "reason": s.reason,
            }
            for s in suggestions
        ],
        "risk_reasons": list(decision.reasons),
        "source_health": source_health,
        "quote_snapshot": _quotes_to_snapshot(quote_map),
        "overlays": overlay_payload,
        "stop_loss_triggered": stop_loss_triggered,
        "score_breakdown": score_breakdown,
    }


def _build_source_health_payload(
    *,
    holdings_supplied: bool,
    quotes_supplied: bool,
    price_matrix_supplied: bool,
    holdings_as_of: _AsOf = None,
    quotes_as_of: _AsOf = None,
    price_matrix_as_of: _AsOf = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Describe where the ETF rotation inputs came from.

    The plan's three inputs (holdings, quotes, price matrix) can each be
    supplied externally or filled by the deterministic screenshot seed. The
    registry exposes that provenance so dashboards / API consumers can show
    whether they're looking at live data or the fallback synthetic frame.

    Contract for ``as_of``:

    * Supplied data + ``*_as_of`` known → ``status='ready'``, ``as_of`` is
      that timestamp, ``reason`` is empty. Freshness reflects reality.
    * Supplied data + ``*_as_of`` unknown → ``status='ready'``,
      ``as_of=None``, ``reason='sample_timestamp_unknown'``. We don't fake
      freshness from the plan-build clock.
    * Synthetic (no upstream data) → ``status='synthetic'``, ``ok=True``,
      ``as_of=None``, ``fallback=True``, ``reason`` names the substitute
      ("screenshot_seed" / "derived_from_holdings" /
      "deterministic_random_walk").
    """
    reference_now = now or datetime.now(timezone.utc)

    def _spec(
        *,
        source_id: str,
        display_name: str,
        capabilities: Tuple[str, ...],
        supplied: bool,
        sample_as_of: _AsOf,
        synthetic_reason: str,
    ) -> Dict[str, Any]:
        if not supplied:
            return {
                "source_id": source_id,
                "display_name": display_name,
                "status": "synthetic",
                "ok": True,
                "as_of": None,
                "reason": synthetic_reason,
                "capabilities": capabilities,
                "fallback": True,
            }
        if sample_as_of is None:
            return {
                "source_id": source_id,
                "display_name": display_name,
                "status": "ready",
                "ok": True,
                "as_of": None,
                "reason": "sample_timestamp_unknown",
                "capabilities": capabilities,
                "fallback": False,
            }
        return {
            "source_id": source_id,
            "display_name": display_name,
            "status": "ready",
            "ok": True,
            "as_of": sample_as_of,
            "reason": None,
            "capabilities": capabilities,
            "fallback": False,
        }

    specs = [
        _spec(
            source_id="etf_holdings",
            display_name="ETF 持仓快照",
            capabilities=("holdings",),
            supplied=holdings_supplied,
            sample_as_of=holdings_as_of,
            synthetic_reason="screenshot_seed",
        ),
        _spec(
            source_id="etf_quotes",
            display_name="ETF 实时行情",
            capabilities=("latest_quote",),
            supplied=quotes_supplied,
            sample_as_of=quotes_as_of,
            synthetic_reason="derived_from_holdings",
        ),
        _spec(
            source_id="price_matrix",
            display_name="ETF 价格历史",
            capabilities=("historical_data",),
            supplied=price_matrix_supplied,
            sample_as_of=price_matrix_as_of,
            synthetic_reason="deterministic_random_walk",
        ),
    ]
    return [
        entry.to_dict()
        for entry in build_source_registry(
            specs,
            default_required="etf_holdings",
            now=reference_now,
        )
    ]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_output(plan: Mapping[str, Any], *, output: str = "text") -> str:
    """Render the plan as JSON or human-readable text."""

    if output == "json":
        return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    if output == "text":
        return _render_text(plan)
    raise ValueError(f"Unsupported output format: {output!r}")


def _format_trade_reason_zh(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "—"
    labels = {
        "within_threshold": "无需调仓（偏离低于阈值）",
        "missing_quote": "缺少可用行情，暂不操作",
        "below_lot_size": "调整量不足一手，暂不操作",
    }
    if text in labels:
        return labels[text]
    delta_match = re.match(r"^delta_([+-]?\d+(?:\.\d+)?)$", text)
    if delta_match:
        return f"目标偏离 {float(delta_match.group(1)) * 100:.2f}%"
    return text


def _format_risk_reason_zh(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "—"
    labels = {
        "Cash floor target maintained": "现金底线已保留",
        "Manual-only ETF rotation signal": "手动 ETF 轮动信号",
    }
    if text in labels:
        return labels[text]

    patterns = [
        (
            r"^Cash floor: raised cash from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"现金底线：现金仓位从 {m.group(1)} 提高到 {m.group(2)}。",
        ),
        (
            r"^Commodity/resource bucket cap: reduced combined bucket "
            r"from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"商品/资源类仓位上限：合计仓位从 {m.group(1)} 降至 {m.group(2)}。",
        ),
        (
            r"^Single ETF cap for ([^:]+): reduced from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"单只 ETF 上限：{m.group(1)} 从 {m.group(2)} 降至 {m.group(3)}。",
        ),
        (
            r"^Premium veto for ([^:]+): premium ([\d.]+%) "
            r"exceeds ([\d.]+%); target increase capped at current weight\.$",
            lambda m: (
                f"溢价风控：{m.group(1)} 溢价 {m.group(2)} 超过 {m.group(3)}，"
                "目标增仓限制在当前权重。"
            ),
        ),
        (
            r"^Drawdown cut: portfolio drawdown ([\d.]+%) exceeds ([\d.]+%); "
            r"gross ETF exposure reduced from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: (
                f"回撤风控：组合回撤 {m.group(1)} 超过 {m.group(2)}，"
                f"ETF 总敞口从 {m.group(3)} 降至 {m.group(4)}。"
            ),
        ),
    ]
    for pattern, formatter in patterns:
        match = re.match(pattern, text)
        if match:
            return formatter(match)
    return text


_SOURCE_STATUS_LABELS = {
    "ready": "实盘",
    "synthetic": "示例/合成",
    "stale": "过期",
    "missing": "缺失",
    "error": "错误",
}


def _render_source_health_lines(plan: Mapping[str, Any]) -> List[str]:
    entries = plan.get("source_health") or []
    if not entries:
        return []
    lines = ["数据源："]
    for entry in entries:
        name = entry.get("display_name") or entry.get("source_id", "?")
        status = entry.get("status", "?")
        label = _SOURCE_STATUS_LABELS.get(status, status)
        as_of = entry.get("as_of")
        reason = entry.get("reason")
        details: List[str] = []
        if as_of:
            details.append(f"采样时间 {as_of}")
        if reason:
            details.append(reason)
        suffix = f"（{'，'.join(details)}）" if details else ""
        lines.append(f"  {name}：{label}{suffix}")
    return lines


def _render_text(plan: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append(MANUAL_BANNER)
    lines.append("（无自动下单；不调用券商 API。）")
    lines.append("")
    source_lines = _render_source_health_lines(plan)
    if source_lines:
        lines.extend(source_lines)
        lines.append("")
    lines.append(f"组合资产：¥{plan.get('total_asset', 0.0):,.2f}")
    lines.append("")

    lines.append("当前权重：")
    for code, weight in sorted(plan.get("current_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("策略目标权重（风控前）：")
    for code, weight in sorted(plan.get("target_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("风控后目标权重：")
    for code, weight in sorted(plan.get("adjusted_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("手动交易建议：")
    suggestions = plan.get("suggestions") or []
    if not suggestions:
        lines.append("  （暂无）")
    action_labels = {"buy": "买入", "sell": "卖出", "hold": "持有"}
    for suggestion in suggestions:
        action = action_labels.get(str(suggestion["action"]).lower(), str(suggestion["action"]))
        reason = _format_trade_reason_zh(suggestion["reason"])
        lines.append(
            f"  {suggestion['code']:>6} {suggestion['name']:<18} "
            f"{action:<4} {suggestion['shares']:>7} 股  "
            f"≈¥{suggestion['estimated_amount']:>10,.2f}  "
            f"({suggestion['current_weight'] * 100:5.2f}% → "
            f"{suggestion['target_weight'] * 100:5.2f}%)  "
            f"[{reason}]"
        )

    lines.append("")
    lines.append("风控原因：")
    reasons = plan.get("risk_reasons") or []
    if not reasons:
        lines.append("  （未触发组合级风控调整）")
    for reason in reasons:
        lines.append(f"  - {_format_risk_reason_zh(reason)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _resolve_audit_log_path(explicit: Optional[Path] = None) -> Optional[Path]:
    """Return the active audit log path, or None when auditing is disabled.

    Resolution order:
    1. ``explicit`` argument when provided.
    2. ``ETF_AUDIT_LOG_PATH`` env var.
    3. Default location ``~/.config/etf-rotation/audit.jsonl`` if its
       parent directory already exists (we never create the directory
       ourselves — opt-in via env or arg).
    """

    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(AUDIT_LOG_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    if DEFAULT_AUDIT_LOG_PATH.parent.is_dir():
        return DEFAULT_AUDIT_LOG_PATH
    return None


def _audit_entry_from_plan(
    plan: Mapping[str, Any], *, run_at: datetime, quote_source: Optional[str]
) -> Dict[str, Any]:
    """Slim a plan dict into a stable audit row.

    Carries enough per-code state to support forward-return back-fill
    later: ``score_breakdown`` keeps the strategy's scoring view of each
    ETF at the time of the run, and ``prices_at_decision`` captures the
    current_price the strategy "saw". Together these let the analytics
    module compute Information Coefficient and hit rate by looking up
    later audit entries' prices as the realised forward return.
    """

    suggestions = [
        {
            "code": s["code"],
            "action": s["action"],
            "shares": int(s.get("shares", 0)),
            "current_weight": float(s.get("current_weight", 0.0)),
            "target_weight": float(s.get("target_weight", 0.0)),
            "reason": s.get("reason", ""),
        }
        for s in plan.get("suggestions") or []
    ]
    source_health = [
        {
            "source_id": entry.get("source_id"),
            "status": entry.get("status"),
            "as_of": entry.get("as_of"),
            "reason": entry.get("reason"),
        }
        for entry in plan.get("source_health") or []
    ]
    # Per-code price at decision time — pulled from quote_snapshot so it
    # mirrors what the strategy saw rather than re-querying realtime.
    prices_at_decision: Dict[str, float] = {}
    for code, quote_data in (plan.get("quote_snapshot") or {}).items():
        price = quote_data.get("current_price") if isinstance(quote_data, dict) else None
        if price is not None:
            try:
                prices_at_decision[code] = float(price)
            except (TypeError, ValueError):
                continue
    return {
        "run_at": run_at.isoformat(),
        "quote_source": quote_source,
        "total_asset": float(plan.get("total_asset", 0.0)),
        "current_weights": {k: float(v) for k, v in (plan.get("current_weights") or {}).items()},
        "target_weights": {k: float(v) for k, v in (plan.get("target_weights") or {}).items()},
        "adjusted_weights": {
            k: float(v) for k, v in (plan.get("adjusted_weights") or {}).items()
        },
        "suggestions": suggestions,
        "risk_reasons": list(plan.get("risk_reasons") or []),
        "source_health": source_health,
        "score_breakdown": dict(plan.get("score_breakdown") or {}),
        "stop_loss_triggered": dict(plan.get("stop_loss_triggered") or {}),
        "prices_at_decision": prices_at_decision,
    }


def append_audit_entry(
    plan: Mapping[str, Any],
    *,
    path: Optional[Path] = None,
    run_at: Optional[datetime] = None,
    quote_source: Optional[str] = None,
) -> Optional[Path]:
    """Append one JSON-Lines row describing ``plan`` to the audit log.

    Returns the path written, or ``None`` when auditing is disabled (no
    explicit path, no env var, and no pre-existing config directory).
    Failures (IO errors) are logged and swallowed — auditing must never
    abort a manual trade plan.
    """

    target = _resolve_audit_log_path(path)
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = _audit_entry_from_plan(
        plan,
        run_at=run_at or datetime.now(timezone.utc),
        quote_source=quote_source,
    )
    try:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    except OSError as exc:
        logger.warning("Failed to append ETF audit entry to %s: %s", target, exc)
        return None
    return target


def read_audit_log(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return the audit log as a list of dicts (chronological order).

    Returns an empty list when the file does not exist. Bad lines are
    logged and skipped so an old half-written entry can't break a
    reconciliation run.
    """

    target = path or _resolve_audit_log_path()
    if target is None or not Path(target).is_file():
        return []
    entries: List[Dict[str, Any]] = []
    for line_no, line in enumerate(
        Path(target).read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed audit line %d in %s: %s", line_no, target, exc)
    return entries


# ---------------------------------------------------------------------------
# JSON loaders
# ---------------------------------------------------------------------------


def load_holdings_from_json(path: Path) -> List[EtfHolding]:
    """Load holdings from a JSON file produced manually or by upstream tools."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = payload.get("holdings") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise ValueError("holdings JSON must contain a list of holdings")

    holdings: List[EtfHolding] = []
    for item in raw:
        holdings.append(
            EtfHolding(
                code=str(item["code"]),
                name=str(item.get("name", item["code"])),
                shares=int(item.get("shares", 0)),
                cost_price=float(item.get("cost_price", 0.0)),
                current_price=float(item.get("current_price", 0.0)),
            )
        )
    return holdings


def load_quotes_from_json(path: Path) -> Dict[str, EtfQuote]:
    """Load real-time quotes from a JSON file keyed by code."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("quotes JSON must be a {code: quote-object} mapping")

    quotes: Dict[str, EtfQuote] = {}
    for code, item in payload.items():
        quotes[str(code)] = EtfQuote(
            code=str(code),
            name=str(item.get("name", code)),
            current_price=_maybe_float(item.get("current_price")),
            prev_close=_maybe_float(item.get("prev_close")),
            open_price=_maybe_float(item.get("open_price")),
            high=_maybe_float(item.get("high")),
            low=_maybe_float(item.get("low")),
            volume=_maybe_float(item.get("volume")),
            amount=_maybe_float(item.get("amount")),
            estimated_nav=_maybe_float(item.get("estimated_nav")),
            prev_nav=_maybe_float(item.get("prev_nav")),
            source=str(item.get("source")) if item.get("source") else None,
            timestamp=str(item.get("timestamp")) if item.get("timestamp") else None,
        )
    return quotes


def _maybe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class ChineseArgumentParser(argparse.ArgumentParser):
    """Argparse with localized default help chrome for user-facing CLI output."""

    def format_help(self) -> str:
        text = super().format_help()
        replacements = {
            "usage: ": "用法：",
            "options:": "选项：",
            "optional arguments:": "选项：",
            "show this help message and exit": "显示此帮助信息并退出",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def format_usage(self) -> str:
        return super().format_usage().replace("usage: ", "用法：")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(
        description="生成每日 ETF 轮动手动调仓计划；不连接券商接口，只给出人工复核建议。"
    )
    parser.add_argument(
        "--holdings-json",
        type=Path,
        default=None,
        help="可选：当前持仓 JSON 文件；未提供时使用截图种子。",
    )
    parser.add_argument(
        "--quotes-json",
        type=Path,
        default=None,
        help="可选：按代码索引的当前行情 JSON 文件；未提供时使用持仓推导的模拟行情。",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="输出格式：text 打印易读计划；json 输出机器可读载荷。",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=None,
        help=(
            "可选：审计日志路径 (JSON Lines)。优先级高于 ETF_AUDIT_LOG_PATH 环境变量。"
            "传 --audit-log /dev/null 可显式禁用本次写入。"
        ),
    )
    parser.add_argument(
        "--use-live-history",
        action="store_true",
        help=(
            "通过 akshare 拉取 ETF 真实历史价格（默认关闭，使用确定性合成历史）。"
            "拉取失败时自动回退到合成数据并在 source_health 中标记。"
        ),
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=540,
        help="--use-live-history 时获取多少天历史（默认 540，含 60 日 warmup 余量）。",
    )
    quote_group = parser.add_mutually_exclusive_group()
    quote_group.add_argument(
        "--use-live-quotes",
        dest="use_live_quotes",
        action="store_true",
        default=True,
        help="使用 realtime_manager 拉取实时行情刷新现价（默认开启）。",
    )
    quote_group.add_argument(
        "--no-live-quotes",
        dest="use_live_quotes",
        action="store_false",
        help="禁用实时行情；用 holdings.json 里的 current_price 作为现价（脱机/测试用）。",
    )
    parser.add_argument(
        "--quote-cache",
        choices=("on", "off"),
        default="on",
        help="--use-live-quotes 时是否允许实时行情缓存（默认 on；手动强刷传 off）。",
    )
    parser.add_argument(
        "--position-cut",
        type=float,
        default=1.0,
        help=(
            "对策略想要减仓的标的，按 [0, 1] 区间打折执行：1.0 全额按策略目标"
            "（默认）；0.5 只走一半（current + (target - current) * 0.5）。"
            "用于规避策略一刀切清仓时的执行风险，可手动谨慎减仓。"
        ),
    )
    return parser


def _apply_position_cut(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    cut: float,
) -> Dict[str, float]:
    """Soften reductions: target' = current + (target - current) * cut.

    ``cut=1.0`` (default) leaves targets unchanged. ``cut=0.5`` only
    moves half-way from the current weight toward the strategy target,
    so a "clear out" signal becomes a "halve the position" suggestion.
    Buy-side moves are softened too — the helper is symmetric and
    deliberately treats execution risk uniformly across both directions.
    """

    cut = float(np.clip(cut, 0.0, 1.0))
    if cut >= 1.0 - 1e-9:
        return dict(target_weights)
    softened: Dict[str, float] = {}
    keys = set(target_weights) | set(current_weights)
    for code in keys:
        cw = float(current_weights.get(code, 0.0))
        tw = float(target_weights.get(code, 0.0))
        softened[code] = cw + (tw - cw) * cut
    return softened


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # Holdings resolution: explicit --holdings-json wins, then the configured
    # private file ($ETF_HOLDINGS_PATH / ~/.config/etf-rotation/holdings.json),
    # then ``None`` so ``generate_plan`` records the source-health entry as
    # ``synthetic`` and the dashboard surfaces the seed-fallback state.
    holdings: Optional[List[EtfHolding]]
    holdings_as_of: _AsOf
    if args.holdings_json is not None:
        holdings = load_holdings_from_json(args.holdings_json)
        holdings_as_of = datetime.fromtimestamp(
            args.holdings_json.stat().st_mtime, tz=timezone.utc
        ).isoformat()
    else:
        configured, is_configured = load_configured_holdings()
        if is_configured:
            holdings = configured
            path = _resolve_holdings_path()
            holdings_as_of = (
                datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
                if path is not None
                else None
            )
        else:
            holdings = None
            holdings_as_of = None

    # Quotes: explicit --quotes-json wins, then realtime_manager via
    # fetch_live_quotes (default), then ``None`` so generate_plan derives
    # quotes from holdings (offline mode).
    quotes: Optional[Dict[str, EtfQuote]] = None
    quotes_as_of: _AsOf = None
    if args.quotes_json is not None:
        quotes = load_quotes_from_json(args.quotes_json)
        quotes_as_of = datetime.fromtimestamp(
            args.quotes_json.stat().st_mtime, tz=timezone.utc
        ).isoformat()
    elif args.use_live_quotes:
        codes = [h.code for h in (holdings or load_default_holdings())]
        live_quotes, _status = fetch_live_quotes(
            codes, use_cache=(args.quote_cache == "on")
        )
        if live_quotes:
            quotes = live_quotes
            quotes_as_of = max(
                (q.timestamp for q in live_quotes.values() if q.timestamp),
                default=None,
            )
            # Reprice holdings with live quotes so total_asset reflects today.
            if holdings is not None:
                holdings = apply_quotes_to_holdings(holdings, live_quotes)

    price_matrix: Optional[pd.DataFrame] = None
    price_matrix_as_of: _AsOf = None
    if args.use_live_history:
        codes = [h.code for h in (holdings or load_default_holdings())]
        fetched = fetch_etf_history(
            codes,
            start_date=datetime.now() - timedelta(days=args.history_days),
        )
        if fetched.empty:
            logger.warning(
                "Live ETF history fetch returned empty; falling back to "
                "synthetic price matrix for this run."
            )
        else:
            price_matrix = fetched
            last_dt = fetched.index.max()
            price_matrix_as_of = (
                last_dt.isoformat() if isinstance(last_dt, pd.Timestamp) else str(last_dt)
            )

    plan = generate_plan(
        holdings=holdings,
        quotes=quotes,
        price_matrix=price_matrix,
        holdings_as_of=holdings_as_of,
        quotes_as_of=quotes_as_of,
        price_matrix_as_of=price_matrix_as_of,
    )

    if args.position_cut < 1.0:
        plan = _apply_position_cut_to_plan(plan, holdings, quotes, args.position_cut)

    append_audit_entry(plan, path=args.audit_log, quote_source="cli")
    print(format_output(plan, output=args.output))
    return 0


def _apply_position_cut_to_plan(
    plan: Dict[str, Any],
    holdings: Optional[Sequence[EtfHolding]],
    quotes: Optional[Mapping[str, EtfQuote]],
    cut: float,
) -> Dict[str, Any]:
    """Re-emit suggestions from softened target weights without re-running risk rules."""

    if holdings is None or quotes is None:
        # Without concrete holdings/quotes we can't resize orders; tag and skip.
        plan = dict(plan)
        plan["position_cut"] = cut
        plan["position_cut_warning"] = (
            "position_cut requested but holdings or quotes were unavailable; "
            "suggestions reflect the full strategy target."
        )
        return plan

    softened = _apply_position_cut(
        plan.get("current_weights", {}),
        plan.get("adjusted_weights", {}),
        cut,
    )
    # Keep CASH out of the suggestion sizing pass (same convention as generate_plan).
    softened_for_trades = {k: v for k, v in softened.items() if k != "CASH"}
    total_asset = float(plan.get("total_asset", 0.0))
    suggestions = build_trade_suggestions(
        current_holdings=holdings,
        target_weights=softened_for_trades,
        quotes=quotes,
        total_asset=total_asset,
        lot_size=100,
        threshold_weight=DEFAULT_REBALANCE_THRESHOLD,
    )

    updated = dict(plan)
    updated["adjusted_weights"] = {k: float(v) for k, v in softened.items()}
    updated["suggestions"] = [
        {
            "code": s.code,
            "name": s.name,
            "action": s.action,
            "shares": int(s.shares),
            "estimated_amount": float(s.estimated_amount),
            "current_weight": float(s.current_weight),
            "target_weight": float(s.target_weight),
            "reason": s.reason,
        }
        for s in suggestions
    ]
    updated["position_cut"] = cut
    return updated


if __name__ == "__main__":
    raise SystemExit(main())
