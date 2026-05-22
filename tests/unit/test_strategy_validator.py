"""
Unit tests for src.strategy.strategy_validator module.

Each test exercises a specific validation path with explicit expected values so
the suite acts as a real regression net for the pre-deployment parameter gate.
"""

from typing import ClassVar

import pytest

from src.strategy.strategy_validator import ParameterRule, StrategyValidator

# ---------------------------------------------------------------------------
# ParameterRule.validate — low-level rule object
# ---------------------------------------------------------------------------


class TestParameterRuleValidate:
    """Direct tests for ParameterRule.validate independent of StrategyValidator."""

    def test_valid_int_value(self):
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate(14)
        assert ok is True
        assert msg is None

    def test_valid_float_value(self):
        rule = ParameterRule(name="num_std", type=float, default=2.0, min_value=1.0, max_value=3.0)
        ok, msg = rule.validate(2.0)
        assert ok is True
        assert msg is None

    def test_type_coercion_str_to_int(self):
        """A string that represents a valid int should coerce cleanly."""
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate("20")
        assert ok is True
        assert msg is None

    def test_type_coercion_int_to_float(self):
        """An int passed where float is required is coercible; must pass."""
        rule = ParameterRule(name="num_std", type=float, default=2.0, min_value=1.0, max_value=3.0)
        ok, msg = rule.validate(2)
        assert ok is True
        assert msg is None

    def test_invalid_type_unconvertible(self):
        """A value that cannot be cast to the target type must fail with a message."""
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate("not-a-number")
        assert ok is False
        assert msg is not None
        assert "period" in msg

    def test_below_minimum(self):
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate(4)
        assert ok is False
        assert msg is not None
        assert "5" in msg  # min boundary mentioned in message

    def test_above_maximum(self):
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate(51)
        assert ok is False
        assert msg is not None
        assert "50" in msg  # max boundary mentioned in message

    def test_at_minimum_boundary(self):
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate(5)
        assert ok is True
        assert msg is None

    def test_at_maximum_boundary(self):
        rule = ParameterRule(name="period", type=int, default=14, min_value=5, max_value=50)
        ok, msg = rule.validate(50)
        assert ok is True
        assert msg is None

    def test_no_bounds_allows_any_numeric(self):
        rule = ParameterRule(name="free_param", type=float, default=1.0)
        ok, msg = rule.validate(-999.9)
        assert ok is True
        assert msg is None


# ---------------------------------------------------------------------------
# validate_strategy_params — return-value structure
# ---------------------------------------------------------------------------


class TestValidateStrategyParamsReturnShape:
    """The method always returns (bool, str|None, dict)."""

    def test_returns_three_tuple_on_success(self):
        ok, _err, cleaned = StrategyValidator.validate_strategy_params(
            "rsi", {"period": 14, "oversold": 30, "overbought": 70}
        )
        assert isinstance(ok, bool)
        assert isinstance(cleaned, dict)

    def test_returns_three_tuple_on_failure(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            "rsi", {"period": 999, "oversold": 30, "overbought": 70}
        )
        assert isinstance(ok, bool)
        assert isinstance(err, str)
        assert isinstance(cleaned, dict)


# ---------------------------------------------------------------------------
# Unknown / unsupported strategy names
# ---------------------------------------------------------------------------


class TestUnknownStrategy:
    def test_unknown_strategy_rejected(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            "totally_unknown_strat", {"foo": 1}
        )
        assert ok is False
        assert err is not None
        assert cleaned == {}

    def test_error_message_names_the_strategy(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params("ghost_strategy", {})
        assert ok is False
        assert "ghost_strategy" in _err

    def test_empty_strategy_name_rejected(self):
        ok, _err, cleaned = StrategyValidator.validate_strategy_params("", {})
        assert ok is False
        assert cleaned == {}


# ---------------------------------------------------------------------------
# buy_and_hold — special-cased no-parameter strategy
# ---------------------------------------------------------------------------


class TestBuyAndHold:
    def test_buy_and_hold_valid_empty_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params("buy_and_hold", {})
        assert ok is True
        assert err is None
        assert cleaned == {}

    def test_buy_and_hold_ignores_extra_params(self):
        # Extra keys are irrelevant; the strategy has no rules to check.
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            "buy_and_hold", {"some_key": 42}
        )
        assert ok is True
        assert err is None
        assert cleaned == {}


