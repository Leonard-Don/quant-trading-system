import pytest

from src.backtest.position_sizer import (
    EqualRiskSizer,
    FixedFractionSizer,
    KellyCriterionSizer,
    SizingContext,
    VolatilityTargetSizer,
    create_position_sizer,
)


def make_context(**overrides):
    context = SizingContext(
        current_equity=10_000.0,
        current_price=100.0,
        signal_strength=1.0,
        recent_returns=[0.01, -0.005, 0.012, -0.004, 0.009, 0.006, -0.003, 0.01, -0.002, 0.008],
        recent_win_rate=0.6,
        recent_avg_win=0.03,
        recent_avg_loss=-0.015,
        risk_scale_factor=1.0,
        commission=0.001,
        slippage=0.001,
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


def test_fixed_fraction_sizer_allocates_expected_shares():
    sizer = FixedFractionSizer(fraction=0.5)
    result = sizer.calculate(make_context())

    assert result.method == "fixed_fraction"
    assert result.shares == 49.0
    assert result.position_value == pytest.approx(4900.0)


def test_kelly_sizer_falls_back_when_trade_history_is_short():
    sizer = KellyCriterionSizer(min_trades_required=20)
    result = sizer.calculate(make_context())

    assert result.method == "kelly_fallback"
    assert "insufficient history" in result.details


def test_kelly_sizer_returns_capped_positive_allocation_with_history():
    sizer = KellyCriterionSizer(kelly_fraction=0.5, max_position_pct=0.25, min_trades_required=5)
    result = sizer.calculate(make_context())

    assert result.method == "kelly"
    assert 0 < result.fraction_of_equity <= 0.25
    assert result.shares > 0


def test_volatility_target_sizer_falls_back_without_enough_returns():
    sizer = VolatilityTargetSizer(lookback=20)
    result = sizer.calculate(make_context(recent_returns=[0.01, -0.02]))

    assert result.method == "vol_target_fallback"


def test_equal_risk_sizer_returns_valid_position():
    sizer = EqualRiskSizer(lookback=5, max_position_pct=0.4)
    result = sizer.calculate(make_context())

    assert result.method == "equal_risk"
    assert 0 < result.fraction_of_equity <= 0.4
    assert result.shares > 0


def test_position_sizer_factory_creates_expected_implementation():
    sizer = create_position_sizer("vol_target", target_vol=0.12, lookback=5)

    assert isinstance(sizer, VolatilityTargetSizer)


def test_position_sizer_factory_rejects_unknown_method():
    with pytest.raises(ValueError):
        create_position_sizer("unknown")
