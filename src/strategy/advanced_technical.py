"""
高级技术指标策略模块
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple
import logging

# from scipy import stats  # 暂时未使用
# from sklearn.preprocessing import StandardScaler  # 暂时未使用

# from ..core.base import BaseComponent  # 暂时未使用
from .strategies import BaseStrategy

logger = logging.getLogger(__name__)


def _resolve_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV column names to lowercase so strategies work with both
    Yahoo-style (High/Low/Close/Volume) and backtester-style (high/low/close/volume)
    DataFrames."""
    rename_map = {}
    for expected in ("open", "high", "low", "close", "volume"):
        if expected not in data.columns:
            capitalized = expected.capitalize()
            if capitalized in data.columns:
                rename_map[capitalized] = expected
    if rename_map:
        return data.rename(columns=rename_map)
    return data


class AdvancedTechnicalIndicators:
    """高级技术指标计算类"""

    @staticmethod
    def williams_r(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """威廉指标 %R"""
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()

        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        return wr

    @staticmethod
    def stochastic_oscillator(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3,
    ) -> Tuple[pd.Series, pd.Series]:
        """随机振荡器 KD指标"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)
        k_percent = k_percent.fillna(50)

        # %K 平滑
        k_smooth = k_percent.rolling(window=3).mean()

        # %D 是 %K 的移动平均
        d_smooth = k_smooth.rolling(window=d_period).mean()

        return k_smooth, d_smooth

    @staticmethod
    def commodity_channel_index(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20
    ) -> pd.Series:
        """商品通道指数 CCI"""
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mean_deviation = typical_price.rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x)))
        )

        cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
        return cci

    @staticmethod
    def average_true_range(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """平均真实范围 ATR"""
        high_low = high - low
        high_close_prev = np.abs(high - close.shift(1))
        low_close_prev = np.abs(low - close.shift(1))

        true_range = np.maximum(high_low, np.maximum(high_close_prev, low_close_prev))
        atr = true_range.rolling(window=period).mean()

        return atr

    @staticmethod
    def parabolic_sar(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        af_start: float = 0.02,
        af_increment: float = 0.02,
        af_max: float = 0.2,
    ) -> pd.Series:
        """抛物线转向指标 SAR"""
        length = len(close)
        sar = np.zeros(length)
        trend = np.zeros(length)
        af = af_start
        ep = 0.0

        # 初始化
        sar[0] = low.iloc[0]
        trend[0] = 1  # 1 for uptrend, -1 for downtrend

        for i in range(1, length):
            prev_sar = sar[i - 1]
            prev_trend = trend[i - 1]

            if prev_trend == 1:  # 上升趋势
                sar[i] = prev_sar + af * (ep - prev_sar)

                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_increment, af_max)

                if low.iloc[i] <= sar[i]:
                    trend[i] = -1
                    sar[i] = ep
                    af = af_start
                    ep = low.iloc[i]
                else:
                    trend[i] = 1

            else:  # 下降趋势
                sar[i] = prev_sar - af * (prev_sar - ep)

                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_increment, af_max)

                if high.iloc[i] >= sar[i]:
                    trend[i] = 1
                    sar[i] = ep
                    af = af_start
                    ep = high.iloc[i]
                else:
                    trend[i] = -1

        return pd.Series(sar, index=close.index)

    @staticmethod
    def ichimoku_cloud(
        high: pd.Series, low: pd.Series, close: pd.Series
    ) -> Dict[str, pd.Series]:
        """一目均衡表（云图）"""
        # 转换线 (Tenkan-sen): 9期最高最低平均
        tenkan_sen = (high.rolling(9).max() + low.rolling(9).min()) / 2

        # 基准线 (Kijun-sen): 26期最高最低平均
        kijun_sen = (high.rolling(26).max() + low.rolling(26).min()) / 2

        # 先行带A (Senkou Span A): (转换线+基准线)/2，向前移26期
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

        # 先行带B (Senkou Span B): 52期最高最低平均，向前移26期
        senkou_span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

        # 滞后线 (Chikou Span): 收盘价向后移26期
        chikou_span = close.shift(-26)

        return {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_span_a": senkou_span_a,
            "senkou_span_b": senkou_span_b,
            "chikou_span": chikou_span,
        }


class IchimokuStrategy(BaseStrategy):
    """一目均衡表策略"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.indicators = AdvancedTechnicalIndicators()

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        try:
            data = _resolve_ohlcv(data)
            # 计算一目均衡表指标
            ichimoku = self.indicators.ichimoku_cloud(
                data["high"], data["low"], data["close"]
            )

            signals = pd.Series(0, index=data.index)
            close = data["close"]

            # 信号规则
            for i in range(26, len(data)):  # 从第26个数据点开始
                # 多头信号条件
                bullish_conditions = [
                    close.iloc[i] > ichimoku["senkou_span_a"].iloc[i],  # 价格在云上方
                    close.iloc[i] > ichimoku["senkou_span_b"].iloc[i],
                    (
                        ichimoku["tenkan_sen"].iloc[i] > ichimoku["kijun_sen"].iloc[i]
                    ),  # 转换线在基准线上方
                    (
                        ichimoku["chikou_span"].iloc[i] > close.iloc[i - 26]
                    ),  # 滞后线在26期前价格上方
                ]

                # 空头信号条件
                bearish_conditions = [
                    close.iloc[i] < ichimoku["senkou_span_a"].iloc[i],  # 价格在云下方
                    close.iloc[i] < ichimoku["senkou_span_b"].iloc[i],
                    (
                        ichimoku["tenkan_sen"].iloc[i] < ichimoku["kijun_sen"].iloc[i]
                    ),  # 转换线在基准线下方
                    (
                        ichimoku["chikou_span"].iloc[i] < close.iloc[i - 26]
                    ),  # 滞后线在26期前价格下方
                ]

                if all(bullish_conditions):
                    signals.iloc[i] = 1
                elif all(bearish_conditions):
                    signals.iloc[i] = -1

            return signals

        except Exception as e:
            self.logger.error(f"一目均衡表策略信号生成失败: {e}")
            return pd.Series(0, index=data.index)


class StochasticStrategy(BaseStrategy):
    """随机振荡器策略"""

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        oversold: float = 20,
        overbought: float = 80,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.indicators = AdvancedTechnicalIndicators()

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        try:
            data = _resolve_ohlcv(data)
            # 计算随机振荡器
            k, d = self.indicators.stochastic_oscillator(
                data["high"], data["low"], data["close"], self.k_period, self.d_period
            )

            signals = pd.Series(0, index=data.index)

            # 生成信号
            for i in range(1, len(data)):
                # 金叉买入信号：K线从下方穿越D线，且在超卖区域
                if (
                    k.iloc[i] > d.iloc[i]
                    and k.iloc[i - 1] <= d.iloc[i - 1]
                    and k.iloc[i] < self.oversold
                ):
                    signals.iloc[i] = 1

                # 死叉卖出信号：K线从上方跌破D线，且在超买区域
                elif (
                    k.iloc[i] < d.iloc[i]
                    and k.iloc[i - 1] >= d.iloc[i - 1]
                    and k.iloc[i] > self.overbought
                ):
                    signals.iloc[i] = -1

            return signals

        except Exception as e:
            self.logger.error(f"随机振荡器策略信号生成失败: {e}")
            return pd.Series(0, index=data.index)


class CCIStrategy(BaseStrategy):
    """商品通道指数策略"""

    def __init__(
        self,
        period: int = 20,
        oversold: float = -100,
        overbought: float = 100,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.indicators = AdvancedTechnicalIndicators()

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        try:
            data = _resolve_ohlcv(data)
            # 计算CCI指标
            cci = self.indicators.commodity_channel_index(
                data["high"], data["low"], data["close"], self.period
            )

            signals = pd.Series(0, index=data.index)

            # 生成信号
            for i in range(1, len(data)):
                # 从超卖区域向上突破
                if cci.iloc[i] > self.oversold and cci.iloc[i - 1] <= self.oversold:
                    signals.iloc[i] = 1

                # 从超买区域向下突破
                elif (
                    cci.iloc[i] < self.overbought and cci.iloc[i - 1] >= self.overbought
                ):
                    signals.iloc[i] = -1

            return signals

        except Exception as e:
            self.logger.error(f"CCI策略信号生成失败: {e}")
            return pd.Series(0, index=data.index)


class ParabolicSARStrategy(BaseStrategy):
    """抛物线转向策略"""

    def __init__(
        self,
        af_start: float = 0.02,
        af_increment: float = 0.02,
        af_max: float = 0.2,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.af_start = af_start
        self.af_increment = af_increment
        self.af_max = af_max
        self.indicators = AdvancedTechnicalIndicators()

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        try:
            data = _resolve_ohlcv(data)
            # 计算SAR指标
            sar = self.indicators.parabolic_sar(
                data["high"],
                data["low"],
                data["close"],
                self.af_start,
                self.af_increment,
                self.af_max,
            )

            signals = pd.Series(0, index=data.index)
            close = data["close"]

            # 生成信号
            for i in range(1, len(data)):
                # 价格从SAR下方突破到上方：买入信号
                if close.iloc[i] > sar.iloc[i] and close.iloc[i - 1] <= sar.iloc[i - 1]:
                    signals.iloc[i] = 1

                # 价格从SAR上方跌破到下方：卖出信号
                elif (
                    close.iloc[i] < sar.iloc[i] and close.iloc[i - 1] >= sar.iloc[i - 1]
                ):
                    signals.iloc[i] = -1

            return signals

        except Exception as e:
            self.logger.error(f"抛物线转向策略信号生成失败: {e}")
            return pd.Series(0, index=data.index)


class MultiIndicatorStrategy(BaseStrategy):
    """多指标综合策略"""

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2,
        volume_threshold: float = 1.5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volume_threshold = volume_threshold
        self.indicators = AdvancedTechnicalIndicators()

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(
        self, prices: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算MACD"""
        exp1 = prices.ewm(span=self.macd_fast).mean()
        exp2 = prices.ewm(span=self.macd_slow).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=self.macd_signal).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def _calculate_bollinger_bands(
        self, prices: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算布林带"""
        sma = prices.rolling(window=self.bb_period).mean()
        std = prices.rolling(window=self.bb_period).std()
        upper = sma + (std * self.bb_std)
        lower = sma - (std * self.bb_std)
        return upper, sma, lower

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成综合交易信号"""
        try:
            data = _resolve_ohlcv(data)
            close = data["close"]
            volume = data["volume"]

            # 计算各种指标
            rsi = self._calculate_rsi(close, self.rsi_period)
            macd, macd_signal, macd_hist = self._calculate_macd(close)
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(close)

            # 计算成交量移动平均
            volume_ma = volume.rolling(window=20).mean()
            volume_ratio = volume / volume_ma

            signals = pd.Series(0, index=data.index)

            # 多指标综合判断
            for i in range(26, len(data)):  # 确保所有指标都有足够数据
                bullish_score = 0
                bearish_score = 0

                # RSI条件
                if rsi.iloc[i] < self.rsi_oversold:
                    bullish_score += 1
                elif rsi.iloc[i] > self.rsi_overbought:
                    bearish_score += 1

                # MACD条件
                if (
                    macd.iloc[i] > macd_signal.iloc[i]
                    and macd.iloc[i - 1] <= macd_signal.iloc[i - 1]
                ):
                    bullish_score += 2  # MACD金叉权重更高
                elif (
                    macd.iloc[i] < macd_signal.iloc[i]
                    and macd.iloc[i - 1] >= macd_signal.iloc[i - 1]
                ):
                    bearish_score += 2

                # 布林带条件
                if close.iloc[i] < bb_lower.iloc[i]:
                    bullish_score += 1  # 价格触及下轨
                elif close.iloc[i] > bb_upper.iloc[i]:
                    bearish_score += 1  # 价格触及上轨

                # 成交量确认
                volume_confirmation = volume_ratio.iloc[i] > self.volume_threshold

                # 综合判断
                if bullish_score >= 3 and volume_confirmation:
                    signals.iloc[i] = 1
                elif bearish_score >= 3 and volume_confirmation:
                    signals.iloc[i] = -1

            return signals

        except Exception as e:
            self.logger.error(f"多指标综合策略信号生成失败: {e}")
            return pd.Series(0, index=data.index)

    def get_signal_strength(self, data: pd.DataFrame) -> pd.Series:
        """获取信号强度（0-1之间）"""
        try:
            data = _resolve_ohlcv(data)
            close = data["close"]

            # 计算各种指标
            rsi = self._calculate_rsi(close, self.rsi_period)
            macd, macd_signal, _ = self._calculate_macd(close)
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(close)

            strength = pd.Series(0.0, index=data.index)

            for i in range(26, len(data)):
                score = 0
                max_score = 4

                # RSI强度
                if rsi.iloc[i] < 20:
                    score += 1
                elif rsi.iloc[i] < 30:
                    score += 0.5
                elif rsi.iloc[i] > 80:
                    score += 1
                elif rsi.iloc[i] > 70:
                    score += 0.5

                # MACD强度
                if abs(macd.iloc[i] - macd_signal.iloc[i]) > 0.5:
                    score += 1
                elif abs(macd.iloc[i] - macd_signal.iloc[i]) > 0.2:
                    score += 0.5

                # 布林带强度
                bb_width = bb_upper.iloc[i] - bb_lower.iloc[i]
                price_position = (close.iloc[i] - bb_lower.iloc[i]) / bb_width

                if price_position < 0.1 or price_position > 0.9:
                    score += 1
                elif price_position < 0.2 or price_position > 0.8:
                    score += 0.5

                # 趋势强度
                if close.iloc[i] > bb_middle.iloc[i]:
                    score += 0.5
                else:
                    score += 0.5

                strength.iloc[i] = min(score / max_score, 1.0)

            return strength

        except Exception as e:
            self.logger.error(f"计算信号强度失败: {e}")
            return pd.Series(0.0, index=data.index)