# ---------------------------------------------------------------------------
# moving_average
# ---------------------------------------------------------------------------


class TestMovingAverage:
    STRATEGY = "moving_average"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 20, "slow_period": 50}
        )
        assert ok is True
        assert err is None
        assert cleaned["fast_period"] == 20
        assert cleaned["slow_period"] == 50

    def test_fast_above_slow_rejected(self):
        """Logical constraint: fast_period must be < slow_period."""
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 60, "slow_period": 50}
        )
        assert ok is False
        assert _err is not None

    def test_fast_equal_slow_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 50, "slow_period": 50}
        )
        assert ok is False
        assert _err is not None

    def test_fast_period_below_minimum(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 1, "slow_period": 50}
        )
        assert ok is False

    def test_fast_period_above_maximum(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 101, "slow_period": 150}
        )
        assert ok is False

    def test_slow_period_above_maximum(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 20, "slow_period": 201}
        )
        assert ok is False

    def test_slow_period_below_minimum(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 2, "slow_period": 9}
        )
        assert ok is False

    def test_boundary_values_accepted(self):
        """fast=2 (min), slow=200 (max)."""
        ok, _err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 2, "slow_period": 200}
        )
        assert ok is True
        assert cleaned["fast_period"] == 2
        assert cleaned["slow_period"] == 200

    def test_missing_params_uses_defaults(self):
        """Neither parameter provided → defaults (20, 50) should pass."""
        ok, _err, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["fast_period"] == 20
        assert cleaned["slow_period"] == 50

    def test_type_coercion_str_params(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": "20", "slow_period": "50"}
        )
        assert ok is True
        assert isinstance(cleaned["fast_period"], int)
        assert isinstance(cleaned["slow_period"], int)

    def test_wrong_type_unconvertible(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": "abc", "slow_period": 50}
        )
        assert ok is False
        assert _err is not None


# ---------------------------------------------------------------------------
# rsi
# ---------------------------------------------------------------------------


class TestRSI:
    STRATEGY = "rsi"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 14, "oversold": 30, "overbought": 70}
        )
        assert ok is True
        assert err is None
        assert cleaned == {"period": 14, "oversold": 30, "overbought": 70}

    def test_oversold_above_overbought_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 14, "oversold": 75, "overbought": 70}
        )
        assert ok is False
        assert _err is not None

    def test_oversold_equal_overbought_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 14, "oversold": 50, "overbought": 50}
        )
        assert ok is False

    def test_period_out_of_range_low(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 4, "oversold": 30, "overbought": 70}
        )
        assert ok is False

    def test_period_out_of_range_high(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 51, "oversold": 30, "overbought": 70}
        )
        assert ok is False

    def test_oversold_at_minimum(self):
        """oversold minimum is 10."""
        ok, _err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 14, "oversold": 10, "overbought": 70}
        )
        assert ok is True
        assert cleaned["oversold"] == 10

    def test_overbought_at_maximum(self):
        """overbought maximum is 90."""
        ok, _err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 14, "oversold": 30, "overbought": 90}
        )
        assert ok is True
        assert cleaned["overbought"] == 90

    def test_defaults_accepted(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned == {"period": 14, "oversold": 30, "overbought": 70}


# ---------------------------------------------------------------------------
# bollinger_bands
# ---------------------------------------------------------------------------


class TestBollingerBands:
    STRATEGY = "bollinger_bands"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 20, "num_std": 2.0}
        )
        assert ok is True
        assert err is None
        assert cleaned["period"] == 20
        assert cleaned["num_std"] == pytest.approx(2.0)

    def test_period_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 9, "num_std": 2.0}
        )
        assert ok is False

    def test_period_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 51, "num_std": 2.0}
        )
        assert ok is False

    def test_num_std_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 20, "num_std": 0.9}
        )
        assert ok is False

    def test_num_std_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 20, "num_std": 3.1}
        )
        assert ok is False

    def test_num_std_at_boundaries(self):
        for std in (1.0, 3.0):
            ok, _err, cleaned = StrategyValidator.validate_strategy_params(
                self.STRATEGY, {"period": 20, "num_std": std}
            )
            assert ok is True, f"num_std={std} should be accepted"
            assert cleaned["num_std"] == pytest.approx(std)

    def test_float_type_preserved(self):
        _, _, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 20, "num_std": 2}
        )
        assert isinstance(cleaned["num_std"], float)


