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


# ---------------------------------------------------------------------------
# FixedFractionSizer edge cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_fraction", [0.0, -0.1, 1.5])
def test_fixed_fraction_sizer_rejects_invalid_fraction(bad_fraction):
    with pytest.raises(ValueError):
        FixedFractionSizer(fraction=bad_fraction)


def test_fixed_fraction_sizer_returns_empty_result_for_zero_price():
    sizer = FixedFractionSizer(fraction=0.5)
    result = sizer.calculate(make_context(current_price=0.0))

    assert result.method == "fixed_fraction"
    assert result.shares == 0.0
    assert result.position_value == 0.0
    assert result.fraction_of_equity == 0.0


def test_fixed_fraction_sizer_with_zero_equity_yields_zero_fraction():
    sizer = FixedFractionSizer(fraction=0.5)
    result = sizer.calculate(make_context(current_equity=0.0))

    assert result.shares == 0.0
    assert result.fraction_of_equity == 0.0


def test_fixed_fraction_sizer_supports_fractional_shares():
    sizer = FixedFractionSizer(fraction=0.5)
    result = sizer.calculate(make_context(allow_fractional=True))

    assert 49.0 < result.shares < 50.0
    assert result.position_value > 4900.0


def test_fixed_fraction_sizer_scales_with_risk_and_signal():
    sizer = FixedFractionSizer(fraction=0.5)
    full = sizer.calculate(make_context())
    halved_risk = sizer.calculate(make_context(risk_scale_factor=0.5))
    halved_signal = sizer.calculate(make_context(signal_strength=0.5))
    zero_signal = sizer.calculate(make_context(signal_strength=0.0))

    assert halved_risk.shares < full.shares
    assert halved_signal.shares == pytest.approx(halved_risk.shares)
    assert zero_signal.shares == 0.0


def test_fixed_fraction_sizer_min_shares_acts_as_floor():
    sizer = FixedFractionSizer(fraction=0.001)
    result = sizer.calculate(make_context(min_shares=5))

    assert result.shares == 5.0


# ---------------------------------------------------------------------------
# KellyCriterionSizer edge cases
# ---------------------------------------------------------------------------
def test_kelly_sizer_falls_back_when_avg_win_is_zero():
    sizer = KellyCriterionSizer(min_trades_required=5)
    result = sizer.calculate(make_context(recent_avg_win=0.0))

    assert result.method == "kelly_fallback"


def test_kelly_sizer_falls_back_when_avg_loss_is_zero():
    sizer = KellyCriterionSizer(min_trades_required=5)
    result = sizer.calculate(make_context(recent_avg_loss=0.0))

    assert result.method == "kelly_fallback"


def test_kelly_sizer_returns_zero_for_negative_kelly():
    sizer = KellyCriterionSizer(kelly_fraction=0.5, max_position_pct=0.25, min_trades_required=5)
    result = sizer.calculate(
        make_context(
            recent_win_rate=0.3,
            recent_avg_win=0.01,
            recent_avg_loss=-0.02,
        )
    )

    assert result.method == "kelly"
    assert result.shares == 0.0
    assert "0.00%" in result.details or "0%" in result.details


def test_kelly_sizer_handles_zero_price():
    sizer = KellyCriterionSizer(kelly_fraction=0.5, max_position_pct=0.25, min_trades_required=5)
    result = sizer.calculate(make_context(current_price=0.0))

    assert result.method == "kelly"
    assert result.shares == 0.0


# ---------------------------------------------------------------------------
# VolatilityTargetSizer edge cases
# ---------------------------------------------------------------------------
def test_volatility_target_sizer_uses_max_leverage_when_vol_is_zero():
    constant_returns = [0.01] * 25
    sizer = VolatilityTargetSizer(target_vol=0.15, lookback=20, max_leverage=1.5)
    result = sizer.calculate(make_context(recent_returns=constant_returns))

    assert result.method == "vol_target"
    assert 1.45 <= result.fraction_of_equity <= 1.5
    assert "fraction=" in result.details


def test_volatility_target_sizer_handles_zero_price():
    constant_returns = [0.01] * 25
    sizer = VolatilityTargetSizer(target_vol=0.15, lookback=20)
    result = sizer.calculate(make_context(recent_returns=constant_returns, current_price=0.0))

    assert result.method == "vol_target"
    assert result.shares == 0.0


def test_volatility_target_sizer_scales_with_risk_factor():
    returns = [0.01, -0.005, 0.012, -0.004, 0.009, 0.006, -0.003, 0.01, -0.002, 0.008,
               0.004, 0.005, 0.001, -0.001, 0.003, 0.002, -0.001, 0.004, 0.006, 0.003]
    sizer = VolatilityTargetSizer(target_vol=0.15, lookback=20, max_leverage=1.5)
    full = sizer.calculate(make_context(recent_returns=returns))
    scaled = sizer.calculate(make_context(recent_returns=returns, risk_scale_factor=0.5))

    assert scaled.shares < full.shares
    assert scaled.shares > 0


# ---------------------------------------------------------------------------
# EqualRiskSizer edge cases
# ---------------------------------------------------------------------------
def test_equal_risk_sizer_uses_max_position_with_zero_vol():
    constant = [0.001] * 10
    sizer = EqualRiskSizer(lookback=5, max_position_pct=0.5)
    result = sizer.calculate(make_context(recent_returns=constant))

    assert result.method == "equal_risk"
    # When vol is zero, fraction equals max_position_pct, capped after clip
    assert 0.45 <= result.fraction_of_equity <= 0.5


def test_equal_risk_sizer_falls_back_when_history_short():
    sizer = EqualRiskSizer(lookback=20, max_position_pct=0.5)
    result = sizer.calculate(make_context(recent_returns=[0.01]))

    assert result.method == "equal_risk_fallback"
    assert result.shares > 0


def test_equal_risk_sizer_handles_zero_price():
    sizer = EqualRiskSizer(lookback=5)
    result = sizer.calculate(make_context(current_price=0.0))

    assert result.method == "equal_risk"
    assert result.shares == 0.0


# ---------------------------------------------------------------------------
# Factory edge cases
# ---------------------------------------------------------------------------
def test_create_position_sizer_returns_each_registered_class():
    assert isinstance(create_position_sizer("fixed_fraction"), FixedFractionSizer)
    assert isinstance(create_position_sizer("kelly"), KellyCriterionSizer)
    assert isinstance(create_position_sizer("vol_target"), VolatilityTargetSizer)
    assert isinstance(create_position_sizer("equal_risk"), EqualRiskSizer)


def test_create_position_sizer_forwards_kelly_kwargs():
    sizer = create_position_sizer(
        "kelly",
        kelly_fraction=0.25,
        max_position_pct=0.5,
        min_trades_required=15,
    )

    assert isinstance(sizer, KellyCriterionSizer)
    assert sizer.kelly_fraction == 0.25
    assert sizer.max_position_pct == 0.5
    assert sizer.min_trades_required == 15


def test_create_position_sizer_forwards_fixed_fraction_kwarg():
    sizer = create_position_sizer("fixed_fraction", fraction=0.25)

    assert isinstance(sizer, FixedFractionSizer)
    assert sizer.fraction == 0.25
