
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
import logging


logger = logging.getLogger(__name__)

class TrendAnalyzer:
    """
    增强版趋势分析器
    负责全面分析股票数据的趋势、支撑阻力位、技术评分和多时间周期分析
    """

    def __init__(self):
        self.indicators = {}

    def analyze_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        综合分析入口 - 增强版
        """
        # 降低最小数据要求以支持月线等长周期数据
        if data.empty or len(data) < 20:
            return {
                "trend": "unknown",
                "score": 0,
                "strength": 0,
                "support_levels": [],
                "resistance_levels": [],
                "indicators": {},
                "multi_timeframe": {},
                "momentum": {},
                "volatility": {}
            }

        # 确保数据按时间排序
        df = data.sort_index()
        
        # 标准化列名为小写，提高兼容性
        df.columns = df.columns.str.lower()
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # 1. 趋势方向和强度
        trend_direction, trend_details = self._calculate_trend_direction(close)
        trend_strength = self._calculate_trend_strength(df)

        # 2. 支撑/阻力位
        support_levels, resistance_levels = self._identify_support_resistance(df)

        # 3. 技术评分
        score, indicator_values = self._calculate_technical_score(df)

        # 4. 多时间周期分析
        multi_timeframe = self._multi_timeframe_analysis(close)

        # 5. 动量分析
        momentum = self._analyze_momentum(df)

        # 6. 波动率分析
        volatility = self._analyze_volatility(df)

        # 7. 买卖信号强度
        signal_strength = self._calculate_signal_strength(df, trend_direction)

        # 8. 斐波那契回撤
        fibonacci_levels = self._calculate_fibonacci_levels(df)

        return {
            "trend": trend_direction,
            "trend_details": trend_details,
            "trend_strength": trend_strength,
            "score": score,
            "signal_strength": signal_strength,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "indicators": indicator_values,
            "multi_timeframe": multi_timeframe,
            "momentum": momentum,
            "volatility": volatility,
            "fibonacci_levels": fibonacci_levels
        }

    def _calculate_trend_direction(self, close: pd.Series) -> Tuple[str, Dict[str, Any]]:
        """
        基于移动均线判断趋势
        """
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]
        sma200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
        current_price = close.iloc[-1]
        
        details = {
            "current_price": float(current_price),
            "sma20": float(sma20) if not pd.isna(sma20) else None,
            "sma50": float(sma50) if not pd.isna(sma50) else None,
            "sma200": float(sma200) if sma200 and not pd.isna(sma200) else None
        }

        # 简单的趋势判断逻辑
        if sma200:
            if current_price > sma20 and current_price > sma50 and current_price > sma200:
                return "strong_bullish", details
            elif current_price < sma20 and current_price < sma50 and current_price < sma200:
                return "strong_bearish", details
        
        if current_price > sma50:
            return "bullish", details
        elif current_price < sma50:
            return "bearish", details
            
        return "neutral", details

    def _identify_support_resistance(self, df: pd.DataFrame, window: int = 20) -> Tuple[List[float], List[float]]:
        """
        识别支撑和阻力位
        """
        highs = df["high"]
        lows = df["low"]
        
        support_levels = []
        resistance_levels = []
        
        # 简单的局部极值法
        for i in range(window, len(df) - window):
            is_support = lows.iloc[i] == lows.iloc[i-window:i+window+1].min()
            is_resistance = highs.iloc[i] == highs.iloc[i-window:i+window+1].max()
            
            if is_support:
                support_levels.append(float(lows.iloc[i]))
            if is_resistance:
                resistance_levels.append(float(highs.iloc[i]))
                
        # 过滤相近的水平 (简单的去重)
        support_levels = sorted(list(set([round(x, 2) for x in support_levels])))
        resistance_levels = sorted(list(set([round(x, 2) for x in resistance_levels])))
        
        # 只返回最近的几个关键位
        current_price = df["close"].iloc[-1]
        
        # 筛选接近当前价格的水平
        relevant_supports = [s for s in support_levels if s < current_price][-3:] # 最近的3个支撑
        relevant_resistances = [r for r in resistance_levels if r > current_price][:3] # 最近的3个阻力
        
        return relevant_supports, relevant_resistances

    def _calculate_technical_score(self, df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
        """
        计算技术评分 (0-100)
        整合多个技术指标给出综合评分
        """
        score = 50.0 # 初始中性分
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        
        # 1. RSI (0-100)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        if current_rsi < 30: score += 15 # 超卖，看涨
        elif current_rsi > 70: score -= 15 # 超买，看跌
        elif current_rsi > 50: score += 5
        else: score -= 5
        
        # 2. MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_histogram = macd - signal
        
        if macd.iloc[-1] > signal.iloc[-1]: score += 10
        else: score -= 10
        
        # 3. 均线排列
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]
        
        if sma20 > sma50: score += 10
        else: score -= 10
        
        # 4. CCI (商品通道指数)
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=20).mean()
        mean_deviation = typical_price.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
        current_cci = cci.iloc[-1]
        
        if current_cci < -100: score += 10  # 超卖
        elif current_cci > 100: score -= 10  # 超买
        elif current_cci > 0: score += 3
        else: score -= 3
        
        # 5. ADX (平均趋向指数)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        high_diff = high.diff()
        low_diff = -low.diff()
        pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        pos_di = 100 * (pos_dm.rolling(window=14).mean() / atr)
        neg_di = 100 * (neg_dm.rolling(window=14).mean() / atr)
        dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di)
        adx = dx.rolling(window=14).mean()
        current_adx = adx.iloc[-1]
        current_pos_di = pos_di.iloc[-1]
        current_neg_di = neg_di.iloc[-1]
        
        # ADX > 25 表示趋势明确，趋势方向由DI决定
        if not pd.isna(current_adx) and current_adx > 25:
            if current_pos_di > current_neg_di: score += 5
            else: score -= 5
        
        # 6. Stochastic (随机指标)
        low_14 = low.rolling(window=14).min()
        high_14 = high.rolling(window=14).max()
        stoch_k = 100 * (close - low_14) / (high_14 - low_14)
        stoch_d = stoch_k.rolling(window=3).mean()
        current_stoch_k = stoch_k.iloc[-1]
        current_stoch_d = stoch_d.iloc[-1]
        
        if current_stoch_k < 20: score += 8  # 超卖
        elif current_stoch_k > 80: score -= 8  # 超买
        
        # 7. Williams %R
        williams_r = -100 * (high_14 - close) / (high_14 - low_14)
        current_williams = williams_r.iloc[-1]
        
        if current_williams < -80: score += 5  # 超卖
        elif current_williams > -20: score -= 5  # 超买
        
        # 8. OBV 趋势
        obv = (np.sign(close.diff()) * df["volume"]).fillna(0).cumsum()
        obv_sma = obv.rolling(window=20).mean()
        if obv.iloc[-1] > obv_sma.iloc[-1]: score += 5
        else: score -= 5
        
        # 限制分数范围
        score = max(0, min(100, score))
        
        indicators = {
            "rsi": round(float(current_rsi) if not pd.isna(current_rsi) else 50, 2),
            "macd": round(float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0, 4),
            "macd_signal": round(float(signal.iloc[-1]) if not pd.isna(signal.iloc[-1]) else 0, 4),
            "macd_histogram": round(float(macd_histogram.iloc[-1]) if not pd.isna(macd_histogram.iloc[-1]) else 0, 4),
            "cci": round(float(current_cci) if not pd.isna(current_cci) else 0, 2),
            "adx": round(float(current_adx) if not pd.isna(current_adx) else 0, 2),
            "plus_di": round(float(current_pos_di) if not pd.isna(current_pos_di) else 0, 2),
            "minus_di": round(float(current_neg_di) if not pd.isna(current_neg_di) else 0, 2),
            "stoch_k": round(float(current_stoch_k) if not pd.isna(current_stoch_k) else 50, 2),
            "stoch_d": round(float(current_stoch_d) if not pd.isna(current_stoch_d) else 50, 2),
            "williams_r": round(float(current_williams) if not pd.isna(current_williams) else -50, 2),
            "sma20": round(float(sma20) if not pd.isna(sma20) else 0, 2),
            "sma50": round(float(sma50) if not pd.isna(sma50) else 0, 2),
        }

        return round(score, 1), indicators

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """
        计算趋势强度 (0-100)
        使用ADX、价格动量和均线斜率综合判断
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        strength = 0.0

        # 1. ADX (平均趋向指数) - 衡量趋势强度
        # 简化的ADX计算
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()

        # +DI 和 -DI
        high_diff = high.diff()
        low_diff = -low.diff()

        pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)

        pos_di = 100 * (pos_dm.rolling(window=14).mean() / atr)
        neg_di = 100 * (neg_dm.rolling(window=14).mean() / atr)

        dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di)
        adx = dx.rolling(window=14).mean().iloc[-1]

        if not pd.isna(adx):
            if adx > 50: strength += 40  # 强趋势
            elif adx > 25: strength += 30  # 中等趋势
            elif adx > 20: strength += 20  # 弱趋势
            else: strength += 10  # 无趋势

        # 2. 价格动量
        momentum = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
        if abs(momentum) > 10: strength += 30
        elif abs(momentum) > 5: strength += 20
        else: strength += 10

        # 3. 均线排列
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]

        if len(close) >= 200:
            sma200 = close.rolling(window=200).mean().iloc[-1]
            if sma20 > sma50 > sma200 or sma20 < sma50 < sma200:
                strength += 30  # 完美排列
            elif sma20 > sma50 or sma20 < sma50:
                strength += 15  # 部分排列
        else:
            if sma20 > sma50 or sma20 < sma50:
                strength += 20

        return min(100, round(strength, 1))

    def _multi_timeframe_analysis(self, close: pd.Series) -> Dict[str, str]:
        """
        多时间周期分析
        根据数据长度动态调整分析周期，支持月线、周线等长周期数据
        """
        timeframes = {}
        data_len = len(close)
        
        # 根据数据长度动态设置周期
        # 对于月线数据（通常只有12-60个点），使用更小的周期
        if data_len >= 60:
            # 标准日线数据
            short_period, mid_period, long_period = 5, 20, 60
            short_label, mid_label, long_label = "5天", "20天", "60天"
        elif data_len >= 24:
            # 周线或较少的日线数据
            short_period = min(3, data_len - 1)
            mid_period = min(8, data_len - 1)
            long_period = min(20, data_len - 1)
            short_label, mid_label, long_label = "3周期", "8周期", "20周期"
        elif data_len >= 6:
            # 月线数据 - 使用更小的周期
            short_period = min(2, data_len - 1)
            mid_period = min(4, data_len - 1)
            long_period = min(data_len - 1, data_len - 1)
            short_label = "2周期"
            mid_label = "4周期"
            long_label = f"{long_period}周期"
        else:
            # 数据太少，无法进行多周期分析
            return timeframes

        # 短期
        if data_len > short_period:
            short_trend = "上涨" if close.iloc[-1] > close.iloc[-short_period-1] else "下跌"
            short_change = (close.iloc[-1] - close.iloc[-short_period-1]) / close.iloc[-short_period-1] * 100
            timeframes["short"] = {
                "period": short_label,
                "trend": short_trend,
                "change_percent": round(short_change, 2)
            }

        # 中期
        if data_len > mid_period:
            mid_trend = "上涨" if close.iloc[-1] > close.iloc[-mid_period-1] else "下跌"
            mid_change = (close.iloc[-1] - close.iloc[-mid_period-1]) / close.iloc[-mid_period-1] * 100
            timeframes["medium"] = {
                "period": mid_label,
                "trend": mid_trend,
                "change_percent": round(mid_change, 2)
            }

        # 长期
        if data_len > long_period:
            long_trend = "上涨" if close.iloc[-1] > close.iloc[-long_period-1] else "下跌"
            long_change = (close.iloc[-1] - close.iloc[-long_period-1]) / close.iloc[-long_period-1] * 100
            timeframes["long"] = {
                "period": long_label,
                "trend": long_trend,
                "change_percent": round(long_change, 2)
            }

        return timeframes

    def _analyze_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        动量分析
        """
        close = df["close"]

        # ROC (变动率指标)
        roc_5 = ((close - close.shift(5)) / close.shift(5) * 100).iloc[-1]
        roc_10 = ((close - close.shift(10)) / close.shift(10) * 100).iloc[-1]
        roc_20 = ((close - close.shift(20)) / close.shift(20) * 100).iloc[-1]

        # 威廉指标 %R
        high_14 = df["high"].rolling(window=14).max()
        low_14 = df["low"].rolling(window=14).min()
        williams_r = -100 * (high_14 - close) / (high_14 - low_14)
        current_williams = williams_r.iloc[-1]

        # 判断动量状态
        momentum_status = "neutral"
        if roc_20 > 5 and current_williams > -20:
            momentum_status = "strong_bullish"
        elif roc_20 > 2 and current_williams > -50:
            momentum_status = "bullish"
        elif roc_20 < -5 and current_williams < -80:
            momentum_status = "strong_bearish"
        elif roc_20 < -2 and current_williams < -50:
            momentum_status = "bearish"

        return {
            "status": momentum_status,
            "roc_5d": round(float(roc_5) if not pd.isna(roc_5) else 0, 2),
            "roc_10d": round(float(roc_10) if not pd.isna(roc_10) else 0, 2),
            "roc_20d": round(float(roc_20) if not pd.isna(roc_20) else 0, 2),
            "williams_r": round(float(current_williams) if not pd.isna(current_williams) else 0, 2)
        }

    def _analyze_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        波动率分析
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 历史波动率 (标准差)
        returns = close.pct_change()
        volatility_20 = returns.rolling(window=20).std() * np.sqrt(252) * 100
        current_volatility = volatility_20.iloc[-1]

        # ATR (真实波动幅度均值)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        current_atr = atr.iloc[-1]
        atr_percent = (current_atr / close.iloc[-1]) * 100

        # 布林带宽度
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        bb_width = (std20 * 4 / sma20 * 100).iloc[-1]

        # 波动率水平判断
        volatility_level = "low"
        if current_volatility > 40 or bb_width > 20:
            volatility_level = "high"
        elif current_volatility > 25 or bb_width > 10:
            volatility_level = "medium"

        return {
            "level": volatility_level,
            "historical_volatility": round(float(current_volatility) if not pd.isna(current_volatility) else 0, 2),
            "atr": round(float(current_atr) if not pd.isna(current_atr) else 0, 2),
            "atr_percent": round(float(atr_percent) if not pd.isna(atr_percent) else 0, 2),
            "bollinger_width": round(float(bb_width) if not pd.isna(bb_width) else 0, 2)
        }

    def _calculate_signal_strength(self, df: pd.DataFrame, trend: str) -> Dict[str, Any]:
        """
        计算买卖信号强度
        """
        close = df["close"]

        # 计算多个指标的一致性
        buy_signals = 0
        sell_signals = 0
        total_signals = 0

        # 1. RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        total_signals += 1
        if current_rsi < 30: buy_signals += 1
        elif current_rsi > 70: sell_signals += 1

        # 2. MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()

        total_signals += 1
        if macd.iloc[-1] > signal.iloc[-1]: buy_signals += 1
        else: sell_signals += 1

        # 3. 均线
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]

        total_signals += 1
        if sma20 > sma50: buy_signals += 1
        else: sell_signals += 1

        # 4. 价格位置
        total_signals += 1
        if close.iloc[-1] > sma20: buy_signals += 1
        else: sell_signals += 1

        # 计算信号强度
        buy_strength = (buy_signals / total_signals) * 100
        sell_strength = (sell_signals / total_signals) * 100

        # 判断主要信号
        main_signal = "neutral"
        if buy_strength >= 75:
            main_signal = "strong_buy"
        elif buy_strength >= 50:
            main_signal = "buy"
        elif sell_strength >= 75:
            main_signal = "strong_sell"
        elif sell_strength >= 50:
            main_signal = "sell"

        return {
            "signal": main_signal,
            "buy_strength": round(buy_strength, 1),
            "sell_strength": round(sell_strength, 1),
            "buy_indicators": buy_signals,
            "sell_indicators": sell_signals,
            "total_indicators": total_signals
        }

    def _calculate_fibonacci_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        计算斐波那契回撤位
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # 寻找最近的显著高点和低点 (例如过去6个月)
        # 简化处理：取整个数据集的极值
        period_high = high.max()
        period_low = low.min()
        
        diff = period_high - period_low
        
        levels = {
            "0.0": period_high,
            "0.236": period_high - 0.236 * diff,
            "0.382": period_high - 0.382 * diff,
            "0.5": period_high - 0.5 * diff,
            "0.618": period_high - 0.618 * diff,
            "0.786": period_high - 0.786 * diff,
            "1.0": period_low
        }
        
        # 判断当前价格位置
        current_price = close.iloc[-1]
        nearest_level = "None"
        min_dist = float("inf")
        
        for level_name, price in levels.items():
            dist = abs(current_price - price)
            if dist < min_dist:
                min_dist = dist
                nearest_level = level_name
                
        # 即使距离较远也返回最近的
        if min_dist > current_price * 0.05: # 如果距离超过5%，这不算"附近"
            nearest_level_desc = "区间内"
        else:
            nearest_level_desc = f"接近 Fib {nearest_level}"

        return {
            "high_price": float(period_high),
            "low_price": float(period_low),
            "levels": {k: round(float(v), 2) for k, v in levels.items()},
            "current_position": nearest_level_desc,
            "nearest_level": nearest_level,
            "distance_percent": round(min_dist / current_price * 100, 2)
        }