# ---------------------------------------------------------------------------
# macd
# ---------------------------------------------------------------------------


class TestMACD:
    STRATEGY = "macd"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 12, "slow_period": 26, "signal_period": 9}
        )
        assert ok is True
        assert err is None
        assert cleaned == {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def test_fast_above_slow_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 30, "slow_period": 26, "signal_period": 9}
        )
        assert ok is False
        assert _err is not None

    def test_fast_equal_slow_rejected(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 26, "slow_period": 26, "signal_period": 9}
        )
        assert ok is False

    def test_signal_period_out_of_range(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 12, "slow_period": 26, "signal_period": 21}
        )
        assert ok is False

    def test_slow_period_above_max(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_period": 12, "slow_period": 51, "signal_period": 9}
        )
        assert ok is False

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned == {"fast_period": 12, "slow_period": 26, "signal_period": 9}


# ---------------------------------------------------------------------------
# mean_reversion
# ---------------------------------------------------------------------------


class TestMeanReversion:
    STRATEGY = "mean_reversion"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"lookback_period": 20, "entry_threshold": 2.0}
        )
        assert ok is True
        assert err is None
        assert cleaned["lookback_period"] == 20
        assert cleaned["entry_threshold"] == pytest.approx(2.0)

    def test_lookback_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"lookback_period": 9, "entry_threshold": 2.0}
        )
        assert ok is False

    def test_lookback_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"lookback_period": 101, "entry_threshold": 2.0}
        )
        assert ok is False

    def test_entry_threshold_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"lookback_period": 20, "entry_threshold": 0.9}
        )
        assert ok is False

    def test_entry_threshold_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"lookback_period": 20, "entry_threshold": 4.1}
        )
        assert ok is False

    def test_entry_threshold_at_boundaries(self):
        for threshold in (1.0, 4.0):
            ok, _, _ = StrategyValidator.validate_strategy_params(
                self.STRATEGY, {"lookback_period": 20, "entry_threshold": threshold}
            )
            assert ok is True, f"entry_threshold={threshold} should be accepted"

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["lookback_period"] == 20
        assert cleaned["entry_threshold"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# vwap
# ---------------------------------------------------------------------------


class TestVWAP:
    STRATEGY = "vwap"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"period": 20}
        )
        assert ok is True
        assert err is None
        assert cleaned["period"] == 20

    def test_period_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, {"period": 4})
        assert ok is False

    def test_period_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, {"period": 101})
        assert ok is False

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["period"] == 20


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------


class TestMomentum:
    STRATEGY = "momentum"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_window": 10, "slow_window": 30}
        )
        assert ok is True
        assert err is None
        assert cleaned == {"fast_window": 10, "slow_window": 30}

    def test_fast_above_slow_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_window": 40, "slow_window": 30}
        )
        assert ok is False
        assert _err is not None

    def test_fast_equal_slow_rejected(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_window": 30, "slow_window": 30}
        )
        assert ok is False

    def test_fast_window_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_window": 4, "slow_window": 30}
        )
        assert ok is False

    def test_slow_window_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"fast_window": 10, "slow_window": 101}
        )
        assert ok is False

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned == {"fast_window": 10, "slow_window": 30}


