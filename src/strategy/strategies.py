"""
高级交易策略模块
"""

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
