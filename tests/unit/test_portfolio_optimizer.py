"""Unit tests for src.strategy.portfolio_optimizer.

Optimization runs scipy SLSQP on tiny, well-conditioned return matrices so the
solver converges deterministically. Assertions focus on the contract that must
hold regardless of solver internals: weights sum to ~1, bounds are respected,
the labelled method is echoed, and obviously-dominant assets get the most
weight. No network, no randomness in the asserted quantities.
"""

import numpy as np
import pandas as pd
import pytest

from src.strategy.portfolio_optimizer import (
    DynamicRebalancer,
    PortfolioOptimizer,
    StrategyWeightOptimizer,
)


def returns_frame(seed=0, n=252, cols=("A", "B", "C"), means=(0.0008, 0.0003, 0.0001)):
    """Independent-ish daily returns with distinct drifts so the optimizer has a
    clear preference order (A best Sharpe, C worst)."""
    rng = np.random.default_rng(seed)
    data = {}
    for col, mu in zip(cols, means, strict=False):
        data[col] = rng.normal(mu, 0.01, n)
    return pd.DataFrame(data)


@pytest.fixture
def opt():
    return PortfolioOptimizer(risk_free_rate=0.02)


class TestPortfolioStats:
    def test_stats_match_hand_calc(self, opt):
        # Two assets, deterministic constant daily returns -> zero covariance.
        # Constant series has 0 std -> volatility 0 -> sharpe = inf/nan; avoid that
        # by giving a tiny variation. Use a 2-row frame we can reason about.
        df = pd.DataFrame({"A": [0.01, 0.02], "B": [0.00, 0.01]})
        w = np.array([0.5, 0.5])
        ret, vol, sharpe = opt.calculate_portfolio_stats(w, df)
        mean_annual = df.mean().values * 252
        expected_ret = float(np.dot(w, mean_annual))
        assert ret == pytest.approx(expected_ret)
        assert vol > 0
        assert sharpe == pytest.approx((ret - 0.02) / vol)


class TestMaxSharpe:
    def test_weights_sum_to_one_and_within_bounds(self, opt):
        df = returns_frame(seed=1)
        res = opt.optimize_max_sharpe(df)
        assert res["success"] is True
        assert res["optimization_method"] == "max_sharpe"
        w = np.array(list(res["weights"].values()))
        assert w.sum() == pytest.approx(1.0, abs=1e-6)
        # default bounds [0, 1] respected (allow tiny solver slack)
        assert (w >= -1e-6).all()
        assert (w <= 1.0 + 1e-6).all()
        # cached on the instance
        assert opt.optimal_weights is not None
        assert opt.sharpe_ratio == pytest.approx(res["sharpe_ratio"])

    def test_best_asset_gets_most_weight(self, opt):
        # A has the highest drift / Sharpe -> should receive the largest weight.
        df = returns_frame(seed=2)
        res = opt.optimize_max_sharpe(df)
        weights = res["weights"]
        assert weights["A"] == max(weights.values())

    def test_include_short_allows_negative_weights_bounds(self):
        o = PortfolioOptimizer()
        df = returns_frame(seed=3)
        res = o.optimize_max_sharpe(df, include_short=True)
        assert res["success"] is True
        w = np.array(list(res["weights"].values()))
        assert w.sum() == pytest.approx(1.0, abs=1e-6)
        # short bounds are [-1, 1]
        assert (w >= -1.0 - 1e-6).all()
        assert (w <= 1.0 + 1e-6).all()


class TestMinVariance:
    def test_min_variance_constraints(self, opt):
        df = returns_frame(seed=4)
        res = opt.optimize_min_variance(df)
        assert res["success"] is True
        assert res["optimization_method"] == "min_variance"
        w = np.array(list(res["weights"].values()))
        assert w.sum() == pytest.approx(1.0, abs=1e-6)
        assert (w >= -1e-6).all()

    def test_min_variance_prefers_lower_vol_asset(self):
        # Build returns where one asset is markedly less volatile -> it dominates.
        rng = np.random.default_rng(9)
        df = pd.DataFrame(
            {
                "lowvol": rng.normal(0.0003, 0.002, 252),
                "highvol": rng.normal(0.0003, 0.03, 252),
            }
        )
        o = PortfolioOptimizer()
        res = o.optimize_min_variance(df)
        assert res["weights"]["lowvol"] > res["weights"]["highvol"]


