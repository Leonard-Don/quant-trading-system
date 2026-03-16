"""
高级交易策略模块
统一使用 BaseStrategy 基类
"""
import pandas as pd
import numpy as np
from typing import Optional

from .strategies import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """均值回归策略"""
    
    def __init__(self, lookback_period: int = 20, entry_threshold: float = 2.0):
        super().__init__(
            name="MeanReversion",
            parameters={
                "lookback_period": lookback_period,
                "entry_threshold": entry_threshold
            }
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)
        
        lookback = self.parameters["lookback_period"]
        z_threshold = self.parameters["entry_threshold"]

        mean = data["close"].rolling(window=lookback).mean()
        std = data["close"].rolling(window=lookback).std()
        z_score = (data["close"] - mean) / std

        signals[z_score < -z_threshold] = 1
        signals[z_score > z_threshold] = -1

        return signals


class MomentumStrategy(BaseStrategy):
    """动量策略"""
    
    def __init__(self, fast_window: int = 10, slow_window: int = 30):
        super().__init__(
            name="Momentum",
            parameters={
                "fast_window": fast_window,
                "slow_window": slow_window
            }
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)

        fast_momentum = data["close"].pct_change(self.parameters["fast_window"])
        slow_momentum = data["close"].pct_change(self.parameters["slow_window"])

        signals[(fast_momentum > 0) & (slow_momentum > 0)] = 1
        signals[(fast_momentum < 0) & (slow_momentum < 0)] = -1

        return signals


class VWAPStrategy(BaseStrategy):
    """VWAP 策略"""
    
    def __init__(self, period: int = 20):
        super().__init__(
            name="VWAP",
            parameters={"period": period}
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)
        window = self.parameters["period"]

        typical_price = (data["high"] + data["low"] + data["close"]) / 3
        vwap = (typical_price * data["volume"]).rolling(
            window=window
        ).sum() / data["volume"].rolling(window=window).sum()

        signals[data["close"] > vwap * 1.01] = 1
        signals[data["close"] < vwap * 0.99] = -1

        return signals


class StochasticOscillator(BaseStrategy):
    """随机振荡器策略"""
    
    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        oversold: float = 20,
        overbought: float = 80,
    ):
        super().__init__(
            name="Stochastic",
            parameters={
                "k_period": k_period,
                "d_period": d_period,
                "oversold": oversold,
                "overbought": overbought
            }
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)
        
        k_period = self.parameters["k_period"]
        d_period = self.parameters["d_period"]
        oversold = self.parameters["oversold"]
        overbought = self.parameters["overbought"]

        low_min = data["low"].rolling(window=k_period).min()
        high_max = data["high"].rolling(window=k_period).max()

        k_percent = 100 * ((data["close"] - low_min) / (high_max - low_min))
        d_percent = k_percent.rolling(window=d_period).mean()

        signals[(k_percent < oversold) & (d_percent < oversold)] = 1
        signals[(k_percent > overbought) & (d_percent > overbought)] = -1

        return signals


class MACDStrategy(BaseStrategy):
    """MACD 策略"""
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(
            name="MACD",
            parameters={
                "fast_period": fast_period,
                "slow_period": slow_period,
                "signal_period": signal_period
            }
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)
        
        fast = self.parameters["fast_period"]
        slow = self.parameters["slow_period"]
        signal = self.parameters["signal_period"]

        exp1 = data["close"].ewm(span=fast, adjust=False).mean()
        exp2 = data["close"].ewm(span=slow, adjust=False).mean()

        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()

        signals[macd > signal_line] = 1
        signals[macd < signal_line] = -1

        return signals


class ATRTrailingStop(BaseStrategy):
    """ATR 移动止损策略"""
    
    def __init__(self, atr_period: int = 14, atr_multiplier: float = 2.0):
        super().__init__(
            name="ATRTrailingStop",
            parameters={
                "atr_period": atr_period,
                "atr_multiplier": atr_multiplier
            }
        )

    def calculate_atr(self, data: pd.DataFrame) -> pd.Series:
        high_low = data["high"] - data["low"]
        high_close = np.abs(data["high"] - data["close"].shift())
        low_close = np.abs(data["low"] - data["close"].shift())

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)

        return true_range.rolling(window=self.parameters["atr_period"]).mean()

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(index=data.index, data=0)
        atr = self.calculate_atr(data)
        multiplier = self.parameters["atr_multiplier"]

        trailing_stop_long = data["close"] - (atr * multiplier)
        trailing_stop_short = data["close"] + (atr * multiplier)

        position = 0
        for i in range(1, len(data)):
            if position == 0:
                if data["close"].iloc[i] > trailing_stop_long.iloc[i]:
                    position = 1
                    signals.iloc[i] = 1
                elif data["close"].iloc[i] < trailing_stop_short.iloc[i]:
                    position = -1
                    signals.iloc[i] = -1
            elif position == 1:
                if data["close"].iloc[i] < trailing_stop_long.iloc[i]:
                    position = 0
                    signals.iloc[i] = -1
            elif position == -1:
                if data["close"].iloc[i] > trailing_stop_short.iloc[i]:
                    position = 0
                    signals.iloc[i] = 1

        return signals


class CombinedStrategy(BaseStrategy):
    """组合策略"""
    
    def __init__(self, strategies: list, weights: Optional[list] = None):
        super().__init__(
            name="Combined",
            parameters={
                "strategy_count": len(strategies),
                "weights": weights or [1 / len(strategies)] * len(strategies)
            }
        )
        self.strategies = strategies
        self.weights = weights or [1 / len(strategies)] * len(strategies)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        all_signals = []

        for strategy in self.strategies:
            signals = strategy.generate_signals(data)
            all_signals.append(signals)

        weighted_signals = pd.DataFrame(all_signals).T
        final_signals = (weighted_signals * self.weights).sum(axis=1)

        signals = pd.Series(index=data.index, data=0)
        signals[final_signals > 0.5] = 1
        signals[final_signals < -0.5] = -1

        return signals


# 向后兼容别名
BaseAdvancedStrategy = BaseStrategy
