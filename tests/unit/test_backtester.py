"""
回测引擎单元测试
"""

import pytest
import pandas as pd
import numpy as np

from src.backtest.backtester import Backtester
from src.strategy.strategies import MovingAverageCrossover


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
