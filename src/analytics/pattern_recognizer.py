"""
形态识别模块
识别K线形态和图表形态
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class PatternRecognizer:
    """
    形态识别器
    识别常见的K线形态和图表形态
    
    Args:
        config: 可选配置字典，支持以下参数：
            - doji_threshold: 十字星实体比例阈值
            - max_patterns: 返回的最大形态数量
            - candlestick_window: K线形态分析窗口
            - chart_pattern_window: 图表形态分析窗口
            - peak_detection_window: 峰值检测窗口
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "doji_threshold": 0.15,           # 十字星实体比例阈值
        "max_patterns": 5,                # 返回的最大形态数量
        "candlestick_window": 30,         # K线形态分析窗口（天）
        "chart_pattern_window": 60,       # 图表形态分析窗口（天）
        "peak_detection_window": {
            "short": 5,                   # 短期峰值检测窗口
            "long": 10                    # 长期峰值检测窗口
        },
        "price_tolerance": 0.05,          # 价格相似度容差（5%）
        "engulfing_ratio": 1.2            # 吞没形态实体比例要求
    }

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化形态识别器
        
        Args:
            config: 自定义配置，将与默认配置合并
        """
        self.config = self._merge_config(config or {})
        self.doji_threshold = self.config["doji_threshold"]
        self.max_patterns = self.config["max_patterns"]
        self.candlestick_window = self.config["candlestick_window"]
        self.chart_pattern_window = self.config["chart_pattern_window"]
        self.peak_detection_window = self.config["peak_detection_window"]
        self.price_tolerance = self.config["price_tolerance"]
        self.engulfing_ratio = self.config["engulfing_ratio"]
    
    def _merge_config(self, custom_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并自定义配置与默认配置
        """
        merged = {}
        for key, default_value in self.DEFAULT_CONFIG.items():
            if key in custom_config:
                if isinstance(default_value, dict):
                    merged[key] = {**default_value, **custom_config[key]}
                else:
                    merged[key] = custom_config[key]
            else:
                merged[key] = default_value.copy() if isinstance(default_value, dict) else default_value
        return merged

    def recognize_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        识别所有形态

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            识别结果
        """
        if df.empty or len(df) < 10:
            return {
                "candlestick_patterns": [],
                "chart_patterns": [],
                "total_patterns": 0
            }

        # 1. K线形态
        candlestick_patterns = self._recognize_candlestick_patterns(df)

        # 2. 图表形态
        chart_patterns = self._recognize_chart_patterns(df)

        return {
            "candlestick_patterns": candlestick_patterns,
            "chart_patterns": chart_patterns,
            "total_patterns": len(candlestick_patterns) + len(chart_patterns)
        }

    def _recognize_candlestick_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        识别K线形态
        """
        patterns = []

        # 只分析最近30根K线
        recent_df = df.tail(30).copy()

        # 遍历最近的K线
        for i in range(len(recent_df) - 3):
            idx = i + 3  # 确保有足够的历史数据

            # 获取当前和前几根K线数据
            current = recent_df.iloc[idx]
            prev1 = recent_df.iloc[idx-1]
            prev2 = recent_df.iloc[idx-2]
            prev3 = recent_df.iloc[idx-3] if idx >= 3 else None

            # 检测各种形态
            pattern = self._check_doji(current)
            if pattern:
                patterns.append({**pattern, "date": current.name})

            pattern = self._check_hammer(current, prev1)
            if pattern:
                patterns.append({**pattern, "date": current.name})

            pattern = self._check_engulfing(current, prev1)
            if pattern:
                patterns.append({**pattern, "date": current.name})

            pattern = self._check_morning_evening_star(current, prev1, prev2)
            if pattern:
                patterns.append({**pattern, "date": current.name})

            pattern = self._check_three_soldiers_crows(current, prev1, prev2)
            if pattern:
                patterns.append({**pattern, "date": current.name})

        # 只返回最近的5个形态
        return patterns[-5:] if len(patterns) > 5 else patterns

    def _check_doji(self, candle: pd.Series) -> Dict[str, Any]:
        """
        检测十字星
        """
        open_price = candle["open"]
        close = candle["close"]
        high = candle["high"]
        low = candle["low"]

        body = abs(close - open_price)
        total_range = high - low

        if total_range == 0:
            return None

        # 实体很小，上下影线较长 (放宽阈值从0.1到0.15)
        if body / total_range < 0.15:
            return {
                "pattern": "doji",
                "name": "十字星",
                "signal": "reversal",
                "reliability": "medium",
                "description": "可能预示趋势反转"
            }

        return None

    def _check_hammer(self, current: pd.Series, prev: pd.Series) -> Dict[str, Any]:
        """
        检测锤子线和上吊线
        """
        open_price = current["open"]
        close = current["close"]
        high = current["high"]
        low = current["low"]

        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        total_range = high - low

        if total_range == 0:
            return None

        # 下影线很长，上影线很短，实体在顶部
        if (lower_shadow > body * 2 and
            upper_shadow < body * 0.3 and
            body / total_range < 0.3):

            # 判断是锤子线还是上吊线
            prev_trend = "up" if prev["close"] > prev["open"] else "down"

            if prev_trend == "down":
                return {
                    "pattern": "hammer",
                    "name": "锤子线",
                    "signal": "bullish_reversal",
                    "reliability": "high",
                    "description": "底部反转信号，看涨"
                }
            else:
                return {
                    "pattern": "hanging_man",
                    "name": "上吊线",
                    "signal": "bearish_reversal",
                    "reliability": "medium",
                    "description": "顶部反转信号，看跌"
                }

        return None

    def _check_engulfing(self, current: pd.Series, prev: pd.Series) -> Dict[str, Any]:
        """
        检测吞没形态
        """
        curr_open = current["open"]
        curr_close = current["close"]
        prev_open = prev["open"]
        prev_close = prev["close"]

        curr_body = abs(curr_close - curr_open)
        prev_body = abs(prev_close - prev_open)

        # 看涨吞没
        if (prev_close < prev_open and  # 前一根是阴线
            curr_close > curr_open and  # 当前是阳线
            curr_open < prev_close and  # 当前开盘价低于前收盘
            curr_close > prev_open and  # 当前收盘价高于前开盘
            curr_body > prev_body * 1.2):  # 当前实体更大
            return {
                "pattern": "bullish_engulfing",
                "name": "看涨吞没",
                "signal": "bullish_reversal",
                "reliability": "high",
                "description": "强烈的底部反转信号"
            }

        # 看跌吞没
        if (prev_close > prev_open and  # 前一根是阳线
            curr_close < curr_open and  # 当前是阴线
            curr_open > prev_close and  # 当前开盘价高于前收盘
            curr_close < prev_open and  # 当前收盘价低于前开盘
            curr_body > prev_body * 1.2):  # 当前实体更大
            return {
                "pattern": "bearish_engulfing",
                "name": "看跌吞没",
                "signal": "bearish_reversal",
                "reliability": "high",
                "description": "强烈的顶部反转信号"
            }

        return None

    def _check_morning_evening_star(
        self,
        candle3: pd.Series,
        candle2: pd.Series,
        candle1: pd.Series
    ) -> Dict[str, Any]:
        """
        检测早晨之星和黄昏之星
        """
        # 早晨之星：
        # 1. 第一根为阴线
        # 2. 第二根为小实体（十字星或小阳小阴）
        # 3. 第三根为阳线，收盘价至少深入第一根实体中部

        c1_body = abs(candle1["close"] - candle1["open"])
        c2_body = abs(candle2["close"] - candle2["open"])
        c3_body = abs(candle3["close"] - candle3["open"])

        c1_range = candle1["high"] - candle1["low"]
        c3_range = candle3["high"] - candle3["low"]

        # 早晨之星
        if (candle1["close"] < candle1["open"] and  # 第一根阴线
            c2_body < c1_body * 0.3 and  # 第二根小实体
            candle3["close"] > candle3["open"] and  # 第三根阳线
            candle3["close"] > (candle1["open"] + candle1["close"]) / 2):  # 收在第一根中部以上
            return {
                "pattern": "morning_star",
                "name": "早晨之星",
                "signal": "bullish_reversal",
                "reliability": "very_high",
                "description": "强烈的底部反转信号，三K线组合"
            }

        # 黄昏之星
        if (candle1["close"] > candle1["open"] and  # 第一根阳线
            c2_body < c1_body * 0.3 and  # 第二根小实体
            candle3["close"] < candle3["open"] and  # 第三根阴线
            candle3["close"] < (candle1["open"] + candle1["close"]) / 2):  # 收在第一根中部以下
            return {
                "pattern": "evening_star",
                "name": "黄昏之星",
                "signal": "bearish_reversal",
                "reliability": "very_high",
                "description": "强烈的顶部反转信号，三K线组合"
            }

        return None

    def _check_three_soldiers_crows(
        self,
        candle3: pd.Series,
        candle2: pd.Series,
        candle1: pd.Series
    ) -> Dict[str, Any]:
        """
        检测红三兵和三只乌鸦
        """
        # 红三兵：连续三根阳线，依次收高
        if (candle1["close"] > candle1["open"] and
            candle2["close"] > candle2["open"] and
            candle3["close"] > candle3["open"] and
            candle2["close"] > candle1["close"] and
            candle3["close"] > candle2["close"]):
            return {
                "pattern": "three_white_soldiers",
                "name": "红三兵",
                "signal": "bullish_continuation",
                "reliability": "high",
                "description": "强烈的上涨延续信号"
            }

        # 三只乌鸦：连续三根阴线，依次收低
        if (candle1["close"] < candle1["open"] and
            candle2["close"] < candle2["open"] and
            candle3["close"] < candle3["open"] and
            candle2["close"] < candle1["close"] and
            candle3["close"] < candle2["close"]):
            return {
                "pattern": "three_black_crows",
                "name": "三只乌鸦",
                "signal": "bearish_continuation",
                "reliability": "high",
                "description": "强烈的下跌延续信号"
            }

        return None

    def _recognize_chart_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        识别图表形态
        """
        patterns = []

        if len(df) < 20:
            return patterns

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 1. 检测双顶/双底
        pattern = self._check_double_top_bottom(close, high, low)
        if pattern:
            patterns.append(pattern)

        # 2. 检测头肩顶/头肩底
        pattern = self._check_head_shoulders(close, high, low)
        if pattern:
            patterns.append(pattern)

        # 3. 检测三角形态
        pattern = self._check_triangle(close, high, low)
        if pattern:
            patterns.append(pattern)

        # 4. 检测旗形
        pattern = self._check_flag(close, high, low)
        if pattern:
            patterns.append(pattern)

        return patterns

    def _check_double_top_bottom(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series
    ) -> Dict[str, Any]:
        """
        检测双顶和双底
        """
        # 使用最近60天数据
        # 使用最近60天数据
        if len(close) < 60:
            return None

        recent_close = close.tail(60)
        recent_high = high.tail(60)
        recent_low = low.tail(60)
        offset = len(close) - 60

        # 寻找两个高点（双顶）
        peaks = []
        for i in range(5, len(recent_high) - 5):
            if (recent_high.iloc[i] == recent_high.iloc[i-5:i+6].max()):
                peaks.append((i, recent_high.iloc[i]))

        if len(peaks) >= 2:
            # 检查最后两个高点是否接近
            last_two_peaks = peaks[-2:]
            peak1_idx, peak1_val = last_two_peaks[0]
            peak2_idx, peak2_val = last_two_peaks[1]

            if abs(peak1_val - peak2_val) / peak1_val < 0.05:  # 价格差异小于5% (从3%放宽)
                # 寻找两顶之间的低点（颈线）
                trough_val = low.iloc[offset + peak1_idx : offset + peak2_idx].min()
                trough_idx = low.iloc[offset + peak1_idx : offset + peak2_idx].argmin() + peak1_idx
                
                return {
                    "pattern": "double_top",
                    "name": "双顶",
                    "signal": "bearish_reversal",
                    "reliability": "high",
                    "description": "M型头部，看跌反转形态",
                    "points": [
                        {"date": close.index[offset + peak1_idx].strftime('%Y-%m-%d'), "price": peak1_val, "type": "peak1"},
                        {"date": close.index[offset + trough_idx].strftime('%Y-%m-%d'), "price": trough_val, "type": "neckline"},
                        {"date": close.index[offset + peak2_idx].strftime('%Y-%m-%d'), "price": peak2_val, "type": "peak2"}
                    ]
                }

        # 寻找两个低点（双底）
        troughs = []
        for i in range(5, len(recent_low) - 5):
            if (recent_low.iloc[i] == recent_low.iloc[i-5:i+6].min()):
                troughs.append((i, recent_low.iloc[i]))

        if len(troughs) >= 2:
            last_two_troughs = troughs[-2:]
            trough1_idx, trough1_val = last_two_troughs[0]
            trough2_idx, trough2_val = last_two_troughs[1]

            if abs(trough1_val - trough2_val) / trough1_val < 0.05:  # 从3%放宽到5%
                # 寻找两底之间的高点（颈线）
                peak_val = high.iloc[offset + trough1_idx : offset + trough2_idx].max()
                peak_idx = high.iloc[offset + trough1_idx : offset + trough2_idx].argmax() + trough1_idx
                
                return {
                    "pattern": "double_bottom",
                    "name": "双底",
                    "signal": "bullish_reversal",
                    "reliability": "high",
                    "description": "W型底部，看涨反转形态",
                    "points": [
                        {"date": close.index[offset + trough1_idx].strftime('%Y-%m-%d'), "price": trough1_val, "type": "trough1"},
                        {"date": close.index[offset + peak_idx].strftime('%Y-%m-%d'), "price": peak_val, "type": "neckline"},
                        {"date": close.index[offset + trough2_idx].strftime('%Y-%m-%d'), "price": trough2_val, "type": "trough2"}
                    ]
                }

        return None

    def _check_head_shoulders(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series
    ) -> Dict[str, Any]:
        """
        检测头肩顶和头肩底
        """
        # 简化版本，仅检测基本形态
        if len(close) < 60:
            return None

        recent_high = high.tail(60)
        recent_low = low.tail(60)
        offset = len(close) - 60

        # 寻找三个高点
        peaks = []
        for i in range(10, len(recent_high) - 10):
            if (recent_high.iloc[i] == recent_high.iloc[i-10:i+11].max()):
                peaks.append((i, recent_high.iloc[i]))

        # 头肩顶：中间高点最高，两边较低且大致相等
        if len(peaks) >= 3:
            last_three = peaks[-3:]
            left_idx, left_shoulder = last_three[0]
            head_idx, head = last_three[1]
            right_idx, right_shoulder = last_three[2]

            if (head > left_shoulder and
                head > right_shoulder and
                abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                return {
                    "pattern": "head_shoulders_top",
                    "name": "头肩顶",
                    "signal": "bearish_reversal",
                    "reliability": "very_high",
                    "description": "强烈的顶部反转形态",
                    "points": [
                        {"date": close.index[offset + left_idx].strftime('%Y-%m-%d'), "price": left_shoulder, "type": "left_shoulder"},
                        {"date": close.index[offset + head_idx].strftime('%Y-%m-%d'), "price": head, "type": "head"},
                        {"date": close.index[offset + right_idx].strftime('%Y-%m-%d'), "price": right_shoulder, "type": "right_shoulder"}
                    ]
                }

        # 寻找三个低点（头肩底）
        troughs = []
        for i in range(10, len(recent_low) - 10):
            if (recent_low.iloc[i] == recent_low.iloc[i-10:i+11].min()):
                troughs.append((i, recent_low.iloc[i]))

        if len(troughs) >= 3:
            last_three = troughs[-3:]
            left_idx, left_shoulder = last_three[0]
            head_idx, head = last_three[1]
            right_idx, right_shoulder = last_three[2]

            if (head < left_shoulder and
                head < right_shoulder and
                abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                return {
                    "pattern": "head_shoulders_bottom",
                    "name": "头肩底",
                    "signal": "bullish_reversal",
                    "reliability": "very_high",
                    "description": "强烈的底部反转形态",
                    "points": [
                        {"date": close.index[offset + left_idx].strftime('%Y-%m-%d'), "price": left_shoulder, "type": "left_shoulder"},
                        {"date": close.index[offset + head_idx].strftime('%Y-%m-%d'), "price": head, "type": "head"},
                        {"date": close.index[offset + right_idx].strftime('%Y-%m-%d'), "price": right_shoulder, "type": "right_shoulder"}
                    ]
                }

        return None

    def _check_triangle(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series
    ) -> Dict[str, Any]:
        """
        检测三角形态（上升、下降、对称三角形）
        """
        if len(close) < 30:
            return None

        recent_high = high.tail(30)
        recent_low = low.tail(30)

        # 计算高点和低点的趋势
        high_trend = np.polyfit(range(len(recent_high)), recent_high, 1)[0]
        low_trend = np.polyfit(range(len(recent_low)), recent_low, 1)[0]

        # 上升三角形：高点水平，低点上升 (放宽阈值)
        if abs(high_trend) < 0.02 and low_trend > 0.03:
            return {
                "pattern": "ascending_triangle",
                "name": "上升三角形",
                "signal": "bullish_continuation",
                "reliability": "medium",
                "description": "看涨持续形态，通常向上突破"
            }

        # 下降三角形：低点水平，高点下降 (放宽阈值)
        if abs(low_trend) < 0.02 and high_trend < -0.03:
            return {
                "pattern": "descending_triangle",
                "name": "下降三角形",
                "signal": "bearish_continuation",
                "reliability": "medium",
                "description": "看跌持续形态，通常向下突破"
            }

        # 对称三角形：高点下降，低点上升 (放宽阈值)
        if high_trend < -0.03 and low_trend > 0.03:
            return {
                "pattern": "symmetrical_triangle",
                "name": "对称三角形",
                "signal": "consolidation",
                "reliability": "medium",
                "description": "整理形态，等待突破方向"
            }

        return None

    def _check_flag(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series
    ) -> Dict[str, Any]:
        """
        检测旗形（上升旗形、下降旗形）
        """
        if len(close) < 30:
            return None

        # 检查前期趋势
        early_trend = (close.iloc[-30] - close.iloc[-20]) / close.iloc[-30]

        # 检查近期整理
        recent_range = (high.tail(10).max() - low.tail(10).min()) / close.iloc[-10]

        # 上升旗形：强势上涨后小幅回调整理
        if early_trend > 0.1 and recent_range < 0.05:
            return {
                "pattern": "bull_flag",
                "name": "上升旗形",
                "signal": "bullish_continuation",
                "reliability": "high",
                "description": "强势上涨后的整理，看涨延续"
            }

        # 下降旗形：强势下跌后小幅反弹整理
        if early_trend < -0.1 and recent_range < 0.05:
            return {
                "pattern": "bear_flag",
                "name": "下降旗形",
                "signal": "bearish_continuation",
                "reliability": "high",
                "description": "强势下跌后的整理，看跌延续"
            }

        return None
