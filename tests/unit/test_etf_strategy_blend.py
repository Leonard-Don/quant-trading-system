"""Tests for the multi-strategy ensemble blender."""

from __future__ import annotations

from typing import List, Mapping, Optional

import numpy as np
import pandas as pd
import pytest

from src.strategy.etf_rotation_strategy import EtfOverlay, EtfSignal
from src.strategy.etf_strategy_blend import (
    DEFAULT_REGIME_BLEND_WEIGHTS,
    EtfStrategyBlend,
    EtfStrategyBlendConfig,
)


class _FakeStrategy:
    """Returns a fixed list of EtfSignals regardless of inputs."""

    def __init__(self, signals: List[EtfSignal]) -> None:
        self._signals = signals
        self.last_call_kwargs = None

    def evaluate(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
    ) -> List[EtfSignal]:
        self.last_call_kwargs = {
            "overlays": overlays,
            "current_weights": current_weights,
        }
        return self._signals


def _sig(symbol: str, score: float, target_weight: float) -> EtfSignal:
    return EtfSignal(
        symbol=symbol,
        latest_price=10.0,
        ma20=10.0,
        ma60=10.0,
        return5=0.0,
        return20=0.0,
        return60=0.0,
        drawdown60=0.0,
        volatility60=0.10,
        trend_score=0.0,
        momentum_score=0.0,
        risk_score=0.0,
        premium_score=0.0,
        score=score,
        raw_weight=target_weight,
        target_weight=target_weight,
        reasons=[],
    )


# ---------------------------------------------------------------------------
# Blend math
# ---------------------------------------------------------------------------


def test_blend_with_alpha_one_returns_trend_weights() -> None:
    trend = _FakeStrategy([_sig("A", 80.0, 0.30), _sig("B", 50.0, 0.20)])
    mr = _FakeStrategy([_sig("A", 40.0, 0.10), _sig("B", 90.0, 0.30)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bull": 1.0},
        ),
        regime="bull",
    )
    out = blender.evaluate(pd.DataFrame())
    by_code = {s.symbol: s for s in out}
    assert by_code["A"].target_weight == pytest.approx(0.30)
    assert by_code["B"].target_weight == pytest.approx(0.20)


def test_blend_with_alpha_zero_returns_mr_weights() -> None:
    trend = _FakeStrategy([_sig("A", 80.0, 0.30)])
    mr = _FakeStrategy([_sig("A", 40.0, 0.10)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"sideways": 0.0},
            alpha_floor=0.0,
        ),
        regime="sideways",
    )
    out = blender.evaluate(pd.DataFrame())
    by_code = {s.symbol: s for s in out}
    assert by_code["A"].target_weight == pytest.approx(0.10)


def test_blend_midpoint_is_linear_combination() -> None:
    trend = _FakeStrategy([_sig("A", 80.0, 0.30)])
    mr = _FakeStrategy([_sig("A", 40.0, 0.10)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"sideways": 0.5},
        ),
        regime="sideways",
    )
    out = blender.evaluate(pd.DataFrame())
    sig = out[0]
    # 0.5 * 0.30 + 0.5 * 0.10 = 0.20
    assert sig.target_weight == pytest.approx(0.20)
    # 0.5 * 80 + 0.5 * 40 = 60
    assert sig.score == pytest.approx(60.0)


def test_blend_handles_codes_present_in_only_one_strategy() -> None:
    trend = _FakeStrategy([_sig("A", 80.0, 0.30)])
    mr = _FakeStrategy([_sig("B", 60.0, 0.25)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(regime_blend_weights={"bull": 0.7}),
        regime="bull",
    )
    out = blender.evaluate(pd.DataFrame())
    by_code = {s.symbol: s for s in out}
    # A is only in trend → blended = 0.7 * 0.30 + 0.3 * 0 = 0.21
    assert by_code["A"].target_weight == pytest.approx(0.21)
    # B is only in MR → blended = 0.7 * 0 + 0.3 * 0.25 = 0.075
    assert by_code["B"].target_weight == pytest.approx(0.075)


# ---------------------------------------------------------------------------
# Alpha clamping
# ---------------------------------------------------------------------------


def test_alpha_clamped_to_floor() -> None:
    trend = _FakeStrategy([])
    mr = _FakeStrategy([])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bear": 0.05},
            alpha_floor=0.20,
        ),
        regime="bear",
    )
    assert blender.current_alpha() == 0.20


def test_alpha_clamped_to_ceiling() -> None:
    trend = _FakeStrategy([])
    mr = _FakeStrategy([])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bull": 1.50},
            alpha_ceiling=1.00,
        ),
        regime="bull",
    )
    assert blender.current_alpha() == 1.00