# ---------------------------------------------------------------------------
# stochastic
# ---------------------------------------------------------------------------


class TestStochastic:
    STRATEGY = "stochastic"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 14, "d_period": 3, "oversold": 20.0, "overbought": 80.0},
        )
        assert ok is True
        assert err is None
        assert cleaned["k_period"] == 14
        assert cleaned["d_period"] == 3

    def test_oversold_above_overbought_rejected(self):
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 14, "d_period": 3, "oversold": 85.0, "overbought": 80.0},
        )
        assert ok is False
        assert _err is not None

    def test_oversold_equal_overbought_rejected(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 14, "d_period": 3, "oversold": 50.0, "overbought": 50.0},
        )
        assert ok is False

    def test_k_period_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 4, "d_period": 3, "oversold": 20.0, "overbought": 80.0},
        )
        assert ok is False

    def test_d_period_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 14, "d_period": 21, "oversold": 20.0, "overbought": 80.0},
        )
        assert ok is False

    def test_overbought_float_type_preserved(self):
        _, _, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY,
            {"k_period": 14, "d_period": 3, "oversold": 20, "overbought": 80},
        )
        assert isinstance(cleaned["oversold"], float)
        assert isinstance(cleaned["overbought"], float)

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["k_period"] == 14
        assert cleaned["d_period"] == 3


# ---------------------------------------------------------------------------
# atr_trailing_stop
# ---------------------------------------------------------------------------


class TestATRTrailingStop:
    STRATEGY = "atr_trailing_stop"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"atr_period": 14, "atr_multiplier": 2.0}
        )
        assert ok is True
        assert err is None
        assert cleaned["atr_period"] == 14
        assert cleaned["atr_multiplier"] == pytest.approx(2.0)

    def test_atr_period_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"atr_period": 4, "atr_multiplier": 2.0}
        )
        assert ok is False

    def test_atr_period_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"atr_period": 51, "atr_multiplier": 2.0}
        )
        assert ok is False

    def test_atr_multiplier_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"atr_period": 14, "atr_multiplier": 0.4}
        )
        assert ok is False

    def test_atr_multiplier_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"atr_period": 14, "atr_multiplier": 10.1}
        )
        assert ok is False

    def test_atr_multiplier_at_boundaries(self):
        for mult in (0.5, 10.0):
            ok, _, cleaned = StrategyValidator.validate_strategy_params(
                self.STRATEGY, {"atr_period": 14, "atr_multiplier": mult}
            )
            assert ok is True, f"atr_multiplier={mult} should be accepted"
            assert cleaned["atr_multiplier"] == pytest.approx(mult)

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["atr_period"] == 14
        assert cleaned["atr_multiplier"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# turtle_trading
# ---------------------------------------------------------------------------


class TestTurtleTrading:
    STRATEGY = "turtle_trading"

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"entry_period": 20, "exit_period": 10}
        )
        assert ok is True
        assert err is None
        assert cleaned == {"entry_period": 20, "exit_period": 10}

    def test_entry_not_greater_than_exit_rejected(self):
        """entry_period must be > exit_period."""
        ok, _err, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"entry_period": 10, "exit_period": 10}
        )
        assert ok is False
        assert _err is not None

    def test_entry_less_than_exit_rejected(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"entry_period": 5, "exit_period": 10}
        )
        assert ok is False

    def test_entry_period_below_minimum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"entry_period": 4, "exit_period": 3}
        )
        assert ok is False

    def test_exit_period_above_maximum(self):
        ok, _, _ = StrategyValidator.validate_strategy_params(
            self.STRATEGY, {"entry_period": 70, "exit_period": 61}
        )
        assert ok is False

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["entry_period"] == 20
        assert cleaned["exit_period"] == 10


