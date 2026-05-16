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