def test_alpha_uses_unknown_default_when_regime_missing() -> None:
    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"unknown": 0.85, "bull": 1.0},
        ),
        regime="not_in_map",
    )
    assert blender.current_alpha() == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Default regime weights
# ---------------------------------------------------------------------------


def test_default_regime_blend_weights_have_all_regimes() -> None:
    required = {"bull", "correction", "sideways", "bear", "crisis", "unknown"}
    assert set(DEFAULT_REGIME_BLEND_WEIGHTS) >= required


def test_set_regime_updates_alpha() -> None:
    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bull": 1.0, "bear": 0.4},
        ),
        regime="bull",
    )
    assert blender.current_alpha() == 1.0
    blender.set_regime("bear")
    assert blender.current_alpha() == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Reasons trail
# ---------------------------------------------------------------------------


def test_blend_reason_trail_records_regime_and_components() -> None:
    trend = _FakeStrategy([_sig("A", 80.0, 0.30)])
    mr = _FakeStrategy([_sig("A", 40.0, 0.10)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(regime_blend_weights={"sideways": 0.5}),
        regime="sideways",
    )
    sig = blender.evaluate(pd.DataFrame())[0]
    blend_reasons = [r for r in sig.reasons if r.startswith("blend:")]
    assert blend_reasons
    assert "regime=sideways" in blend_reasons[0]


def test_build_component_breakdown_aggregates_per_strategy() -> None:
    breakdown = EtfStrategyBlend.build_component_breakdown(
        trend_signals=[_sig("A", 80.0, 0.30)],
        mr_signals=[_sig("A", 40.0, 0.10), _sig("B", 60.0, 0.15)],
        alpha=0.6,
    )
    assert breakdown["A"]["trend"]["contribution"] == pytest.approx(0.18)
    assert breakdown["A"]["mr"]["contribution"] == pytest.approx(0.04)
    assert breakdown["B"]["mr"]["contribution"] == pytest.approx(0.06)


# ---------------------------------------------------------------------------
# Forwarding of overlays + current_weights
# ---------------------------------------------------------------------------


def test_blend_forwards_overlays_and_current_weights_to_children() -> None:
    trend = _FakeStrategy([])
    mr = _FakeStrategy([])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(regime_blend_weights={"bull": 0.6}),
        regime="bull",
    )
    overlays = {"A": EtfOverlay(premium=0.03)}
    current_weights = {"A": 0.10}
    blender.evaluate(pd.DataFrame(), overlays=overlays, current_weights=current_weights)
    assert trend.last_call_kwargs["overlays"] == overlays
    assert trend.last_call_kwargs["current_weights"] == current_weights
    assert mr.last_call_kwargs["overlays"] == overlays
    assert mr.last_call_kwargs["current_weights"] == current_weights


# ---------------------------------------------------------------------------
# Construction / config defaults
# ---------------------------------------------------------------------------


def test_blend_construction_with_no_config_uses_defaults() -> None:
    """When no config is supplied, the blender must pick up the
    ``EtfStrategyBlendConfig()`` defaults — including the full regime map.

    Why: live callers in ``daily_etf_signal`` rely on construction with
    only ``trend_strategy`` and ``mr_strategy``.
    """

    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
    )
    # Default regime is "unknown" → alpha pulled from default map
    assert blender.current_alpha() == pytest.approx(
        DEFAULT_REGIME_BLEND_WEIGHTS["unknown"]
    )


def test_blend_construction_default_regime_is_unknown() -> None:
    """The blender's default regime label is 'unknown' until ``set_regime``."""

    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"unknown": 0.95, "bull": 1.0},
        ),
    )
    # No explicit regime kwarg → falls through to "unknown" key
    assert blender.current_alpha() == pytest.approx(0.95)


@pytest.mark.parametrize(
    "regime,expected",
    [
        ("bull", 1.00),
        ("correction", 0.60),
        ("sideways", 0.50),
        ("bear", 0.40),
        ("crisis", 1.00),
        ("unknown", 1.00),
    ],
)
def test_default_regime_blend_weights_match_documented_defaults(
    regime: str, expected: float,
) -> None:
    """Pin the documented defaults so we don't silently drift the
    contract that ``EtfRegimeDetector`` callers depend on.

    Why: this strategy lives behind a feature-flag (``enabled=False``)
    and is mostly read from inside ``daily_etf_signal``; documented
    defaults are the contract.
    """

    assert DEFAULT_REGIME_BLEND_WEIGHTS[regime] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_blend_with_two_empty_strategies_returns_empty_list() -> None:
    """Two empty child strategies must give an empty blended output
    (no codes to walk), not crash."""

    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
        config=EtfStrategyBlendConfig(regime_blend_weights={"bull": 0.7}),
        regime="bull",
    )
    out = blender.evaluate(pd.DataFrame())
    assert out == []


