"""
高级交易策略模块
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import warnings


from ..utils.performance import timing_decorator

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Base class for all trading strategies"""

    def __init__(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self.name = name
        self.parameters = parameters or {}
        self.signals = pd.Series()

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Series with signals (1: buy, -1: sell, 0: hold)
        """
        pass

    def get_positions(self, signals: pd.Series) -> pd.Series:
        """Convert signals to positions"""
        return signals.fillna(0)


class MovingAverageCrossover(BaseStrategy):
    """Simple Moving Average Crossover Strategy"""

    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        if fast_period >= slow_period:
            raise ValueError("Fast period must be less than slow period")
        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("Periods must be positive")

        super().__init__(
            name="MA_Crossover",
            parameters={"fast_period": fast_period, "slow_period": slow_period},
        )

    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals based on MA crossover"""
        fast_ma = data["close"].rolling(window=self.parameters["fast_period"]).mean()
        slow_ma = data["close"].rolling(window=self.parameters["slow_period"]).mean()

        signals = pd.Series(index=data.index, data=0)

        # Buy signal when fast MA crosses above slow MA
        signals[fast_ma > slow_ma] = 1
        # Sell signal when fast MA crosses below slow MA
        signals[fast_ma < slow_ma] = -1

        # Only keep actual crossover points
        signals = signals.diff()
        signals[signals > 0] = 1
        signals[signals < 0] = -1
        signals[(signals != 1) & (signals != -1)] = 0

        self.signals = signals
        return signals


class RSIStrategy(BaseStrategy):
    """RSI (Relative Strength Index) Strategy"""

    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        super().__init__(
            name="RSI",
            parameters={
                "period": period,
                "oversold": oversold,
                "overbought": overbought,
            },
        )

    def calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (
            (delta.where(delta > 0, 0)).rolling(window=self.parameters["period"]).mean()
        )
        loss = (
            (-delta.where(delta < 0, 0))
            .rolling(window=self.parameters["period"])
            .mean()
        )

        # 防止零除错误: 当loss为0时,使用极小值替代
        # 这样RSI会接近100,表示强势上涨
        loss = loss.replace(0, 1e-10)

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals based on RSI"""
        rsi = self.calculate_rsi(data["close"])

        signals = pd.Series(index=data.index, data=0)

        # Buy when RSI is oversold
        signals[rsi < self.parameters["oversold"]] = 1
        # Sell when RSI is overbought
        signals[rsi > self.parameters["overbought"]] = -1

        self.signals = signals
        return signals


class BollingerBands(BaseStrategy):
    """Bollinger Bands Strategy"""

    def __init__(self, period: int = 20, num_std: float = 2):
        super().__init__(
            name="BollingerBands", parameters={"period": period, "num_std": num_std}
        )

    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals based on Bollinger Bands"""
        close = data["close"]

        # Calculate Bollinger Bands
        sma = close.rolling(window=self.parameters["period"]).mean()
        std = close.rolling(window=self.parameters["period"]).std()

        upper_band = sma + (std * self.parameters["num_std"])
        lower_band = sma - (std * self.parameters["num_std"])

        signals = pd.Series(index=data.index, data=0)

        # Buy when price touches lower band
        signals[close <= lower_band] = 1
        # Sell when price touches upper band
        signals[close >= upper_band] = -1

        self.signals = signals
        return signals


class BuyAndHold(BaseStrategy):
    """Simple Buy and Hold Strategy"""

    def __init__(self):
        super().__init__(name="BuyAndHold")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals for buy and hold"""
        signals = pd.Series(index=data.index, data=0)
        signals.iloc[0] = 1  # Buy at the beginning

        self.signals = signals
        return signals


class TurtleTradingStrategy(BaseStrategy):
    """Donchian breakout strategy inspired by the Turtle Trading rules."""

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        if entry_period <= 1 or exit_period <= 1:
            raise ValueError("Entry and exit periods must be greater than 1")
        if entry_period <= exit_period:
            raise ValueError("Entry period must be greater than exit period")

        super().__init__(
            name="TurtleTrading",
            parameters={"entry_period": entry_period, "exit_period": exit_period},
        )

    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        high_series = data["high"] if "high" in data.columns else data["close"]
        low_series = data["low"] if "low" in data.columns else data["close"]
        close_series = data["close"]

        entry_high = high_series.rolling(self.parameters["entry_period"]).max().shift(1)
        exit_low = low_series.rolling(self.parameters["exit_period"]).min().shift(1)

        desired_position = pd.Series(index=data.index, data=np.nan, dtype="float64")
        desired_position[close_series > entry_high] = 1.0
        desired_position[close_series < exit_low] = 0.0
        desired_position = desired_position.ffill().fillna(0.0)

        signals = desired_position.diff().fillna(desired_position)
        signals[signals > 0] = 1
        signals[signals < 0] = -1
        signals[(signals != 1) & (signals != -1)] = 0

        self.signals = signals.astype(int)
        return self.signals


class MultiFactorStrategy(BaseStrategy):
    """Single-asset composite factor timing strategy.

    Combines medium-term momentum, short-term mean reversion, volume impulse
    and volatility penalty into a single factor score.  The score is then
    thresholded into long/flat signals.
    """

    def __init__(
        self,
        momentum_window: int = 20,
        mean_reversion_window: int = 5,
        volume_window: int = 20,
        volatility_window: int = 20,
        entry_threshold: float = 0.4,
        exit_threshold: float = 0.1,
    ):
        if min(momentum_window, mean_reversion_window, volume_window, volatility_window) <= 1:
            raise ValueError("All factor windows must be greater than 1")
        if exit_threshold >= entry_threshold:
            raise ValueError("Exit threshold must be smaller than entry threshold")

        super().__init__(
            name="MultiFactor",
            parameters={
                "momentum_window": momentum_window,
                "mean_reversion_window": mean_reversion_window,
                "volume_window": volume_window,
                "volatility_window": volatility_window,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
            },
        )

    @staticmethod
    def _zscore(series: pd.Series, window: int) -> pd.Series:
        rolling_mean = series.rolling(window).mean()
        rolling_std = series.rolling(window).std().replace(0, np.nan)
        return ((series - rolling_mean) / rolling_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = pd.to_numeric(data["close"], errors="coerce")
        volume = pd.to_numeric(data.get("volume", pd.Series(index=data.index, data=1.0)), errors="coerce").fillna(1.0)

        momentum = close.pct_change(self.parameters["momentum_window"])
        mean_reversion = -close.pct_change(self.parameters["mean_reversion_window"])
        volume_impulse = volume / volume.rolling(self.parameters["volume_window"]).mean() - 1
        realized_vol = close.pct_change().rolling(self.parameters["volatility_window"]).std()

        factor_score = (
            0.45 * self._zscore(momentum, self.parameters["momentum_window"])
            + 0.25 * self._zscore(mean_reversion, self.parameters["mean_reversion_window"] + 3)
            + 0.20 * self._zscore(volume_impulse, self.parameters["volume_window"])
            - 0.10 * self._zscore(realized_vol, self.parameters["volatility_window"])
        )

        desired_position = pd.Series(index=data.index, data=np.nan, dtype="float64")
        desired_position[factor_score >= self.parameters["entry_threshold"]] = 1.0
        desired_position[factor_score <= -self.parameters["entry_threshold"]] = 0.0
        desired_position[abs(factor_score) <= self.parameters["exit_threshold"]] = 0.0
        desired_position = desired_position.ffill().fillna(0.0)

        signals = desired_position.diff().fillna(desired_position)
        signals[signals > 0] = 1
        signals[signals < 0] = -1
        signals[(signals != 1) & (signals != -1)] = 0

        self.signals = signals.astype(int)
        return self.signals