# ---------------------------------------------------------------------------
# multi_factor
# ---------------------------------------------------------------------------


class TestMultiFactor:
    STRATEGY = "multi_factor"

    VALID_PARAMS: ClassVar[dict] = {
        "momentum_window": 20,
        "mean_reversion_window": 5,
        "volume_window": 20,
        "volatility_window": 20,
        "entry_threshold": 0.4,
        "exit_threshold": 0.1,
    }

    def test_valid_params(self):
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            self.STRATEGY, self.VALID_PARAMS
        )
        assert ok is True
        assert err is None
        assert cleaned["momentum_window"] == 20
        assert cleaned["entry_threshold"] == pytest.approx(0.4)
        assert cleaned["exit_threshold"] == pytest.approx(0.1)

    def test_exit_threshold_above_entry_rejected(self):
        params = {**self.VALID_PARAMS, "exit_threshold": 0.5, "entry_threshold": 0.4}
        ok, _err, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is False
        assert _err is not None

    def test_exit_threshold_equal_entry_rejected(self):
        params = {**self.VALID_PARAMS, "exit_threshold": 0.4, "entry_threshold": 0.4}
        ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is False

    def test_momentum_window_below_minimum(self):
        params = {**self.VALID_PARAMS, "momentum_window": 4}
        ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is False

    def test_momentum_window_above_maximum(self):
        params = {**self.VALID_PARAMS, "momentum_window": 121}
        ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is False

    def test_entry_threshold_at_boundaries(self):
        for thr in (0.05, 3.0):
            params = {**self.VALID_PARAMS, "entry_threshold": thr, "exit_threshold": 0.01}
            ok, _, _ = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
            assert ok is True, f"entry_threshold={thr} should be accepted"

    def test_exit_threshold_at_zero(self):
        """exit_threshold minimum is 0.0; must be accepted."""
        params = {**self.VALID_PARAMS, "exit_threshold": 0.0, "entry_threshold": 0.4}
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is True
        assert cleaned["exit_threshold"] == pytest.approx(0.0)

    def test_defaults_pass(self):
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, {})
        assert ok is True
        assert cleaned["momentum_window"] == 20
        assert cleaned["exit_threshold"] == pytest.approx(0.1)

    def test_missing_single_param_uses_default(self):
        """Omit one param; expect it filled in from default while rest validate."""
        params = {k: v for k, v in self.VALID_PARAMS.items() if k != "volume_window"}
        ok, _, cleaned = StrategyValidator.validate_strategy_params(self.STRATEGY, params)
        assert ok is True
        assert cleaned["volume_window"] == 20  # ParameterRule default


# ---------------------------------------------------------------------------
# get_strategy_info
# ---------------------------------------------------------------------------


class TestGetStrategyInfo:
    def test_known_strategy_returns_dict(self):
        info = StrategyValidator.get_strategy_info("rsi")
        assert info is not None
        assert info["name"] == "rsi"
        assert "parameters" in info

    def test_rsi_info_has_all_params(self):
        info = StrategyValidator.get_strategy_info("rsi")
        params = info["parameters"]
        assert "period" in params
        assert "oversold" in params
        assert "overbought" in params

    def test_rsi_info_param_structure(self):
        info = StrategyValidator.get_strategy_info("rsi")
        period_info = info["parameters"]["period"]
        assert period_info["type"] == "int"
        assert period_info["default"] == 14
        assert period_info["min"] == 5
        assert period_info["max"] == 50
        assert period_info["required"] is True

    def test_buy_and_hold_returns_info(self):
        info = StrategyValidator.get_strategy_info("buy_and_hold")
        assert info is not None
        assert info["name"] == "buy_and_hold"
        assert info["parameters"] == {}

    def test_unknown_strategy_returns_none(self):
        info = StrategyValidator.get_strategy_info("nonexistent_strategy")
        assert info is None

    def test_all_known_strategies_return_non_none_info(self):
        for name in StrategyValidator.STRATEGY_RULES:
            info = StrategyValidator.get_strategy_info(name)
            assert info is not None, f"get_strategy_info({name!r}) returned None"