def test_blend_with_only_trend_strategy_emitting() -> None:
    """If only the trend strategy emits signals, they're scaled by alpha
    and the MR contribution is zero. Acts as a one-sided smoke test."""

    trend = _FakeStrategy([_sig("A", 80.0, 0.40)])
    mr = _FakeStrategy([])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(regime_blend_weights={"bull": 0.75}),
        regime="bull",
    )
    out = blender.evaluate(pd.DataFrame())
    assert len(out) == 1
    # 0.75 * 0.40 + 0.25 * 0 = 0.30
    assert out[0].target_weight == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Regime switching
# ---------------------------------------------------------------------------


def test_set_regime_walks_through_full_default_map_without_crash() -> None:
    """Sequentially walking every documented regime must give a finite
    alpha each time — guards against typos in the default map.
    """

    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
    )
    for regime in DEFAULT_REGIME_BLEND_WEIGHTS:
        blender.set_regime(regime)
        alpha = blender.current_alpha()
        assert 0.0 <= alpha <= 1.0


def test_alpha_uses_floor_when_unknown_falls_below_it() -> None:
    """When the regime is missing *and* ``unknown`` is below the floor,
    the floor still wins. Belt-and-braces against bad config drift."""

    blender = EtfStrategyBlend(
        trend_strategy=_FakeStrategy([]),
        mr_strategy=_FakeStrategy([]),
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"unknown": 0.05},
            alpha_floor=0.25,
            alpha_ceiling=1.0,
        ),
        regime="not_in_map",
    )
    assert blender.current_alpha() == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Boundary: blend at exactly alpha_floor and alpha_ceiling
# ---------------------------------------------------------------------------


def test_blend_at_alpha_floor_uses_floor_weighting() -> None:
    """When raw α from the regime map is clamped to the floor, the
    blended weights reflect the floor, not the raw α."""

    trend = _FakeStrategy([_sig("A", 80.0, 0.40)])
    mr = _FakeStrategy([_sig("A", 20.0, 0.10)])
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bear": 0.0},
            alpha_floor=0.30,
        ),
        regime="bear",
    )
    out = blender.evaluate(pd.DataFrame())
    # α = 0.30 (clamped). 0.30 * 0.40 + 0.70 * 0.10 = 0.19
    assert out[0].target_weight == pytest.approx(0.19)


# ---------------------------------------------------------------------------
# Integration smoke: real strategies through the blender
# ---------------------------------------------------------------------------


