"""策略单元测试

These smoke tests deliberately construct inputs where a strategy MUST emit a
known signal at a known bar, then assert that it does. A length-only /
value-range-only check would be passed by a strategy that never trades — which
is exactly the silent-failure mode these tests are written to catch.
"""

import numpy as np
import pandas as pd
import pytest

from src.strategy.advanced_strategies import MACDStrategy, MeanReversionStrategy
from src.strategy.strategies import (
    BollingerBands,
    MovingAverageCrossover,
    MultiFactorStrategy,
    RSIStrategy,
    TurtleTradingStrategy,
)


def _ohlcv_from_close(close):
    """Build a deterministic OHLCV frame from a close-price sequence."""
    close = pd.Series(close, dtype=float)
    index = pd.date_range("2024-01-01", periods=len(close), freq="D")
    close.index = index
    high = close * 1.005
    low = close * 0.995
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": pd.Series(1_000_000.0, index=index),
        }
    )


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

    def test_golden_cross_emits_buy_at_known_bar(self):
        """A flat run followed by a sharp rally forces the fast MA to cross
        above the slow MA exactly once → exactly one buy signal, and it must
        land after the rally begins."""
        # 12 flat bars, then 12 sharply rising bars.
        close = [100.0] * 12 + list(np.linspace(101.0, 160.0, 12))
        data = _ohlcv_from_close(close)

        signals = MovingAverageCrossover(fast_period=3, slow_period=6).generate_signals(data)

        buy_bars = list(np.where(signals.to_numpy() == 1)[0])
        assert buy_bars, "an unambiguous golden cross must produce a buy signal"
        assert (signals == 1).sum() == 1, "exactly one crossover up expected"
        assert buy_bars[0] >= 12, "the buy must occur once the rally is underway"
        assert not (signals == -1).any(), "no death cross in a pure uptrend"

    def test_death_cross_emits_sell_at_known_bar(self):
        """A flat run followed by a sharp sell-off forces a single death
        cross → exactly one sell signal."""
        close = [100.0] * 12 + list(np.linspace(99.0, 40.0, 12))
        data = _ohlcv_from_close(close)

        signals = MovingAverageCrossover(fast_period=3, slow_period=6).generate_signals(data)

        sell_bars = list(np.where(signals.to_numpy() == -1)[0])
        assert sell_bars, "an unambiguous death cross must produce a sell signal"
        assert (signals == -1).sum() == 1
        assert sell_bars[0] >= 12
        assert not (signals == 1).any()

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

    def test_sustained_decline_drives_rsi_oversold_buy(self):
        """A long monotonic decline drives RSI toward 0 → the strategy must
        emit a buy once RSI falls below the oversold threshold."""
        close = list(np.linspace(200.0, 80.0, 40))
        data = _ohlcv_from_close(close)

        signals = RSIStrategy(period=14, oversold=30, overbought=70).generate_signals(data)

        assert (signals == 1).any(), "a sustained decline must trip the oversold buy"
        assert not (signals == -1).any()

    def test_sustained_rally_drives_rsi_overbought_sell(self):
        """A long monotonic rally drives RSI toward 100 → the strategy must
        emit a sell once RSI rises above the overbought threshold."""
        close = list(np.linspace(80.0, 200.0, 40))
        data = _ohlcv_from_close(close)

        signals = RSIStrategy(period=14, oversold=30, overbought=70).generate_signals(data)

        assert (signals == -1).any(), "a sustained rally must trip the overbought sell"
        assert not (signals == 1).any()


class TestBollingerBands:
    """布林带策略测试"""

    def test_signal_generation(self, sample_data):
        """测试布林带信号生成"""
        strategy = BollingerBands(period=20, num_std=2)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        unique_signals = signals.dropna().unique()
        assert all(signal in [-1, 0, 1] for signal in unique_signals)

    def test_price_spike_above_upper_band_emits_sell(self):
        """A flat window establishes a tight band; a sharp single-bar spike
        then closes above the upper band → a sell signal."""
        close = [100.0] * 20 + [140.0]
        data = _ohlcv_from_close(close)

        signals = BollingerBands(period=20, num_std=2).generate_signals(data)

        assert signals.iloc[-1] == -1, "a close above the upper band must sell"

    def test_price_drop_below_lower_band_emits_buy(self):
        """A flat window then a sharp single-bar drop closes below the lower
        band → a buy signal."""
        close = [100.0] * 20 + [60.0]
        data = _ohlcv_from_close(close)

        signals = BollingerBands(period=20, num_std=2).generate_signals(data)

        assert signals.iloc[-1] == 1, "a close below the lower band must buy"


