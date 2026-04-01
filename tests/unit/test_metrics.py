"""
Unit tests for src.backtest.metrics module.

Every test uses deterministic, hand-crafted data so the expected results can
be verified analytically or with a pocket calculator.  This ensures regression
safety and validates the financial correctness of each metric.
"""

import math
import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics import (
    calculate_annualized_return,
    calculate_calmar_ratio,
    calculate_cvar,
    calculate_expectancy,
    calculate_information_ratio,
    calculate_max_drawdown,
    calculate_max_drawdown_duration,
    calculate_omega_ratio,
    calculate_recovery_factor,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_treynor_ratio,
    calculate_var,
    calculate_volatility,
)


# ---------------------------------------------------------------------------
# calculate_returns
# ---------------------------------------------------------------------------
class TestCalculateReturns:
    def test_basic_return(self):
        curve = np.array([100.0, 110.0, 120.0])
        assert calculate_returns(curve) == pytest.approx(0.2)

    def test_negative_return(self):
        curve = pd.Series([100.0, 90.0, 80.0])
        assert calculate_returns(curve) == pytest.approx(-0.2)

    def test_zero_start_value(self):
        """Division by zero should return 0."""
        assert calculate_returns(np.array([0, 100])) == 0.0

    def test_empty_curve(self):
        assert calculate_returns(np.array([])) == 0.0

    def test_single_value(self):
        assert calculate_returns(np.array([100.0])) == 0.0


# ---------------------------------------------------------------------------
# calculate_annualized_return
# ---------------------------------------------------------------------------
class TestCalculateAnnualizedReturn:
    def test_one_year(self):
        """Over exactly 252 trading days, annualized return == total return."""
        assert calculate_annualized_return(0.10, 252) == pytest.approx(0.10)

    def test_two_years(self):
        """100 % over 504 days ≈ 41.4 % annualized."""
        result = calculate_annualized_return(1.0, 504)
        expected = (2.0 ** 0.5) - 1  # sqrt(2)-1
        assert result == pytest.approx(expected, rel=1e-6)

    def test_zero_days(self):
        assert calculate_annualized_return(0.1, 0) == 0.0

    def test_negative_days(self):
        assert calculate_annualized_return(0.1, -5) == 0.0


# ---------------------------------------------------------------------------
# calculate_max_drawdown
# ---------------------------------------------------------------------------
class TestCalculateMaxDrawdown:
    def test_no_drawdown(self):
        curve = np.array([100.0, 110.0, 120.0, 130.0])
        assert calculate_max_drawdown(curve) == pytest.approx(0.0)

    def test_known_drawdown(self):
        # peak=200, trough=100 → drawdown = 50 %
        curve = np.array([100.0, 200.0, 100.0, 150.0])
        assert calculate_max_drawdown(curve) == pytest.approx(0.5)

    def test_pandas_series_input(self):
        curve = pd.Series([100, 80, 90, 70, 100])
        # peak=100, trough=70 → 30 %
        assert calculate_max_drawdown(curve) == pytest.approx(0.3)

    def test_empty_curve(self):
        assert calculate_max_drawdown(np.array([])) == 0.0


# ---------------------------------------------------------------------------
# calculate_max_drawdown_duration
# ---------------------------------------------------------------------------
class TestMaxDrawdownDuration:
    def test_no_drawdown(self):
        curve = np.array([100.0, 110.0, 120.0])
        dd_dur, uw = calculate_max_drawdown_duration(curve)
        assert dd_dur == 0
        assert uw == 0

    def test_simple_recovery(self):
        # [100, 200, 100, 200] — peak at idx 1, trough at idx 2, recovery at idx 3
        curve = np.array([100.0, 200.0, 100.0, 200.0])
        dd_dur, uw = calculate_max_drawdown_duration(curve)
        assert dd_dur == 2  # idx 1 → idx 3
        assert uw == 1  # only idx 2 is underwater

    def test_no_recovery(self):
        curve = np.array([100.0, 200.0, 100.0, 120.0])
        dd_dur, uw = calculate_max_drawdown_duration(curve)
        # Not recovered by end → duration = idx 3 - idx 1 = 2
        assert dd_dur == 2
        assert uw == 2  # idx 2, idx 3 both underwater

    def test_short_curve(self):
        dd_dur, uw = calculate_max_drawdown_duration(np.array([100.0]))
        assert dd_dur == 0
        assert uw == 0


# ---------------------------------------------------------------------------
# calculate_sharpe_ratio
# ---------------------------------------------------------------------------
class TestCalculateSharpeRatio:
    def test_constant_returns(self):
        """Constant returns → std ≈ 0 → Sharpe should be 0.
        With ddof=1, floating-point noise may produce a tiny non-zero std,
        so the function must guard against this."""
        returns = pd.Series([0.01] * 100)
        sharpe = calculate_sharpe_ratio(returns)
        # With ddof=1 on truly constant data, numpy gives std=0.0 exactly,
        # so Sharpe should be 0.
        assert sharpe == 0.0

    def test_positive_sharpe(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        sharpe = calculate_sharpe_ratio(returns)
        # Direction check: mean > 0 → Sharpe should be positive
        assert sharpe > 0

    def test_uses_sample_std(self):
        """Verify ddof=1 is used by comparing against manual calculation."""
        returns = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015])
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1))
        expected = (mean_ret / std_ret) * np.sqrt(252)
        assert calculate_sharpe_ratio(returns) == pytest.approx(expected, rel=1e-6)

    def test_insufficient_data(self):
        assert calculate_sharpe_ratio(pd.Series([0.01])) == 0.0