def _build_synthetic_universe(periods: int = 220) -> pd.DataFrame:
    """Two-asset matrix — one trending strongly up, one with a recent dip
    on a long uptrend (good for MR). Lets a real blend show both bodies
    of the strategy contributing.
    """

    dates = pd.date_range("2024-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed=123)
    # Strong steady trend
    strong = 100.0 * np.exp(
        np.linspace(0.0, 0.45, periods) + np.cumsum(rng.normal(0.0, 0.003, periods))
    )
    # Uptrend that takes a 6% haircut on the last 5 bars
    drift_dip = 100.0 * np.exp(
        np.linspace(0.0, 0.30, periods - 5) + np.cumsum(rng.normal(0.0, 0.003, periods - 5))
    )
    dipped = np.concatenate([drift_dip, drift_dip[-1] * np.linspace(1.0, 0.94, 5)])
    return pd.DataFrame({"STRONG": strong, "DIPPED": dipped}, index=dates)


def test_blend_with_real_strategies_produces_signals() -> None:
    """Smoke test: wire a real ``EtfRotationStrategy`` + real
    ``EtfMeanReversionStrategy`` into the blender and confirm it emits
    signals that respect the gross cap on a synthetic universe.

    Why: the unit tests use ``_FakeStrategy`` shims that bypass the real
    interface contract. This pins the integration so a future change in
    either strategy's ``evaluate`` signature is caught here.
    """

    from src.strategy.etf_mean_reversion_strategy import (
        EtfMeanReversionRotationConfig,
        EtfMeanReversionStrategy,
    )
    from src.strategy.etf_rotation_strategy import (
        EtfAssetConfig as TrendAsset,
        EtfRotationConfig,
        EtfRotationStrategy,
    )

    universe = _build_synthetic_universe(periods=220)
    trend_cfg = EtfRotationConfig(
        assets=[
            TrendAsset(symbol="STRONG", max_weight=0.50),
            TrendAsset(symbol="DIPPED", max_weight=0.50),
        ],
        gross_cap=0.80,
    )
    mr_cfg = EtfMeanReversionRotationConfig(
        assets=[
            TrendAsset(symbol="STRONG", max_weight=0.50),
            TrendAsset(symbol="DIPPED", max_weight=0.50),
        ],
        gross_cap=0.80,
    )
    blender = EtfStrategyBlend(
        trend_strategy=EtfRotationStrategy(trend_cfg),
        mr_strategy=EtfMeanReversionStrategy(mr_cfg),
        config=EtfStrategyBlendConfig(regime_blend_weights={"sideways": 0.5}),
        regime="sideways",
    )
    signals = blender.evaluate(universe)
    by_code = {s.symbol: s for s in signals}
    # Both symbols make it through.
    assert set(by_code) == {"STRONG", "DIPPED"}
    # Strong should still dominate — its trend score is high in both
    # strategies. (Mean-reversion may favour DIPPED, but trend at 0.5
    # offsets it.)
    assert by_code["STRONG"].target_weight > 0.0
    # All weights non-negative, sum within reasonable bound.
    assert all(s.target_weight >= 0.0 for s in signals)
    assert sum(s.target_weight for s in signals) <= 0.80 + 1e-6


def test_blend_pure_trend_alpha_matches_pure_trend_strategy_output() -> None:
    """With α = 1.0 the blender must reproduce the trend strategy's
    target weight for each symbol on a real universe.

    Why: regression-guard against the blend math drifting away from
    the contract that "trend at α=1.0 ≡ pure trend strategy".
    """

    from src.strategy.etf_mean_reversion_strategy import (
        EtfMeanReversionRotationConfig,
        EtfMeanReversionStrategy,
    )
    from src.strategy.etf_rotation_strategy import (
        EtfAssetConfig as TrendAsset,
        EtfRotationConfig,
        EtfRotationStrategy,
    )

    universe = _build_synthetic_universe(periods=220)
    trend_cfg = EtfRotationConfig(
        assets=[TrendAsset(symbol="STRONG", max_weight=0.50)],
        gross_cap=0.80,
    )
    mr_cfg = EtfMeanReversionRotationConfig(
        assets=[TrendAsset(symbol="STRONG", max_weight=0.50)],
        gross_cap=0.80,
    )
    trend = EtfRotationStrategy(trend_cfg)
    mr = EtfMeanReversionStrategy(mr_cfg)
    blender = EtfStrategyBlend(
        trend_strategy=trend, mr_strategy=mr,
        config=EtfStrategyBlendConfig(
            regime_blend_weights={"bull": 1.0},
        ),
        regime="bull",
    )

    pure_trend = {s.symbol: s.target_weight for s in trend.evaluate(universe[["STRONG"]])}
    blended = {s.symbol: s.target_weight for s in blender.evaluate(universe[["STRONG"]])}
    assert blended["STRONG"] == pytest.approx(pure_trend["STRONG"])


def test_blend_target_weights_feed_portfolio_risk_rules() -> None:
    """End-to-end smoke: blended output is shape-compatible with
    ``apply_etf_portfolio_risk_rules`` — the same handoff the live
    pipeline performs after the strategy emits its plan.

    Why: closes the integration loop the original commit left open.
    """

    from src.risk.etf_portfolio_rules import apply_etf_portfolio_risk_rules
    from src.strategy.etf_mean_reversion_strategy import (
        EtfMeanReversionRotationConfig,
        EtfMeanReversionStrategy,
    )
    from src.strategy.etf_rotation_strategy import (
        EtfAssetConfig as TrendAsset,
        EtfRotationConfig,
        EtfRotationStrategy,
    )

    universe = _build_synthetic_universe(periods=220)
    trend_cfg = EtfRotationConfig(
        assets=[
            TrendAsset(symbol="STRONG", max_weight=0.50),
            TrendAsset(symbol="DIPPED", max_weight=0.50),
        ],
        gross_cap=0.80,
    )
    mr_cfg = EtfMeanReversionRotationConfig(
        assets=[
            TrendAsset(symbol="STRONG", max_weight=0.50),
            TrendAsset(symbol="DIPPED", max_weight=0.50),
        ],
        gross_cap=0.80,
    )
    blender = EtfStrategyBlend(
        trend_strategy=EtfRotationStrategy(trend_cfg),
        mr_strategy=EtfMeanReversionStrategy(mr_cfg),
        config=EtfStrategyBlendConfig(regime_blend_weights={"sideways": 0.5}),
        regime="sideways",
    )
    signals = blender.evaluate(universe)
    proposed = {s.symbol: s.target_weight for s in signals}

    decision = apply_etf_portfolio_risk_rules(
        proposed_weights=proposed,
        asset_metadata={
            "STRONG": {"category": "domestic_equity"},
            "DIPPED": {"category": "domestic_equity"},
        },
    )
    # Single-name cap respected
    for symbol in ("STRONG", "DIPPED"):
        assert decision.adjusted_weights.get(symbol, 0.0) <= 0.30 + 1e-9
    # Cash floor injected
    assert decision.adjusted_weights.get("CASH", 0.0) >= 0.10 - 1e-9
