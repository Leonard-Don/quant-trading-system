"""
回测引擎单元测试
"""

import pytest
import pandas as pd
import numpy as np

from src.backtest.backtester import Backtester
from src.strategy.strategies import BuyAndHold, MovingAverageCrossover


class DummyStrategy:
    """用于精确控制买卖信号的测试策略"""

    name = "DummyStrategy"

    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, data):
        return pd.Series(self._signals, index=data.index)


class DummyTargetStrategy(DummyStrategy):
    """返回目标仓位信号的测试策略。"""


class TestBacktester:
    """回测引擎测试"""

    def test_initialization(self):
        """测试回测器初始化"""
        backtester = Backtester(initial_capital=10000, commission=0.001, slippage=0.001)
        assert backtester.initial_capital == 10000
        assert backtester.commission == 0.001
        assert backtester.slippage == 0.001

    def test_backtest_execution(self, sample_data):
        """测试回测执行"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        backtester = Backtester(initial_capital=10000)

        results = backtester.run(strategy, sample_data)

        # 检查必要的结果字段
        required_fields = [
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "num_trades",
            "portfolio",
        ]
        for field in required_fields:
            assert field in results

        # 检查组合值是否为DataFrame
        assert isinstance(results["portfolio"], pd.DataFrame)
        assert len(results["portfolio"]) == len(sample_data)

    def test_commission_calculation(self, sample_data):
        """测试手续费计算"""
        # 使用更激进的参数确保产生交易信号
        strategy = MovingAverageCrossover(fast_period=3, slow_period=7)

        # 无手续费回测
        backtester_no_commission = Backtester(initial_capital=10000, commission=0)
        results_no_commission = backtester_no_commission.run(strategy, sample_data)

        # 有手续费回测
        backtester_with_commission = Backtester(
            initial_capital=10000, commission=0.001
        )  # 降低手续费避免过大影响
        results_with_commission = backtester_with_commission.run(strategy, sample_data)

        # 有手续费的回报应该更低（当有交易时）
        if results_no_commission["num_trades"] > 0:
            assert (
                results_with_commission["total_return"]
                <= results_no_commission["total_return"]
            )
        else:
            # 没有交易时，两者应该相等
            assert (
                abs(
                    results_with_commission["total_return"]
                    - results_no_commission["total_return"]
                )
                < 1e-10
            )

    def test_slippage_impact(self, sample_data):
        """测试滑点影响"""
        # 使用更激进的参数确保产生交易信号
        strategy = MovingAverageCrossover(fast_period=3, slow_period=7)

        # 无滑点回测
        backtester_no_slippage = Backtester(initial_capital=10000, slippage=0)
        results_no_slippage = backtester_no_slippage.run(strategy, sample_data)

        # 有滑点回测
        backtester_with_slippage = Backtester(
            initial_capital=10000, slippage=0.001
        )  # 降低滑点避免过大影响
        results_with_slippage = backtester_with_slippage.run(strategy, sample_data)

        # 有滑点的回报应该更低（当有交易时）
        if results_no_slippage["num_trades"] > 0:
            assert (
                results_with_slippage["total_return"]
                <= results_no_slippage["total_return"]
            )
        else:
            # 没有交易时，两者应该相等
            assert (
                abs(
                    results_with_slippage["total_return"]
                    - results_no_slippage["total_return"]
                )
                < 1e-10
            )

    def test_portfolio_consistency(self, sample_data):
        """测试组合一致性"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        backtester = Backtester(initial_capital=10000)

        results = backtester.run(strategy, sample_data)
        portfolio = results["portfolio"]

        # 检查组合值非负
        assert (portfolio["total"] >= 0).all()

        # 检查初始值
        assert portfolio["total"].iloc[0] == 10000

        # 检查现金和持仓的一致性
        total_value = portfolio["cash"] + portfolio["holdings"]
        np.testing.assert_array_almost_equal(
            portfolio["total"].values, total_value.values, decimal=2
        )

    def test_open_position_not_counted_as_completed_trade(self):
        """未平仓头寸不应进入已完成交易统计"""
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        data = pd.DataFrame({"close": [100, 110, 120, 130]}, index=dates)
        strategy = DummyStrategy([0, 1, 0, 0])

        results = Backtester(initial_capital=1000, commission=0, slippage=0).run(
            strategy, data
        )

        assert results["num_trades"] == 1
        assert results["total_completed_trades"] == 0
        assert results["has_open_position"] is True
        assert results["win_rate"] == 0
        assert results["max_consecutive_wins"] == 0
        assert results["max_consecutive_losses"] == 0
        assert results["net_profit"] == 180

    def test_consecutive_stats_follow_completed_trade_order(self):
        """连胜连败应按真实成交顺序统计，而不是按盈亏分组"""
        dates = pd.date_range("2024-01-01", periods=7, freq="D")
        data = pd.DataFrame(
            {"close": [100, 100, 110, 120, 110, 100, 110]}, index=dates
        )
        strategy = DummyStrategy([0, 1, -1, 1, -1, 1, -1])

        results = Backtester(initial_capital=10000, commission=0, slippage=0).run(
            strategy, data
        )

        assert results["num_trades"] == 6
        assert results["total_completed_trades"] == 3
        assert results["win_rate"] == pytest.approx(2 / 3)
        assert results["max_consecutive_wins"] == 1
        assert results["max_consecutive_losses"] == 1
        assert results["best_trade"] == 1000
        assert results["worst_trade"] == -910

    def test_buy_signal_on_first_bar_executes(self):
        """首根K线买入信号应能成交，并正确更新首日组合状态"""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        data = pd.DataFrame({"close": [100, 110, 120]}, index=dates)

        results = Backtester(initial_capital=1000, commission=0, slippage=0).run(
            DummyStrategy([1, 0, 0]), data
        )

        portfolio = results["portfolio"]
        assert results["num_trades"] == 1
        assert results["total_return"] == pytest.approx(0.2)
        assert portfolio["cash"].iloc[0] == 0
        assert portfolio["holdings"].iloc[0] == 1000
        assert portfolio["total"].iloc[0] == 1000

    def test_sell_signal_on_first_bar_without_position_does_not_trade(self):
        """首根K线卖出信号在空仓时不应错误成交"""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        data = pd.DataFrame({"close": [100, 90, 80]}, index=dates)

        results = Backtester(initial_capital=1000, commission=0, slippage=0).run(
            DummyStrategy([-1, 0, 0]), data
        )

        assert results["num_trades"] == 0
        assert results["total_return"] == 0

    def test_buy_and_hold_buys_on_first_bar(self):
        """买入持有策略应在首日建仓并产生非零收益"""
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        data = pd.DataFrame({"close": [100, 105, 110, 120]}, index=dates)

        results = Backtester(initial_capital=1000, commission=0, slippage=0).run(
            BuyAndHold(), data
        )

        assert results["num_trades"] == 1
        assert results["total_return"] == pytest.approx(0.2)
        assert results["final_value"] == pytest.approx(1200)

    def test_trailing_nan_price_bar_is_ignored(self):
        """尾部未完成K线若价格缺失，不应把最终组合价值冲成0。"""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        data = pd.DataFrame({"close": [100, 110, 120, 130, np.nan]}, index=dates)

        results = Backtester(initial_capital=1000, commission=0, slippage=0).run(
            BuyAndHold(), data
        )

        assert results["num_trades"] == 1
        assert results["final_value"] == pytest.approx(1300)
        assert results["total_return"] == pytest.approx(0.3)

    def test_target_exposure_signals_support_partial_rebalances(self):
        """目标仓位信号应支持分批建仓和减仓，而不只是全进全出。"""
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        data = pd.DataFrame({"close": [100, 110, 120, 120]}, index=dates)

        results = Backtester(
            initial_capital=1000,
            commission=0,
            slippage=0,
        ).run(DummyTargetStrategy([0.5, 1.0, 0.5, 0.0]), data)

        portfolio = results["portfolio"]
        assert results["num_trades"] == 4
        assert results["total_completed_trades"] >= 2
        assert portfolio["position"].iloc[0] == pytest.approx(5.0)
        assert portfolio["position"].iloc[1] == pytest.approx(9.0)
        assert portfolio["position"].iloc[2] == pytest.approx(4.0)
        assert portfolio["position"].iloc[3] == pytest.approx(0.0)
        assert results["final_value"] == pytest.approx(portfolio["total"].iloc[-1])

    def test_fractional_share_mode_keeps_decimal_position_sizes(self):
        """允许小数份额时，目标仓位执行应保留非整数头寸。"""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        data = pd.DataFrame({"close": [300, 315, 330]}, index=dates)

        results = Backtester(
            initial_capital=1000,
            commission=0,
            slippage=0,
            allow_fractional_shares=True,
        ).run(DummyTargetStrategy([0.25, 0.25, 0.0]), data)

        portfolio = results["portfolio"]
        assert portfolio["position"].iloc[0] == pytest.approx(1000 * 0.25 / 300)
        assert results["num_trades"] == 3
        assert (
            portfolio["holdings"].iloc[1] / portfolio["total"].iloc[1]
        ) == pytest.approx(0.25)

    def test_execution_diagnostics_include_resolved_signal_mode(self):
        """回测结果应显式包含执行语义诊断信息。"""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        data = pd.DataFrame({"close": [100, 110, 120]}, index=dates)

        results = Backtester(
            initial_capital=1000,
            commission=0,
            slippage=0,
            allow_fractional_shares=True,
        ).run(DummyTargetStrategy([0.5, 1.0, 0.0]), data)

        diagnostics = results["execution_diagnostics"]
        assert diagnostics["configured_signal_mode"] == "auto"
        assert diagnostics["resolved_signal_mode"] == "target"
        assert diagnostics["allow_fractional_shares"] is True
        assert diagnostics["position_sizer"] == "FixedFractionSizer"