class TestRiskParity:
    def test_risk_parity_constraints_and_min_weight(self, opt):
        df = returns_frame(seed=5)
        res = opt.optimize_risk_parity(df)
        assert res["success"] is True
        assert res["optimization_method"] == "risk_parity"
        w = np.array(list(res["weights"].values()))
        assert w.sum() == pytest.approx(1.0, abs=1e-6)
        # risk-parity uses a hard 1% floor
        assert (w >= 0.01 - 1e-6).all()
        # risk contributions reported and roughly equal across assets
        rc = np.array(list(res["risk_contributions"].values()))
        assert len(rc) == 3
        # contributions should be close to one another (parity)
        assert rc.std() / rc.mean() < 0.5


class TestTargetReturnAndFrontier:
    def test_target_return_hits_target(self, opt):
        df = returns_frame(seed=6)
        mean_annual = df.mean() * 252
        target = float((mean_annual.min() + mean_annual.max()) / 2)
        res = opt.optimize_target_return(df, target)
        assert res["success"] is True
        assert res["target_return"] == pytest.approx(target)
        # the achieved return should equal the target (equality constraint)
        assert res["expected_return"] == pytest.approx(target, abs=1e-4)

    def test_efficient_frontier_monotone_returns(self, opt):
        df = returns_frame(seed=7)
        frontier = opt.generate_efficient_frontier(df, n_points=8)
        assert len(frontier) >= 2
        rets = [p["return"] for p in frontier]
        # frontier is generated over a linspace of increasing target returns
        assert rets == sorted(rets)
        for p in frontier:
            assert "volatility" in p and "sharpe" in p


class TestDispatchAndMatrices:
    def test_optimize_strategy_weights_dispatch(self, opt):
        df = returns_frame(seed=8)
        for method in ("max_sharpe", "min_variance", "risk_parity"):
            res = opt.optimize_strategy_weights(df, method)
            assert res["optimization_method"] == method

    def test_unknown_method_raises(self, opt):
        df = returns_frame(seed=8)
        with pytest.raises(ValueError):
            opt.optimize_strategy_weights(df, "nope")

    def test_correlation_and_covariance_matrices(self, opt):
        df = returns_frame(seed=10)
        corr = opt.get_correlation_matrix(df)
        assert corr.shape == (3, 3)
        # diagonal of a correlation matrix is 1
        assert np.allclose(np.diag(corr.values), 1.0)
        cov_annual = opt.get_covariance_matrix(df, annualized=True)
        cov_daily = opt.get_covariance_matrix(df, annualized=False)
        # annualized = daily * 252
        assert np.allclose(cov_annual.values, cov_daily.values * 252)