# ---------------------------------------------------------------------------
# get_all_strategies_info
# ---------------------------------------------------------------------------


class TestGetAllStrategiesInfo:
    def test_returns_list(self):
        result = StrategyValidator.get_all_strategies_info()
        assert isinstance(result, list)

    def test_includes_all_rule_strategies(self):
        result = StrategyValidator.get_all_strategies_info()
        names = {item["name"] for item in result}
        for strategy in StrategyValidator.STRATEGY_RULES:
            assert strategy in names, f"{strategy} missing from get_all_strategies_info()"

    def test_includes_buy_and_hold(self):
        result = StrategyValidator.get_all_strategies_info()
        names = {item["name"] for item in result}
        assert "buy_and_hold" in names

    def test_count_matches_rules_plus_one(self):
        """Length = len(STRATEGY_RULES) + 1 (buy_and_hold)."""
        result = StrategyValidator.get_all_strategies_info()
        assert len(result) == len(StrategyValidator.STRATEGY_RULES) + 1

    def test_all_entries_have_name_and_parameters(self):
        for item in StrategyValidator.get_all_strategies_info():
            assert "name" in item, f"Entry missing 'name': {item}"
            assert "parameters" in item, f"Entry missing 'parameters': {item}"


# ---------------------------------------------------------------------------
# Edge cases / cross-cutting
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_none_value_for_param_uses_default(self):
        """Explicitly passing None should fall through to the default."""
        ok, _, cleaned = StrategyValidator.validate_strategy_params(
            "vwap", {"period": None}
        )
        assert ok is True
        assert cleaned["period"] == 20

    def test_cleaned_params_never_populated_on_failure(self):
        """On any validation failure, cleaned params must be empty dict."""
        _, _, cleaned = StrategyValidator.validate_strategy_params(
            "rsi", {"period": 999, "oversold": 30, "overbought": 70}
        )
        assert cleaned == {}

    def test_validate_strategy_params_does_not_mutate_input(self):
        """The caller's dict must not be altered by validation."""
        params = {"fast_period": 20, "slow_period": 50}
        original = dict(params)
        StrategyValidator.validate_strategy_params("moving_average", params)
        assert params == original

    def test_extra_keys_in_params_are_ignored(self):
        """Unknown extra keys should not cause a crash or rejection."""
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            "vwap", {"period": 20, "totally_unknown_key": 999}
        )
        assert ok is True
        assert err is None
        # Extra key must not appear in cleaned output
        assert "totally_unknown_key" not in cleaned

    # BUG: required=True is set on every rule, but the code logs a note and
    # substitutes the default instead of returning an error when a required
    # param is absent.  The code at lines 371-375 of strategy_validator.py
    # reads:
    #   if value is None:
    #       if rule.required and rule.name not in parameters:
    #           logger.info(...)   # <-- only logs, does NOT reject
    #       cleaned_params[rule.name] = rule.default
    #       continue
    # This means required=True has no enforcement effect — missing required
    # fields silently get defaults.  The test below documents current
    # behavior; a human/owner should decide whether to enforce required.
    def test_bug_required_fields_not_enforced(self):
        """
        BUG (strategy_validator.py:371-375): required=True on a ParameterRule
        is never enforced.  Missing required parameters are silently replaced
        with their default values instead of causing a validation failure.
        Document current (permissive) behavior here; fix TBD.
        """
        # All required params for moving_average are absent — current code accepts.
        ok, err, cleaned = StrategyValidator.validate_strategy_params(
            "moving_average", {}
        )
        # Current behavior: ok=True, defaults substituted.
        assert ok is True  # BUG: should arguably be False
        assert err is None  # BUG: should arguably contain an error message
        assert cleaned["fast_period"] == 20  # default substituted silently
        assert cleaned["slow_period"] == 50  # default substituted silently
