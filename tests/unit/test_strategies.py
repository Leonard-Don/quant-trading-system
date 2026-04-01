"""
策略单元测试
"""

import pytest
import pandas as pd
import numpy as np

from src.strategy.strategies import (
    MovingAverageCrossover,
    RSIStrategy,
    BollingerBands,
    TurtleTradingStrategy,
    MultiFactorStrategy,
)
from src.strategy.advanced_strategies import MACDStrategy, MeanReversionStrategy


class TestMovingAverageCrossover:
    """移动平均交叉策略测试"""

    def test_initialization(self):
        """测试策略初始化"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        assert strategy.parameters["fast_period"] == 10
        assert strategy.parameters["slow_period"] == 20
        assert strategy.name == "MA_Crossover"

    def test_signal_generation(self, sample_data):
        """测试信号生成"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        signals = strategy.generate_signals(sample_data)

        # 检查信号长度
        assert len(signals) == len(sample_data)

        # 检查信号值范围
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)

    def test_invalid_parameters(self):
        """测试无效参数"""
        with pytest.raises(Exception):
            # fast_period应该小于slow_period
            MovingAverageCrossover(fast_period=20, slow_period=10)


class TestRSIStrategy:
    """RSI策略测试"""

    def test_rsi_calculation(self, sample_data):
        """测试RSI计算"""
        strategy = RSIStrategy(period=14)
        rsi = strategy.calculate_rsi(sample_data["close"])

        # RSI应该在0-100范围内
        assert rsi.dropna().min() >= 0
        assert rsi.dropna().max() <= 100

    def test_signal_generation(self, sample_data):
        """测试信号生成"""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)


class TestBollingerBands:
    """布林带策略测试"""

    def test_signal_generation(self, sample_data):
        """测试布林带信号生成"""
        strategy = BollingerBands(period=20, num_std=2)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)


class TestMACDStrategy:
    """MACD策略测试"""

    def test_signal_generation(self, sample_data):
        """测试MACD信号生成"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        assert strategy.name == "MACD"


class TestMeanReversionStrategy:
    """均值回归策略测试"""

    def test_signal_generation(self, sample_data):
        """测试均值回归信号生成"""
        strategy = MeanReversionStrategy(lookback_period=20, entry_threshold=2.0)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        assert strategy.name == "MeanReversion"


class TestTurtleTradingStrategy:
    """海龟交易策略测试"""

    def test_initialization(self):
        strategy = TurtleTradingStrategy(entry_period=20, exit_period=10)
        assert strategy.parameters["entry_period"] == 20
        assert strategy.parameters["exit_period"] == 10
        assert strategy.name == "TurtleTrading"

    def test_signal_generation(self, sample_data):
        strategy = TurtleTradingStrategy(entry_period=10, exit_period=5)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)

    def test_invalid_parameters(self):
        with pytest.raises(Exception):
            TurtleTradingStrategy(entry_period=10, exit_period=10)


class TestMultiFactorStrategy:
    def test_initialization(self):
        strategy = MultiFactorStrategy()
        assert strategy.parameters["momentum_window"] == 20
        assert strategy.parameters["entry_threshold"] == 0.4
        assert strategy.name == "MultiFactor"

    def test_signal_generation(self, sample_data):
        strategy = MultiFactorStrategy(
            momentum_window=10,
            mean_reversion_window=3,
            volume_window=10,
            volatility_window=10,
            entry_threshold=0.2,
            exit_threshold=0.05,
        )
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)

    def test_invalid_parameters(self):
        with pytest.raises(Exception):
            MultiFactorStrategy(entry_threshold=0.1, exit_threshold=0.2)