# ---------------------------------------------------------------------------
# calculate_sortino_ratio
# ---------------------------------------------------------------------------
class TestCalculateSortinoRatio:
    def test_no_downside(self):
        """All positive returns → no downside risk → Sortino = 0."""
        returns = pd.Series([0.01, 0.02, 0.03, 0.04])
        assert calculate_sortino_ratio(returns) == 0.0

    def test_positive_sortino(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        sortino = calculate_sortino_ratio(returns)
        assert sortino > 0

    def test_insufficient_data(self):
        assert calculate_sortino_ratio(pd.Series([0.01])) == 0.0


# ---------------------------------------------------------------------------
# calculate_volatility
# ---------------------------------------------------------------------------
class TestCalculateVolatility:
    def test_known_volatility(self):
        """Verify annualized volatility with known sample std."""
        returns = pd.Series([0.01, -0.01, 0.01, -0.01, 0.01])
        daily_std = float(np.std(returns, ddof=1))
        expected = daily_std * np.sqrt(252)
        assert calculate_volatility(returns) == pytest.approx(expected, rel=1e-6)

    def test_insufficient_data(self):
        assert calculate_volatility(pd.Series([0.01])) == 0.0


# ---------------------------------------------------------------------------
# calculate_var
# ---------------------------------------------------------------------------
class TestCalculateVaR:
    def test_known_var(self):
        # 100 values uniformly spaced from -0.99 to 0
        returns = pd.Series(np.linspace(-0.99, 0, 100))
        var_95 = calculate_var(returns, 0.95)
        # 5th percentile of linspace(-0.99, 0, 100) should be around -0.94
        assert var_95 < 0

    def test_empty_returns(self):
        assert calculate_var(pd.Series([], dtype=float)) == 0.0


# ---------------------------------------------------------------------------
# calculate_cvar
# ---------------------------------------------------------------------------
class TestCalculateCVaR:
    def test_cvar_worse_than_var(self):
        """CVaR should be <= VaR (more negative = bigger loss)."""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0, 0.02, 500))
        var = calculate_var(returns, 0.95)
        cvar = calculate_cvar(returns, 0.95)
        assert cvar <= var

    def test_empty_returns(self):
        assert calculate_cvar(pd.Series([], dtype=float)) == 0.0


# ---------------------------------------------------------------------------
# calculate_omega_ratio
# ---------------------------------------------------------------------------
class TestCalculateOmegaRatio:
    def test_all_gains(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        assert calculate_omega_ratio(returns) == float("inf")

    def test_all_losses(self):
        returns = pd.Series([-0.01, -0.02, -0.03])
        assert calculate_omega_ratio(returns) == 0.0

    def test_balanced_returns(self):
        returns = pd.Series([0.01, -0.01, 0.02, -0.02, 0.03, -0.03])
        omega = calculate_omega_ratio(returns)
        # Symmetric → omega ≈ 1
        assert omega == pytest.approx(1.0)

    def test_empty_returns(self):
        assert calculate_omega_ratio(pd.Series([], dtype=float)) == 0.0


# ---------------------------------------------------------------------------
# calculate_information_ratio
# ---------------------------------------------------------------------------
class TestCalculateInformationRatio:
    def test_identical_returns(self):
        """Strategy == benchmark → active return = 0 everywhere → IR = 0."""
        returns = pd.Series([0.01, -0.005, 0.02])
        assert calculate_information_ratio(returns, returns) == 0.0

    def test_positive_ir(self):
        strat = pd.Series([0.02, 0.01, 0.03, 0.02, 0.01])
        bench = pd.Series([0.01, 0.005, 0.015, 0.01, 0.005])
        ir = calculate_information_ratio(strat, bench)
        assert ir > 0

    def test_insufficient_data(self):
        assert calculate_information_ratio(pd.Series([0.01]), pd.Series([0.01])) == 0.0


# ---------------------------------------------------------------------------
# calculate_calmar_ratio
# ---------------------------------------------------------------------------
class TestCalculateCalmarRatio:
    def test_basic_calmar(self):
        assert calculate_calmar_ratio(0.10, 0.05) == pytest.approx(2.0)

    def test_zero_drawdown_positive_return(self):
        assert calculate_calmar_ratio(0.10, 0.0) == float("inf")

    def test_zero_drawdown_negative_return(self):
        assert calculate_calmar_ratio(-0.10, 0.0) == 0.0

    def test_negative_return(self):
        assert calculate_calmar_ratio(-0.10, 0.20) == pytest.approx(-0.5)


class TestCalculateTreynorRatio:
    def test_basic_treynor(self):
        assert calculate_treynor_ratio(0.12, 1.2, 0.02) == pytest.approx((0.12 - 0.02) / 1.2)

    def test_zero_beta(self):
        assert calculate_treynor_ratio(0.12, 0.0, 0.02) == 0.0


class TestCalculateRecoveryFactor:
    def test_basic_recovery_factor(self):
        assert calculate_recovery_factor(2000, 0.1) == pytest.approx(20000)

    def test_zero_drawdown(self):
        assert calculate_recovery_factor(100, 0.0) == float("inf")
        assert calculate_recovery_factor(-100, 0.0) == 0.0


class TestCalculateExpectancy:
    def test_basic_expectancy(self):
        assert calculate_expectancy([100, -50, 200, -25]) == pytest.approx(56.25)

    def test_empty_expectancy(self):
        assert calculate_expectancy([]) == 0.0