class TestMACDStrategy:
    """MACD策略测试"""

    def test_signal_generation(self, sample_data):
        """测试MACD信号生成"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        assert strategy.name == "MACD"

    def test_uptrend_drives_macd_above_signal_line(self):
        """In a sustained rally the fast EMA outruns the slow EMA, lifting
        MACD above its signal line → the final bars must be long (+1)."""
        close = list(np.linspace(100.0, 260.0, 80))
        data = _ohlcv_from_close(close)

        signals = MACDStrategy(fast_period=12, slow_period=26, signal_period=9).generate_signals(data)

        assert len(signals) == len(data)
        assert signals.iloc[-1] == 1, "a sustained rally must hold MACD above signal"
        assert (signals == 1).any()

    def test_downtrend_drives_macd_below_signal_line(self):
        """In a sustained sell-off MACD sits below its signal line → the
        final bars must be short (-1)."""
        close = list(np.linspace(260.0, 100.0, 80))
        data = _ohlcv_from_close(close)

        signals = MACDStrategy(fast_period=12, slow_period=26, signal_period=9).generate_signals(data)

        assert signals.iloc[-1] == -1, "a sustained sell-off must hold MACD below signal"
        assert (signals == -1).any()


class TestMeanReversionStrategy:
    """均值回归策略测试"""

    def test_signal_generation(self, sample_data):
        """测试均值回归信号生成"""
        strategy = MeanReversionStrategy(lookback_period=20, entry_threshold=2.0)
        signals = strategy.generate_signals(sample_data)

        assert len(signals) == len(sample_data)
        assert strategy.name == "MeanReversion"

    def test_spike_above_mean_emits_sell(self):
        """A flat window gives a near-zero rolling std; a sharp upward spike
        produces a large positive z-score → a sell signal."""
        close = [100.0] * 20 + [115.0]
        data = _ohlcv_from_close(close)

        signals = MeanReversionStrategy(lookback_period=20, entry_threshold=2.0).generate_signals(data)

        assert signals.iloc[-1] == -1, "a large positive z-score must sell"

    def test_drop_below_mean_emits_buy(self):
        """A flat window then a sharp downward spike produces a large
        negative z-score → a buy signal."""
        close = [100.0] * 20 + [85.0]
        data = _ohlcv_from_close(close)

        signals = MeanReversionStrategy(lookback_period=20, entry_threshold=2.0).generate_signals(data)

        assert signals.iloc[-1] == 1, "a large negative z-score must buy"


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

    def test_breakout_above_donchian_high_emits_entry(self):
        """Price closes above the prior entry-period rolling high → a
        breakout entry (+1). The flat window then drop forces an exit (-1)
        once price breaches the exit-period low."""
        close = [100.0] * 12 + [140.0] + [100.0] * 12 + [70.0]
        data = _ohlcv_from_close(close)

        signals = TurtleTradingStrategy(entry_period=10, exit_period=5).generate_signals(data)

        assert (signals == 1).any(), "a Donchian-high breakout must produce an entry"
        assert (signals == -1).any(), "a breach of the Donchian low must produce an exit"
        entry_bar = int(np.where(signals.to_numpy() == 1)[0][0])
        assert entry_bar == 12, "the entry must land on the breakout bar"

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

    def test_strong_steady_uptrend_produces_a_long_signal(self):
        """A long, low-volatility uptrend yields strongly positive momentum
        and a low volatility penalty → the composite factor must clear the
        entry threshold and the strategy must go long at least once."""
        close = list(np.linspace(100.0, 200.0, 80))
        data = _ohlcv_from_close(close)

        strategy = MultiFactorStrategy(
            momentum_window=10,
            mean_reversion_window=3,
            volume_window=10,
            volatility_window=10,
            entry_threshold=0.2,
            exit_threshold=0.05,
        )
        signals = strategy.generate_signals(data)

        assert len(signals) == len(data)
        assert set(signals.dropna().unique()).issubset({-1, 0, 1})
        assert (signals == 1).any(), "a strong steady uptrend must trigger a long"

    def test_invalid_parameters(self):
        with pytest.raises(Exception):
            MultiFactorStrategy(entry_threshold=0.1, exit_threshold=0.2)