class TestDynamicRebalancer:
    def test_rebalance_needed_when_drift_exceeds_threshold(self):
        rb = DynamicRebalancer(rebalance_threshold=0.05)
        assert rb.check_rebalance_needed({"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.4})
        assert not rb.check_rebalance_needed(
            {"A": 0.5, "B": 0.5}, {"A": 0.52, "B": 0.48}
        )

    def test_rebalance_needed_when_asset_missing_from_current(self):
        rb = DynamicRebalancer(rebalance_threshold=0.05)
        # missing asset treated as current weight 0 -> diff 0.3 > threshold
        assert rb.check_rebalance_needed({}, {"A": 0.3})

    def test_calculate_trades_signed_amounts(self):
        rb = DynamicRebalancer()
        trades = rb.calculate_trades(
            {"A": 0.5, "B": 0.5}, {"A": 0.7, "B": 0.3}, portfolio_value=100_000
        )
        # A: +0.2 * 100k = +20k (buy), B: -0.2 * 100k = -20k (sell)
        assert trades["A"] == pytest.approx(20_000)
        assert trades["B"] == pytest.approx(-20_000)

    def test_calculate_trades_handles_new_asset(self):
        rb = DynamicRebalancer()
        trades = rb.calculate_trades({"A": 1.0}, {"B": 1.0}, portfolio_value=1000)
        assert trades["A"] == pytest.approx(-1000)  # fully sold
        assert trades["B"] == pytest.approx(1000)  # fully bought


class TestStrategyWeightOptimizer:
    def test_bounds_use_max_weight_cap(self):
        swo = StrategyWeightOptimizer(min_weight=0.0, max_weight=0.5)
        assert swo.optimizer.constraints["max_weight"] == 0.5
        assert swo.optimizer.constraints["min_weight"] == 0.0

    def test_optimize_from_backtest_needs_two_strategies(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=60)
        res = swo.optimize_from_backtest_results(
            {"only": {"returns": pd.Series(np.zeros(60), index=idx)}}
        )
        assert res["success"] is False

    def test_optimize_from_backtest_needs_enough_history(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=10)
        rng = np.random.default_rng(1)
        res = swo.optimize_from_backtest_results(
            {
                "a": {"returns": pd.Series(rng.normal(0, 0.01, 10), index=idx)},
                "b": {"returns": pd.Series(rng.normal(0, 0.01, 10), index=idx)},
            }
        )
        # only 10 rows < 30 -> rejected
        assert res["success"] is False

    def test_optimize_from_backtest_success_caches_weights(self):
        swo = StrategyWeightOptimizer(max_weight=0.7)
        idx = pd.date_range("2020-01-01", periods=120)
        rng = np.random.default_rng(4)
        res = swo.optimize_from_backtest_results(
            {
                "a": {"returns": pd.Series(rng.normal(0.0006, 0.01, 120), index=idx)},
                "b": {"returns": pd.Series(rng.normal(0.0002, 0.01, 120), index=idx)},
            },
            method="max_sharpe",
        )
        assert res["success"] is True
        assert swo.optimal_weights == res["weights"]
        assert len(swo.optimization_history) == 1
        # max-weight cap honoured
        assert all(v <= 0.7 + 1e-6 for v in res["weights"].values())

    def test_optimize_from_signals(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=120)
        rng = np.random.default_rng(6)
        close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)), index=idx)
        price = pd.DataFrame({"close": close})
        # two simple signal series
        sig_a = pd.Series(np.where(rng.normal(size=120) > 0, 1, -1), index=idx)
        sig_b = pd.Series(np.where(rng.normal(size=120) > 0, 1, -1), index=idx)
        res = swo.optimize_from_signals({"a": sig_a, "b": sig_b}, price)
        # may succeed or report insufficient — but must be a dict with 'success'
        assert "success" in res

    def test_get_weighted_signal_equal_when_no_optimal(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=5)
        sigs = {
            "a": pd.Series([1, 1, 1, 1, 1], index=idx),
            "b": pd.Series([1, 1, 1, 1, 1], index=idx),
        }
        out = swo.get_weighted_signal(sigs)
        # equal-weight of all +1 -> mean 1.0 > 0.3 -> discrete +1
        assert (out == 1).all()

    def test_get_weighted_signal_uses_optimal_weights(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=4)
        swo.optimal_weights = {"a": 1.0, "b": 0.0}
        sigs = {
            "a": pd.Series([1, 1, -1, -1], index=idx),
            "b": pd.Series([-1, -1, 1, 1], index=idx),  # weight 0, ignored
        }
        out = swo.get_weighted_signal(sigs)
        # only 'a' counts -> +1,+1,-1,-1
        assert list(out.values) == [1, 1, -1, -1]

    def test_compare_strategies_columns_and_sort(self):
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=120)
        rng = np.random.default_rng(12)
        df = pd.DataFrame(
            {
                "good": rng.normal(0.001, 0.01, 120),
                "bad": rng.normal(-0.001, 0.01, 120),
            },
            index=idx,
        )
        out = swo.compare_strategies(df)
        expected_cols = {
            "strategy",
            "annual_return",
            "annual_volatility",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "calmar_ratio",
            "optimal_weight",
        }
        assert expected_cols.issubset(set(out.columns))
        # sorted by sharpe descending
        sharpes = out["sharpe_ratio"].tolist()
        assert sharpes == sorted(sharpes, reverse=True)

    def test_compare_strategies_with_some_valid_and_some_short(self):
        # A strategy with < 10 obs is skipped; a valid one still appears. This
        # is the realistic mixed case and exercises the skip branch without
        # tripping the empty-frame bug documented below.
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=40)
        rng = np.random.default_rng(21)
        full = rng.normal(0.0005, 0.01, 40)
        short = np.concatenate([rng.normal(0, 0.01, 6), [np.nan] * 34])
        df = pd.DataFrame({"good": full, "short": short}, index=idx)
        out = swo.compare_strategies(df)
        assert list(out["strategy"]) == ["good"]  # 'short' dropped

    def test_compare_strategies_all_short_returns_empty_frame(self):
        # When EVERY strategy has < 10 observations they are all skipped,
        # leaving an empty `metrics` list. compare_strategies must return an
        # empty DataFrame that still carries the expected columns, rather than
        # calling ``.sort_values('sharpe_ratio')`` on a column-less frame (which
        # raised ``KeyError: 'sharpe_ratio'``).
        swo = StrategyWeightOptimizer()
        idx = pd.date_range("2020-01-01", periods=5)
        df = pd.DataFrame({"tiny": [0.01, -0.01, 0.0, 0.01, -0.01]}, index=idx)
        out = swo.compare_strategies(df)
        assert out.empty
        expected_cols = {
            "strategy",
            "annual_return",
            "annual_volatility",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "calmar_ratio",
            "optimal_weight",
        }
        assert expected_cols.issubset(set(out.columns))
