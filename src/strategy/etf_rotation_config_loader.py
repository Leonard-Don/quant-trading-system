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
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


CONFIG_PATH_ENV = "ETF_STRATEGY_CONFIG_PATH"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "etf-rotation" / "strategy.json"


# ---------------------------------------------------------------------------
# Defaults (mirror prior in-code constants)
# ---------------------------------------------------------------------------


DEFAULT_UNIVERSE: list[dict[str, Any]] = [
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


DEFAULT_RISK_RULES: dict[str, Any] = {
    "max_single_weight": 0.30,
    "commodity_resource_bucket_cap": 0.55,
    "min_cash_weight": 0.10,
    "qdii_premium_veto": 0.02,
    "hard_premium_veto": 0.05,
    "drawdown_cut_threshold": 0.08,
    "drawdown_gross_exposure_multiplier": 0.75,
    "cash_symbol": "CASH",
}


DEFAULT_STRATEGY_PARAMS: dict[str, Any] = {
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
    # When True, ``stop_loss_threshold`` is detected and surfaced (audit
    # log entry, dashboard badge, ``stop_loss_triggered`` payload) but
    # does NOT zero the target weight. The plan keeps the scoring
    # layer's intended weight. Use this when the system is running as a
    # technical-timing overlay on top of fundamentals-driven long-term
    # holdings — a -15% drawdown becomes "review thesis", not "sell".
    "stop_loss_advisory_only": False,
    # Trade-suggestion threshold: only emit a buy/sell action if the
    # target weight differs from the current weight by at least this
    # amount. Backtested on 4 years of CN ETF data — values around
    # 0.15–0.20 deliver materially better Sharpe than the legacy 0.03
    # because they let positions ride through normal volatility instead
    # of churning on every wiggle. Set to 0.0 to emit every drift as a
    # suggestion (high cognitive load, more friction in live trading).
    "rebalance_threshold": 0.20,
    # ---- policy_signal_factor (opt-in policy_radar integration) ----
    # OFF by default — legacy callers see identical behaviour. When True
    # the ETF rotation tilt each ETF's target weight by its mapped
    # policy_radar industry signal: bullish industries gain
    # ``policy_signal_factor_bullish_boost``; bearish industries lose
    # ``policy_signal_factor_bearish_penalty``. Neutral signals pass
    # through unchanged when ``policy_signal_factor_neutral_pass=True``.
    # The default ±10% knobs are deliberately mild: with defaults the
    # change is at most ±10% per ETF, never zeroing or doubling a
    # position. After the per-ETF tilt the strategy re-normalises so
    # the gross_cap invariant is preserved.
    "policy_signal_factor_enabled": False,
    "policy_signal_factor_bullish_boost": 0.10,
    "policy_signal_factor_bearish_penalty": 0.10,
    "policy_signal_factor_neutral_pass": True,
    "policy_signal_factor_bullish_threshold": 0.10,
}


# Mapping from each ETF code to the policy_radar industry name used by the
# policy_signal_factor opt-in. Keys are 6-digit codes, values match the
# ``industry_signals`` key in ``cache/alt_data/providers/policy_radar.json``
# (or whatever the active policy_radar provider produces). ETFs not in the
# map are left untouched by the factor — adding rows is a non-breaking,
# opt-in operation. Empty by default; populated via ``etf_industry_map`` in
# the strategy.json file or the example config. The default mapping uses
# the broad-industry buckets that exist in policy_radar.json today.
DEFAULT_ETF_INDUSTRY_MAP: dict[str, str] = {
    # 新能源汽车 sleeve (currently no ETF mapped to it in the default
    # universe — the entry is reserved for users who add an EV-themed
    # sleeve via strategy.json).
    # "515030": "新能源汽车",
    # The legacy default universe (159985 / 512400 / 510300 / 518680 /
    # 513130) has no clean 1:1 mapping into policy_radar industries
    # today, so the default map is empty: enabling the factor on the
    # legacy universe is a no-op until the user provides a mapping.
}


DEFAULT_REFRESH_PARAMS: dict[str, Any] = {
    "interval_seconds": 300,
    "trading_hours": [["09:30", "11:30"], ["13:00", "15:00"]],
    "timezone": "Asia/Shanghai",
    "rebalance_debounce_weight": 0.005,
    "enabled": False,  # background loop must be opted into explicitly
}


DEFAULT_REGIME_PARAMS: dict[str, Any] = {
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


DEFAULT_PREMIUM_PARAMS: dict[str, Any] = {
    "auto_block_threshold": 0.05,
}


DEFAULT_ORDER_PRICING_PARAMS: dict[str, Any] = {
    "tick_size": 0.001,
    "aggressive_ticks": 2,
    "neutral_ticks": 1,
    "passive_ticks": 1,
    "default_recommendation": "neutral",
    "batch_breakpoint_shares": 5000,
    "batch_breakpoint_notional": 30000.0,
    "preferred_windows": [
        "10:00-11:00 (上午盘中段，流动性最好)",
        "13:30-14:30 (下午盘中段，避开 14:55+ 收盘冲击)",
    ],
}


DEFAULT_ENSEMBLE_PARAMS: dict[str, Any] = {
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

    ``etf_industry_map`` carries the opt-in mapping from each ETF's 6-digit
    code to the policy_radar industry name used by the policy_signal_factor.
    The map can be partial — codes not listed are simply left untouched
    by the policy nudge (legacy-safe by construction).

    ``manual_overrides`` records the user's per-ETF "I'm holding regardless
    of strategy" thesis lines. Each entry is keyed by 6-digit code and
    contains at minimum a thesis string. When the entry includes
    ``invalidation_price`` (a positive float), the strategy compares
    today's price to it and surfaces an ``invalidated=True`` flag in the
    plan's ``manual_override_status`` payload — the dashboard renders
    that as a red "你的 override 已破" badge so the user knows their
    own line is broken. Pure annotation: never changes weights, scoring,
    or stop-loss behaviour.
    """

    universe: list[dict[str, Any]]
    risk_rules: dict[str, Any]
    strategy: dict[str, Any]
    scoring: dict[str, Any]
    refresh: dict[str, Any]
    regime: dict[str, Any] = field(default_factory=dict)
    premium: dict[str, Any] = field(default_factory=dict)
    ensemble: dict[str, Any] = field(default_factory=dict)
    order_pricing: dict[str, Any] = field(default_factory=dict)
    etf_industry_map: dict[str, str] = field(default_factory=dict)
    manual_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_path: Optional[Path] = None
    source_mtime: Optional[float] = None

    def asset_metadata(self) -> dict[str, dict[str, Any]]:
        """Project the universe into the {symbol: metadata} shape risk rules need."""

        out: dict[str, dict[str, Any]] = {}
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

    def asset_lookup(self) -> dict[str, dict[str, Any]]:
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


def _merge_dict(base: Mapping[str, Any], override: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Shallow override for scalar fields, deep for nested dicts."""

    merged = dict(base)
    if not override:
        return merged
    if not isinstance(override, Mapping):
        logger.warning("Strategy config section override is not a mapping; ignoring: %r", override)
        return merged
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_universe(
    base: list[dict[str, Any]],
    override: Optional[list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Override-by-code: any base asset whose code appears in override is
    deep-merged with the override entry; assets present only in override
    are appended; ``override is None`` keeps the base universe unchanged.

    Pass an empty list ``[]`` to wipe the universe — useful for tests.
    """

    if override is None:
        return [dict(asset) for asset in base]

    by_code: dict[str, dict[str, Any]] = {
        asset["code"]: dict(asset) for asset in base if asset.get("code")
    }
    ordered_codes: list[str] = [asset["code"] for asset in base if asset.get("code")]

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


class StrategyConfigError(ValueError):
    """Raised when a resolved strategy config fails numeric/safety validation.

    A subclass of ``ValueError`` so existing ``except ValueError`` call
    sites keep catching it, while new code can be specific.
    """


# ---------------------------------------------------------------------------
# Validation
#
# The loader deep-merges user JSON over defaults. Without validation a
# typo'd or pasted-wrong value (``max_weight: 3.5``, a negative cash
# floor, a positive ``stop_loss_threshold`` that silently disables the
# protective stop) flows all the way into a real-money plan. We validate
# the *resolved* config here, at the single load chokepoint, and raise a
# specific error naming the offending field and its expected range — fail
# fast at load time, not deep inside the strategy.
# ---------------------------------------------------------------------------


def _require_number(value: Any, field_path: str) -> float:
    """Coerce ``value`` to float or raise a specific ``StrategyConfigError``.

    Booleans are rejected: ``True``/``False`` are technically ``int`` in
    Python but never a valid weight/threshold.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyConfigError(
            f"{field_path} must be a number, got {value!r}"
        )
    number = float(value)
    if number != number:  # NaN guard
        raise StrategyConfigError(f"{field_path} must not be NaN")
    return number


def _require_fraction(
    value: Any,
    field_path: str,
    *,
    low: float = 0.0,
    high: float = 1.0,
    low_inclusive: bool = True,
    high_inclusive: bool = True,
) -> float:
    """Validate ``value`` is a number inside the given fractional bounds."""

    number = _require_number(value, field_path)
    lo_ok = number >= low if low_inclusive else number > low
    hi_ok = number <= high if high_inclusive else number < high
    if not (lo_ok and hi_ok):
        lb = "[" if low_inclusive else "("
        rb = "]" if high_inclusive else ")"
        raise StrategyConfigError(
            f"{field_path} must be a fraction in {lb}{low}, {high}{rb}, "
            f"got {number}"
        )
    return number


def _validate_resolved_config(
    *,
    universe: list[dict[str, Any]],
    risk_rules: dict[str, Any],
    strategy: dict[str, Any],
) -> None:
    """Validate weight/risk/stop-loss/threshold fields of a resolved config.

    Raises :class:`StrategyConfigError` (a ``ValueError``) on the first
    offending field, naming the field and its expected range.
    """

    # --- universe: per-ETF weight fractions ---
    for asset in universe:
        code = asset.get("code", "<no-code>")
        if "max_weight" in asset:
            _require_fraction(asset["max_weight"], f"universe[{code}].max_weight")
        if "base_weight" in asset:
            _require_fraction(asset["base_weight"], f"universe[{code}].base_weight")
        if "min_weight" in asset:
            _require_fraction(asset["min_weight"], f"universe[{code}].min_weight")
        max_w = asset.get("max_weight")
        base_w = asset.get("base_weight")
        if (
            isinstance(max_w, (int, float)) and not isinstance(max_w, bool)
            and isinstance(base_w, (int, float)) and not isinstance(base_w, bool)
            and float(base_w) > float(max_w)
        ):
            raise StrategyConfigError(
                f"universe[{code}].base_weight ({base_w}) must not exceed "
                f"max_weight ({max_w})"
            )

    # --- risk_rules: caps + cash floor + premium vetoes are fractions ---
    for field_name in (
        "max_single_weight",
        "commodity_resource_bucket_cap",
        "min_cash_weight",
        "qdii_premium_veto",
        "hard_premium_veto",
        "drawdown_cut_threshold",
        "drawdown_gross_exposure_multiplier",
    ):
        if field_name in risk_rules:
            _require_fraction(risk_rules[field_name], f"risk_rules.{field_name}")

    # --- strategy: gross cap, score ramp, warmup, stop-loss ---
    if "gross_cap" in strategy:
        _require_fraction(
            strategy["gross_cap"], "strategy.gross_cap",
            low=0.0, low_inclusive=False,
        )

    min_hold = None
    if "min_score_to_hold" in strategy:
        min_hold = _require_number(
            strategy["min_score_to_hold"], "strategy.min_score_to_hold"
        )
        if min_hold < 0.0:
            raise StrategyConfigError(
                f"strategy.min_score_to_hold must be >= 0, got {min_hold}"
            )
    full_hold = None
    if "min_score_full_hold" in strategy:
        full_hold = _require_number(
            strategy["min_score_full_hold"], "strategy.min_score_full_hold"
        )
        if full_hold < 0.0:
            raise StrategyConfigError(
                f"strategy.min_score_full_hold must be >= 0, got {full_hold}"
            )
    if min_hold is not None and full_hold is not None and full_hold < min_hold:
        raise StrategyConfigError(
            f"strategy.min_score_full_hold ({full_hold}) must be >= "
            f"strategy.min_score_to_hold ({min_hold})"
        )

    if "warmup_days" in strategy:
        warmup = strategy["warmup_days"]
        if isinstance(warmup, bool) or not isinstance(warmup, int):
            raise StrategyConfigError(
                f"strategy.warmup_days must be a positive integer, "
                f"got {warmup!r}"
            )
        if warmup <= 0:
            raise StrategyConfigError(
                f"strategy.warmup_days must be a positive integer, got {warmup}"
            )

    if "annualized_vol_target" in strategy:
        vol_target = strategy["annualized_vol_target"]
        if vol_target is not None:
            vt = _require_number(
                vol_target, "strategy.annualized_vol_target"
            )
            if vt <= 0.0:
                raise StrategyConfigError(
                    f"strategy.annualized_vol_target must be > 0 (or null to "
                    f"disable), got {vt}"
                )

    # The protective stop. ``None`` deliberately disables it; ANY numeric
    # value MUST be strictly negative (it is a loss bound). A positive
    # value silently disables the stop on a real-money portfolio — reject.
    if "stop_loss_threshold" in strategy:
        stop = strategy["stop_loss_threshold"]
        if stop is not None:
            stop_num = _require_number(stop, "strategy.stop_loss_threshold")
            if stop_num >= 0.0:
                raise StrategyConfigError(
                    "strategy.stop_loss_threshold must be a negative fraction "
                    "(e.g. -0.15 for a 15% stop) — a non-negative value "
                    "silently disables the protective stop. Use null to "
                    f"disable it intentionally. Got {stop_num}"
                )
            if stop_num < -1.0:
                raise StrategyConfigError(
                    "strategy.stop_loss_threshold must be a fraction in "
                    f"[-1, 0); got {stop_num}"
                )


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
    raw: dict[str, Any] = {}
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
    order_pricing = _merge_dict(DEFAULT_ORDER_PRICING_PARAMS, raw.get("order_pricing"))
    raw_industry_map = raw.get("etf_industry_map") or {}
    if not isinstance(raw_industry_map, Mapping):
        logger.warning(
            "etf_industry_map in strategy config is not a mapping; ignoring.",
        )
        raw_industry_map = {}
    etf_industry_map = {
        **DEFAULT_ETF_INDUSTRY_MAP,
        **{str(k): str(v) for k, v in raw_industry_map.items() if k and v},
    }

    # Numeric/safety validation at the single load chokepoint. Runs on
    # the *resolved* (defaults + overrides) config so a partial user
    # override that pushes a field out of range is still caught. Raises
    # StrategyConfigError (a ValueError) naming the offending field.
    _validate_resolved_config(
        universe=universe,
        risk_rules=risk_rules,
        strategy=strategy,
    )

    raw_manual_overrides = raw.get("manual_overrides") or {}
    if not isinstance(raw_manual_overrides, Mapping):
        logger.warning(
            "manual_overrides in strategy config is not a mapping; ignoring.",
        )
        raw_manual_overrides = {}
    manual_overrides: dict[str, dict[str, Any]] = {}
    for raw_code, entry in raw_manual_overrides.items():
        if not raw_code or not isinstance(entry, Mapping):
            continue
        code = str(raw_code).strip()
        if not code or code.startswith("_"):
            continue
        # Whitelist + coerce known keys. Anything else is silently dropped
        # so a typo in the JSON ("invalidate_price") doesn't pretend to
        # work. The dashboard reads from this normalised view.
        normalised: dict[str, Any] = {}
        invalidation = entry.get("invalidation_price")
        if invalidation is not None:
            try:
                value = float(invalidation)
                if value > 0:
                    normalised["invalidation_price"] = value
            except (TypeError, ValueError):
                logger.warning(
                    "manual_overrides[%s].invalidation_price must be a positive "
                    "number; ignoring %r",
                    code, invalidation,
                )
        thesis = entry.get("thesis")
        if isinstance(thesis, str) and thesis.strip():
            normalised["thesis"] = thesis.strip()
        set_at = entry.get("set_at")
        if isinstance(set_at, str) and set_at.strip():
            normalised["set_at"] = set_at.strip()
        note = entry.get("note")
        if isinstance(note, str) and note.strip():
            normalised["note"] = note.strip()
        if normalised:
            manual_overrides[code] = normalised

    return StrategyConfig(
        universe=universe,
        risk_rules=risk_rules,
        strategy=strategy,
        scoring=scoring,
        refresh=refresh,
        regime=regime,
        premium=premium,
        ensemble=ensemble,
        order_pricing=order_pricing,
        etf_industry_map=etf_industry_map,
        manual_overrides=manual_overrides,
        source_path=resolved_path,
        source_mtime=mtime,
    )


__all__ = [
    "CONFIG_PATH_ENV",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_ENSEMBLE_PARAMS",
    "DEFAULT_ETF_INDUSTRY_MAP",
    "DEFAULT_ORDER_PRICING_PARAMS",
    "DEFAULT_PREMIUM_PARAMS",
    "DEFAULT_REFRESH_PARAMS",
    "DEFAULT_REGIME_PARAMS",
    "DEFAULT_RISK_RULES",
    "DEFAULT_STRATEGY_PARAMS",
    "DEFAULT_UNIVERSE",
    "StrategyConfig",
    "StrategyConfigError",
    "load_strategy_config",
]
