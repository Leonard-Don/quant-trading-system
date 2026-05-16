"""Loader for the ETF rotation strategy's external configuration.

Everything that used to be hand-edited in Python (asset universe, per-ETF
caps, base weights, risk thresholds, scoring constants, refresh cadence)
now lives in a single JSON file. The loader resolves the active config
path in this order:

1. ``ETF_STRATEGY_CONFIG_PATH`` environment variable.
2. ``~/.config/etf-rotation/strategy.json`` if it exists.
3. The built-in ``DEFAULT_*`` constants in this module (backward compat).

Each layer is **partial**: any field not present in the user's JSON falls
back to the default. So you can override just ``risk_rules.min_cash_weight``
without re-specifying the entire universe.

The loader is *the single source of truth* for everything the rotation
strategy needs. ``daily_etf_signal`` builds its strategy/risk/asset config
from one call to ``load_strategy_config()``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)


CONFIG_PATH_ENV = "ETF_STRATEGY_CONFIG_PATH"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "etf-rotation" / "strategy.json"


# ---------------------------------------------------------------------------
# Defaults (mirror prior in-code constants)
# ---------------------------------------------------------------------------


DEFAULT_UNIVERSE: List[Dict[str, Any]] = [
    {
        "code": "159985", "name": "豆粕ETF华夏", "exchange": "sz",
        "category": "commodity_event",
        "max_weight": 0.08, "base_weight": 0.05,
        "risk_metadata": {
            "bucket": "commodity",
            "tags": ["commodity", "agri"],
        },
    },
    {
        "code": "512400", "name": "有色金属ETF南方", "exchange": "sh",
        "category": "nonferrous",
        "max_weight": 0.25, "base_weight": 0.22,
        "risk_metadata": {
            "bucket": "commodity",
            "tags": ["metals", "commodity"],
        },
    },
    {
        "code": "510300", "name": "沪深300ETF华泰柏瑞", "exchange": "sh",
        "category": "a_share_core",
        "max_weight": 0.35, "base_weight": 0.28,
        "risk_metadata": {"bucket": "domestic_equity"},
    },
    {
        "code": "518680", "name": "金ETF富国", "exchange": "sh",
        "category": "gold_hedge",
        "max_weight": 0.25, "base_weight": 0.20,
        "risk_metadata": {
            "bucket": "commodity",
            "tags": ["gold", "commodity"],
        },
    },
    {
        "code": "513130", "name": "恒生科技ETF华泰柏瑞", "exchange": "sh",
        "category": "hk_tech_satellite",
        "max_weight": 0.12, "base_weight": 0.07,
        "risk_metadata": {"bucket": "qdii", "is_qdii": True},
    },
]


DEFAULT_RISK_RULES: Dict[str, Any] = {
    "max_single_weight": 0.30,
    "commodity_resource_bucket_cap": 0.55,
    "min_cash_weight": 0.10,
    "qdii_premium_veto": 0.02,
    "hard_premium_veto": 0.05,
    "drawdown_cut_threshold": 0.08,
    "drawdown_gross_exposure_multiplier": 0.75,
    "cash_symbol": "CASH",
}


DEFAULT_STRATEGY_PARAMS: Dict[str, Any] = {
    "gross_cap": 0.90,
    "warmup_days": 60,
    "annualized_vol_target": 0.20,
    "enable_vol_targeting": False,
    "min_score_to_hold": 25.0,
    "min_score_full_hold": 35.0,
    "scoring_mode": "absolute",  # "absolute" | "cross_sectional"
    # Per-position protective stop: any holding whose mark-to-market loss
    # vs cost basis is at or below this threshold (negative number) is
    # force-sold to target_weight=0 before risk rules, regardless of
    # what the scoring layer thinks. ``None`` disables. Default -15%
    # because the scoring layer's MA60 trend filter can lag 30+ days
    # and a hard stop is the simplest reliable backstop on real money.
    "stop_loss_threshold": -0.15,
    # Trade-suggestion threshold: only emit a buy/sell action if the
    # target weight differs from the current weight by at least this
    # amount. Backtested on 4 years of CN ETF data — values around
    # 0.15–0.20 deliver materially better Sharpe than the legacy 0.03
    # because they let positions ride through normal volatility instead
    # of churning on every wiggle. Set to 0.0 to emit every drift as a
    # suggestion (high cognitive load, more friction in live trading).
    "rebalance_threshold": 0.20,
}


DEFAULT_REFRESH_PARAMS: Dict[str, Any] = {
    "interval_seconds": 300,
    "trading_hours": [["09:30", "11:30"], ["13:00", "15:00"]],
    "timezone": "Asia/Shanghai",
    "rebalance_debounce_weight": 0.005,
    "enabled": False,  # background loop must be opted into explicitly
}


DEFAULT_REGIME_PARAMS: Dict[str, Any] = {
    "enabled": True,
    "proxy_code": "510300",
    "ma_long_window": 200,
    "vol_window": 60,
    "vol_history_window": 252,
    "drawdown_window": 60,
    "vol_elevated_multiplier": 1.5,
    "vol_crisis_multiplier": 2.0,
    "drawdown_correction": 0.05,
    "drawdown_crisis": 0.15,
    "ma_hysteresis": 0.01,
    "gross_cap_multipliers": {
        "bull": 1.00,
        "correction": 0.85,
        "sideways": 0.90,
        "bear": 0.60,
        "crisis": 0.40,
        "unknown": 1.00,
    },
    "min_score_to_hold_offsets": {
        "bull": 0.0,
        "correction": 0.0,
        "sideways": 0.0,
        "bear": 5.0,
        "crisis": 10.0,
        "unknown": 0.0,
    },
    # Per-regime EtfScoringConfig overrides. Each entry is partial — only
    # the fields you list here override the default scoring; everything
    # else falls back. Empty/missing regime keys use the default scoring.
    #
    # Reasoning:
    # * bear: dial DOWN momentum (trend-following loses edge in bear
    #   markets), dial UP short-term reversal bonus (oversold bounces),
    #   dial UP risk-volatility penalty (defensive)
    # * crisis: nearly mute momentum, max risk aversion
    # * bull/correction/sideways: keep default trend-momentum tilt
    "scoring_overrides": {
        "bear": {
            "momentum_return20_multiplier": 120.0,
            "momentum_return60_multiplier": 60.0,
            "momentum_short_uptrend_bonus": 2.0,
            "short_reversal_bonus": 8.0,
            "risk_volatility_multiplier": 50.0,
        },
        "crisis": {
            "momentum_return20_multiplier": 40.0,
            "momentum_return60_multiplier": 20.0,
            "momentum_short_uptrend_bonus": 0.0,
            "momentum_short_spike_penalty": 20.0,
            "short_reversal_bonus": 6.0,
            "risk_baseline": 25.0,
            "risk_volatility_multiplier": 70.0,
            "risk_volatility_penalty_ceiling": 40.0,
            "trend_above_ma200_points": 6.0,
            "trend_below_ma200_penalty": 16.0,
        },
        "correction": {
            "momentum_short_uptrend_bonus": 3.0,
            "short_reversal_bonus": 6.0,
        },
    },
}


DEFAULT_PREMIUM_PARAMS: Dict[str, Any] = {
    "auto_block_threshold": 0.05,
}


DEFAULT_ENSEMBLE_PARAMS: Dict[str, Any] = {
    "enabled": False,  # off by default so legacy behaviour is preserved
    "regime_blend_weights": {
        "bull": 1.00,
        "correction": 0.60,
        "sideways": 0.50,
        "bear": 0.40,
        "crisis": 1.00,
        "unknown": 1.00,
    },
    "alpha_floor": 0.20,
    "alpha_ceiling": 1.00,
    # Mean-reversion strategy scoring (only consulted when enabled=True)
    "mean_reversion": {
        "require_above_ma200": True,
        "allow_below_long_trend": False,
        "above_ma200_baseline": 30.0,
        "deviation_clip": 0.10,
        "deviation_max_points": 40.0,
        "short_reversal_threshold": -0.04,
        "short_reversal_bonus": 15.0,
        "deep_capitulation_threshold": -0.07,
        "deep_capitulation_bonus": 10.0,
        "risk_baseline": 10.0,
        "risk_volatility_multiplier": 35.0,
        "min_long_return": -0.20,
        "min_score_to_hold": 25.0,
        "min_score_full_hold": 40.0,
    },
}


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyConfig:
    """Resolved (defaults + user overrides) ETF rotation configuration.

    The loader returns one of these and the rest of the codebase consumes
    it. Never mutate; if you need a different shape, construct a new one.
    """

    universe: List[Dict[str, Any]]
    risk_rules: Dict[str, Any]
    strategy: Dict[str, Any]
    scoring: Dict[str, Any]
    refresh: Dict[str, Any]
    regime: Dict[str, Any] = field(default_factory=dict)
    premium: Dict[str, Any] = field(default_factory=dict)
    ensemble: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[Path] = None
    source_mtime: Optional[float] = None

    def asset_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Project the universe into the {symbol: metadata} shape risk rules need."""

        out: Dict[str, Dict[str, Any]] = {}
        for asset in self.universe:
            code = asset.get("code")
            if not code:
                continue
            meta = dict(asset.get("risk_metadata") or {})
            meta.setdefault("category", asset.get("category", ""))
            out[code] = meta
        # Risk rules expect an explicit CASH metadata entry.
        out.setdefault(self.risk_rules.get("cash_symbol", "CASH"), {"category": "cash"})
        return out

    def asset_lookup(self) -> Dict[str, Dict[str, Any]]:
        return {asset["code"]: asset for asset in self.universe if asset.get("code")}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _resolve_config_path(explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(CONFIG_PATH_ENV)
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.is_file():
            return candidate
        logger.warning(
            "%s=%s is set but the file does not exist; using built-in defaults.",
            CONFIG_PATH_ENV, env_value,
        )
        return None
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return None


def _merge_dict(base: Mapping[str, Any], override: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Shallow override for scalar fields, deep for nested dicts."""

    merged = dict(base)
    if not override:
        return merged
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_universe(
    base: List[Dict[str, Any]],
    override: Optional[List[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Override-by-code: any base asset whose code appears in override is
    deep-merged with the override entry; assets present only in override
    are appended; ``override is None`` keeps the base universe unchanged.

    Pass an empty list ``[]`` to wipe the universe — useful for tests.
    """

    if override is None:
        return [dict(asset) for asset in base]

    by_code: Dict[str, Dict[str, Any]] = {
        asset["code"]: dict(asset) for asset in base if asset.get("code")
    }
    ordered_codes: List[str] = [asset["code"] for asset in base if asset.get("code")]

    for entry in override:
        code = entry.get("code")
        if not code:
            logger.warning("Universe override entry missing 'code' field: %s", entry)
            continue
        if code in by_code:
            by_code[code] = _merge_dict(by_code[code], entry)
        else:
            by_code[code] = dict(entry)
            ordered_codes.append(code)

    return [by_code[code] for code in ordered_codes]


def load_strategy_config(
    path: Optional[Path] = None,
    *,
    include_scoring_defaults: bool = True,
) -> StrategyConfig:
    """Resolve and return the active strategy configuration.

    Args:
        path: Explicit config file path; overrides env / default resolution.
        include_scoring_defaults: Pull the ``EtfScoringConfig`` field
            defaults so the returned ``scoring`` dict is complete. Set to
            False if you want only the user-specified overrides (rare).

    Returns a ``StrategyConfig`` whose dicts are guaranteed to contain
    every key the rest of the codebase expects — callers can index without
    .get() defaults.
    """

    # Lazy import to avoid a circular dep with etf_rotation_strategy.
    if include_scoring_defaults:
        from src.strategy.etf_rotation_strategy import EtfScoringConfig
        default_scoring = {
            f.name: getattr(EtfScoringConfig(), f.name)
            for f in EtfScoringConfig.__dataclass_fields__.values()  # type: ignore[attr-defined]
        }
    else:
        default_scoring = {}

    resolved_path = _resolve_config_path(path)
    raw: Dict[str, Any] = {}
    mtime: Optional[float] = None
    if resolved_path is not None:
        try:
            raw = json.loads(resolved_path.read_text(encoding="utf-8"))
            mtime = resolved_path.stat().st_mtime
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "Failed to load strategy config %s (%s); using defaults.",
                resolved_path, exc,
            )
            raw = {}
            resolved_path = None

    # Strip top-level comment keys for ergonomic JSON authoring.
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}

    universe = _merge_universe(DEFAULT_UNIVERSE, raw.get("universe"))
    risk_rules = _merge_dict(DEFAULT_RISK_RULES, raw.get("risk_rules"))
    strategy = _merge_dict(DEFAULT_STRATEGY_PARAMS, raw.get("strategy"))
    scoring = _merge_dict(default_scoring, raw.get("scoring"))
    refresh = _merge_dict(DEFAULT_REFRESH_PARAMS, raw.get("refresh"))
    regime = _merge_dict(DEFAULT_REGIME_PARAMS, raw.get("regime"))
    premium = _merge_dict(DEFAULT_PREMIUM_PARAMS, raw.get("premium"))
    ensemble = _merge_dict(DEFAULT_ENSEMBLE_PARAMS, raw.get("ensemble"))

    return StrategyConfig(
        universe=universe,
        risk_rules=risk_rules,
        strategy=strategy,
        scoring=scoring,
        refresh=refresh,
        regime=regime,
        premium=premium,
        ensemble=ensemble,
        source_path=resolved_path,
        source_mtime=mtime,
    )


__all__ = [
    "CONFIG_PATH_ENV",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_ENSEMBLE_PARAMS",
    "DEFAULT_PREMIUM_PARAMS",
    "DEFAULT_REFRESH_PARAMS",
    "DEFAULT_REGIME_PARAMS",
    "DEFAULT_RISK_RULES",
    "DEFAULT_STRATEGY_PARAMS",
    "DEFAULT_UNIVERSE",
    "StrategyConfig",
    "load_strategy_config",
]
