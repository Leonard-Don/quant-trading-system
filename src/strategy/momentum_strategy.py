"""
增强的动量策略模块
"""

import pandas as pd
import numpy as np

# from typing import Dict  # 暂时未使用
import logging
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression

from .strategies import BaseStrategy

logger = logging.getLogger(__name__)


class EnhancedMomentumStrategy(BaseStrategy):
    """增强的动量策略"""

    def __init__(
        self,
        lookback_period: int = 20,
        momentum_threshold: float = 0.02,
        use_regression: bool = True,
        volatility_adjustment: bool = True,
    ):
        super().__init__(
            name="Enhanced_Momentum",
            parameters={
                "lookback_period": lookback_period,
                "momentum_threshold": momentum_threshold,
                "use_regression": use_regression,
                "volatility_adjustment": volatility_adjustment,
            },
        )
        self.scaler = StandardScaler()

    def calculate_momentum_score(self, data: pd.DataFrame) -> pd.Series:
        """计算动量分数"""
        lookback = self.parameters["lookback_period"]

        # 价格动量
        price_momentum = data["close"].pct_change(lookback)

        # 成交量动量
        volume_momentum = data["volume"].pct_change(lookback)

        # 波动率调整
        if self.parameters["volatility_adjustment"]:
            volatility = data["close"].pct_change().rolling(lookback).std()
            price_momentum = price_momentum / volatility

        # 线性回归趋势
        if self.parameters["use_regression"]:
            trend_strength = self._calculate_trend_strength(data, lookback)
            momentum_score = (
                price_momentum + volume_momentum * 0.3 + trend_strength * 0.5
            ) / 1.8
        else:
            momentum_score = (price_momentum + volume_momentum * 0.3) / 1.3

        return momentum_score.fillna(0)

    def _calculate_trend_strength(self, data: pd.DataFrame, lookback: int) -> pd.Series:
        """计算趋势强度"""
        trend_strength = pd.Series(index=data.index, dtype=float)

        for i in range(lookback, len(data)):
            y = data["close"].iloc[i - lookback : i].values
            x = np.arange(len(y)).reshape(-1, 1)

            try:
                model = LinearRegression()
                model.fit(x, y)
                slope = model.coef_[0]
                r_squared = model.score(x, y)
                trend_strength.iloc[i] = slope * r_squared
            except (ValueError, IndexError):
                trend_strength.iloc[i] = 0

        return trend_strength

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        momentum_score = self.calculate_momentum_score(data)
        threshold = self.parameters["momentum_threshold"]

        signals = pd.Series(index=data.index, data=0)

        # 生成信号
        signals[momentum_score > threshold] = 1  # 买入信号
        signals[momentum_score < -threshold] = -1  # 卖出信号

        # 过滤信号，避免频繁交易
        signals = self._filter_signals(signals)

        return signals

    def _filter_signals(
        self, signals: pd.Series, min_hold_periods: int = 5
    ) -> pd.Series:
        """过滤信号，避免频繁交易"""
        filtered_signals = signals.copy()
        last_signal = 0
        last_signal_date = None

        for i, (date, signal) in enumerate(signals.items()):
            if signal != 0 and signal != last_signal:
                if last_signal_date is not None:
                    # 检查是否满足最小持仓期
                    periods_since_last = i - signals.index.get_loc(last_signal_date)
                    if periods_since_last < min_hold_periods:
                        filtered_signals[date] = 0
                        continue

                last_signal = signal
                last_signal_date = date
            elif signal == 0:
                filtered_signals[date] = 0

        return filtered_signals


class PairsTradingStrategy(BaseStrategy):
    """配对交易策略"""

    def __init__(
        self,
        lookback_period: int = 30,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        cointegration_test: bool = True,
    ):
        super().__init__(
            name="Pairs_Trading",
            parameters={
                "lookback_period": lookback_period,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "cointegration_test": cointegration_test,
            },
        )

    def calculate_spread(self, price1: pd.Series, price2: pd.Series) -> pd.Series:
        """计算价差"""
        # 使用线性回归计算对冲比率
        model = LinearRegression()
        model.fit(price2.values.reshape(-1, 1), price1.values)
        hedge_ratio = model.coef_[0]

        spread = price1 - hedge_ratio * price2
        return spread

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成配对交易信号"""
        # 注意：这里假设data包含两个价格序列
        # 实际使用时需要传入两只股票的数据

        signals = pd.Series(index=data.index, data=0)

        # 这是一个简化版本，实际配对交易需要两只股票的数据
        price = data["close"]
        benchmark = price.rolling(self.parameters["lookback_period"]).mean()
        spread = price - benchmark

        # 计算Z分数
        spread_mean = spread.rolling(self.parameters["lookback_period"]).mean()
        spread_std = spread.rolling(self.parameters["lookback_period"]).std()
        z_score = (spread - spread_mean) / spread_std

        # 生成信号
        entry_threshold = self.parameters["entry_threshold"]
        exit_threshold = self.parameters["exit_threshold"]

        signals[z_score > entry_threshold] = -1  # 价差过高，做空价差
        signals[z_score < -entry_threshold] = 1  # 价差过低，做多价差
        signals[abs(z_score) < exit_threshold] = 0  # 价差回归，平仓

        return signals
