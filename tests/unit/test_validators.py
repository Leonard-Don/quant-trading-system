"""Unit tests for src.utils.validators.

Pure validation logic — no network, no fixtures. Covers the public validators'
happy paths and every raise branch.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.utils.exceptions import ValidationError
from src.utils.validators import (
    validate_backtest_params,
    validate_dataframe,
    validate_date_range,
    validate_signals,
    validate_strategy_parameters,
    validate_symbol,
)


class TestValidateSymbol:
    def test_uppercases_and_strips(self):
        assert validate_symbol("  aapl ") == "AAPL"

    def test_returns_already_valid(self):
        assert validate_symbol("MSFT") == "MSFT"

    @pytest.mark.parametrize("bad", ["", None, 123, []])
    def test_empty_or_non_string_raises(self, bad):
        with pytest.raises(ValidationError):
            validate_symbol(bad)

    @pytest.mark.parametrize("bad", ["TOOLONG", "AB1", "A.B", "12345"])
    def test_bad_format_raises(self, bad):
        with pytest.raises(ValidationError):
            validate_symbol(bad)


class TestValidateDateRange:
    def test_valid_range_passes(self):
        start = datetime(2020, 1, 1)
        end = datetime(2020, 6, 1)
        # No exception => pass
        assert validate_date_range(start, end) is None

    def test_none_args_are_noop(self):
        assert validate_date_range(None, None) is None
        assert validate_date_range(datetime(2020, 1, 1), None) is None

    def test_start_after_end_raises(self):
        with pytest.raises(ValidationError):
            validate_date_range(datetime(2021, 1, 1), datetime(2020, 1, 1))

    def test_equal_dates_raise(self):
        d = datetime(2020, 1, 1)
        with pytest.raises(ValidationError):
            validate_date_range(d, d)

    def test_end_in_future_raises(self):
        start = datetime(2020, 1, 1)
        future = datetime.now() + timedelta(days=10)
        with pytest.raises(ValidationError):
            validate_date_range(start, future)

    def test_range_over_ten_years_raises(self):
        start = datetime(2000, 1, 1)
        end = datetime(2015, 1, 1)  # >3650 days, and in the past
        with pytest.raises(ValidationError):
            validate_date_range(start, end)


class TestValidateStrategyParameters:
    def test_moving_average_defaults(self):
        out = validate_strategy_parameters("moving_average", {})
        assert out == {"fast_period": 20, "slow_period": 50}

    def test_moving_average_fast_ge_slow_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters(
                "moving_average", {"fast_period": 50, "slow_period": 50}
            )

    def test_moving_average_non_int_fast_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters("moving_average", {"fast_period": 0})

    def test_rsi_defaults(self):
        out = validate_strategy_parameters("rsi", {})
        assert out == {"period": 14, "oversold": 30, "overbought": 70}

    def test_rsi_oversold_ge_overbought_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters("rsi", {"oversold": 80, "overbought": 70})

    def test_rsi_threshold_out_of_bounds_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters("rsi", {"oversold": 0})
        with pytest.raises(ValidationError):
            validate_strategy_parameters("rsi", {"overbought": 100})

    def test_bollinger_bands_defaults_and_float_cast(self):
        out = validate_strategy_parameters("bollinger_bands", {"num_std": 3})
        assert out == {"period": 20, "num_std": 3.0}
        assert isinstance(out["num_std"], float)

    def test_bollinger_bands_bad_std_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters("bollinger_bands", {"num_std": 0})

    def test_macd_defaults(self):
        out = validate_strategy_parameters("macd", {})
        assert out == {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def test_macd_fast_ge_slow_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters(
                "macd", {"fast_period": 30, "slow_period": 26}
            )

    def test_macd_bad_signal_raises(self):
        with pytest.raises(ValidationError):
            validate_strategy_parameters("macd", {"signal_period": 0})

    def test_unknown_strategy_returns_empty(self):
        assert validate_strategy_parameters("unknown", {"foo": 1}) == {}


class TestValidateBacktestParams:
    def test_valid_params_pass(self):
        assert validate_backtest_params(100000, 0.001, 0.0005) is None

    def test_zero_or_negative_capital_raises(self):
        with pytest.raises(ValidationError):
            validate_backtest_params(0, 0.001, 0.001)

    def test_negative_commission_raises(self):
        with pytest.raises(ValidationError):
            validate_backtest_params(1000, -0.01, 0.001)

    def test_negative_slippage_raises(self):
        with pytest.raises(ValidationError):
            validate_backtest_params(1000, 0.001, -0.01)

    def test_excessive_commission_raises(self):
        with pytest.raises(ValidationError):
            validate_backtest_params(1000, 0.2, 0.001)

    def test_excessive_slippage_raises(self):
        with pytest.raises(ValidationError):
            validate_backtest_params(1000, 0.001, 0.2)


class TestValidateDataframe:
    def _good_df(self):
        return pd.DataFrame(
            {
                "open": [1.0, 2.0],
                "high": [2.0, 3.0],
                "low": [0.5, 1.5],
                "close": [1.5, 2.5],
                "volume": [100, 200],
            }
        )

    def test_valid_df_passes(self):
        assert validate_dataframe(self._good_df(), ["open", "close"]) is None

    def test_none_or_empty_raises(self):
        with pytest.raises(ValidationError):
            validate_dataframe(None)
        with pytest.raises(ValidationError):
            validate_dataframe(pd.DataFrame())

    def test_missing_required_columns_raises(self):
        with pytest.raises(ValidationError):
            validate_dataframe(self._good_df(), ["open", "missing_col"])

    def test_nan_values_raise(self):
        df = self._good_df()
        df.loc[0, "close"] = None
        with pytest.raises(ValidationError):
            validate_dataframe(df)

    def test_non_numeric_price_column_raises(self):
        df = self._good_df()
        df["close"] = ["a", "b"]
        with pytest.raises(ValidationError):
            validate_dataframe(df)


class TestValidateSignals:
    def test_valid_signals_pass(self):
        sig = pd.Series([1, 0, -1, 0])
        assert validate_signals(sig, 4) is None

    def test_none_or_empty_raises(self):
        with pytest.raises(ValidationError):
            validate_signals(None, 0)
        with pytest.raises(ValidationError):
            validate_signals(pd.Series([], dtype=float), 0)

    def test_length_mismatch_raises(self):
        with pytest.raises(ValidationError):
            validate_signals(pd.Series([1, 0]), 5)

    def test_invalid_signal_value_raises(self):
        with pytest.raises(ValidationError):
            validate_signals(pd.Series([1, 2, -1]), 3)

    def test_nan_signals_are_ignored(self):
        # NaN values are dropped before the membership check, so they pass.
        sig = pd.Series([1.0, float("nan"), -1.0])
        assert validate_signals(sig, 3) is None
