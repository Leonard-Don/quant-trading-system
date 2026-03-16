"""
市场情绪分析模块
分析市场情绪、波动率和恐慌程度
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    市场情绪分析器
    通过波动率、恐慌指数等指标判断市场情绪
    
    Args:
        config: 可选配置字典，支持以下参数：
            - volatility_thresholds: 波动率情绪阈值
            - fear_greed_weights: 恐慌贪婪指数各因子权重
            - risk_thresholds: 风险等级阈值
            - analysis_window: 分析窗口期（天数）
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "volatility_thresholds": {
            "panic": 40,      # 恐慌阈值
            "fear": 30,       # 恐惧阈值
            "calm": 20,       # 平静阈值
            "complacent": 15  # 自满阈值
        },
        "fear_greed_weights": {
            "momentum": 25,       # 价格动量权重
            "price_strength": 20, # 价格强度权重
            "volatility": 20,     # 波动率权重
            "volume": 20,         # 成交量权重
            "trend": 15           # 趋势权重
        },
        "risk_thresholds": {
            "very_high": 7,
            "high": 5,
            "medium": 3,
            "low": 1
        },
        "analysis_window": {
            "short": 5,
            "medium": 20,
            "long": 50
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化情绪分析器
        
        Args:
            config: 自定义配置，将与默认配置合并
        """
        self.config = self._merge_config(config or {})
        self.volatility_thresholds = self.config["volatility_thresholds"]
        self.fear_greed_weights = self.config["fear_greed_weights"]
        self.risk_thresholds = self.config["risk_thresholds"]
        self.analysis_window = self.config["analysis_window"]
    
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

    def analyze(self, df: pd.DataFrame, symbol: str = None) -> Dict[str, Any]:
        """
        综合情绪分析

        Args:
            df: 股票OHLCV数据
            symbol: 股票代码（可选）

        Returns:
            情绪分析结果
        """
        if df.empty or len(df) < 20:
            return {
                "overall_sentiment": "unknown",
                "fear_greed_index": 50,
                "volatility_sentiment": {},
                "market_indicators": {},
                "risk_level": "medium"
            }

        # 1. 波动率情绪
        volatility_sentiment = self._analyze_volatility_sentiment(df)

        # 2. 恐慌贪婪指数
        fear_greed = self._calculate_fear_greed_index(df)

        # 3. 市场广度指标
        market_breadth = self._analyze_market_breadth(df)

        # 4. 极端情绪检测
        extreme_sentiment = self._detect_extreme_sentiment(df)

        # 5. 风险水平
        risk_level = self._assess_risk_level(df, volatility_sentiment, fear_greed)

        # 6. 整体情绪判断
        overall_sentiment = self._determine_overall_sentiment(
            volatility_sentiment, fear_greed, extreme_sentiment
        )

        return {
            "overall_sentiment": overall_sentiment,
            "fear_greed_index": fear_greed,
            "volatility_sentiment": volatility_sentiment,
            "market_breadth": market_breadth,
            "extreme_sentiment": extreme_sentiment,
            "risk_level": risk_level
        }

    def _analyze_volatility_sentiment(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        基于波动率的情绪分析
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 1. 历史波动率
        returns = close.pct_change()
        hist_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
        current_vol = hist_vol.iloc[-1]

        # 2. ATR百分比
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        atr_pct = (atr / close * 100).iloc[-1]

        # 3. 波动率趋势
        vol_ma5 = hist_vol.rolling(window=5).mean().iloc[-1]
        vol_ma20 = hist_vol.rolling(window=20).mean().iloc[-1]

        vol_trend = "stable"
        if vol_ma5 > vol_ma20 * 1.5:
            vol_trend = "increasing"  # 波动率上升，情绪紧张
        elif vol_ma5 < vol_ma20 * 0.7:
            vol_trend = "decreasing"  # 波动率下降，情绪平稳

        # 情绪状态
        sentiment = "neutral"
        
        # 动态计算阈值 (如果数据足够)
        if len(hist_vol) > 100:
            high_vol_threshold = hist_vol.rolling(window=100).quantile(0.8).iloc[-1]
            low_vol_threshold = hist_vol.rolling(window=100).quantile(0.2).iloc[-1]
            # 确保阈值在合理范围内
            high_vol_threshold = max(25, min(high_vol_threshold, 60))
            low_vol_threshold = max(10, min(low_vol_threshold, 25))
        else:
            high_vol_threshold = 30
            low_vol_threshold = 15

        if current_vol > high_vol_threshold * 1.3:
            sentiment = "panic"  # 恐慌 (>80%分位数的1.3倍)
        elif current_vol > high_vol_threshold:
            sentiment = "fear"  # 恐惧 (>80%分位数)
        elif current_vol < low_vol_threshold:
            sentiment = "complacent"  # 自满 (<20%分位数)
        elif current_vol < low_vol_threshold * 1.3:
            sentiment = "calm"  # 平静
            
        return {
            "sentiment": sentiment,
            "historical_volatility": round(float(current_vol) if not pd.isna(current_vol) else 0, 2),
            "atr_percent": round(float(atr_pct) if not pd.isna(atr_pct) else 0, 2),
            "volatility_trend": vol_trend,
            "thresholds": {
                "high": round(high_vol_threshold, 2),
                "low": round(low_vol_threshold, 2)
            }
        }

    def _calculate_fear_greed_index(self, df: pd.DataFrame) -> float:
        """
        计算恐慌贪婪指数 (0-100)
        0 = 极度恐慌, 50 = 中性, 100 = 极度贪婪
        """
        score = 50.0  # 基准分

        close = df["close"]
        volume = df["volume"]

        # 1. 价格动量 (25分)
        momentum_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
        if momentum_20 > 10:
            score += 25
        elif momentum_20 > 5:
            score += 15
        elif momentum_20 > 0:
            score += 5
        elif momentum_20 < -10:
            score -= 25
        elif momentum_20 < -5:
            score -= 15
        elif momentum_20 < 0:
            score -= 5

        # 2. 价格强度 (20分)
        high_52w = close.rolling(window=252).max().iloc[-1] if len(close) >= 252 else close.max()
        low_52w = close.rolling(window=252).min().iloc[-1] if len(close) >= 252 else close.min()
        price_position = (close.iloc[-1] - low_52w) / (high_52w - low_52w) * 100

        if price_position > 80:
            score += 20
        elif price_position > 60:
            score += 10
        elif price_position < 20:
            score -= 20
        elif price_position < 40:
            score -= 10

        # 3. 波动率 (20分) - 高波动率表示恐慌
        returns = close.pct_change()
        volatility = returns.rolling(window=20).std() * np.sqrt(252) * 100
        current_vol = volatility.iloc[-1]

        if current_vol < 20:
            score += 20  # 低波动率，贪婪
        elif current_vol < 30:
            score += 10
        elif current_vol > 50:
            score -= 20  # 高波动率，恐慌
        elif current_vol > 40:
            score -= 10

        # 4. 成交量 (20分)
        vol_avg = volume.rolling(window=20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_avg

        if vol_ratio > 2 and close.iloc[-1] > close.iloc[-5]:
            score += 20  # 放量上涨，贪婪
        elif vol_ratio > 1.5 and close.iloc[-1] > close.iloc[-5]:
            score += 10
        elif vol_ratio > 2 and close.iloc[-1] < close.iloc[-5]:
            score -= 20  # 放量下跌，恐慌
        elif vol_ratio > 1.5 and close.iloc[-1] < close.iloc[-5]:
            score -= 10

        # 5. 趋势 (15分)
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]

        if close.iloc[-1] > sma20 > sma50:
            score += 15  # 上升趋势，贪婪
        elif close.iloc[-1] > sma20:
            score += 7
        elif close.iloc[-1] < sma20 < sma50:
            score -= 15  # 下降趋势，恐慌
        elif close.iloc[-1] < sma20:
            score -= 7

        # 限制在0-100范围
        score = max(0, min(100, score))

        return round(score, 1)

    def _analyze_market_breadth(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        市场广度分析
        """
        close = df["close"]

        # 新高新低比
        high_20 = close.rolling(window=20).max()
        low_20 = close.rolling(window=20).min()

        new_highs = (close == high_20).sum()
        new_lows = (close == low_20).sum()

        breadth_ratio = new_highs / (new_highs + new_lows) if (new_highs + new_lows) > 0 else 0.5

        breadth_status = "neutral"
        if breadth_ratio > 0.7:
            breadth_status = "strong_bullish"
        elif breadth_ratio > 0.6:
            breadth_status = "bullish"
        elif breadth_ratio < 0.3:
            breadth_status = "strong_bearish"
        elif breadth_ratio < 0.4:
            breadth_status = "bearish"

        return {
            "status": breadth_status,
            "new_highs": int(new_highs),
            "new_lows": int(new_lows),
            "breadth_ratio": round(float(breadth_ratio), 2)
        }

    def _detect_extreme_sentiment(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测极端情绪
        """
        close = df["close"]
        volume = df["volume"]

        extreme_signals = []

        # 1. 恐慌性抛售
        returns = close.pct_change()
        vol_avg = volume.rolling(window=20).mean()

        # 单日大幅下跌且放量
        recent_5_days = df.tail(5)
        for i in range(len(recent_5_days)):
            day_return = returns.iloc[-(5-i)]
            day_volume = volume.iloc[-(5-i)]
            vol_avg_val = vol_avg.iloc[-(5-i)]

            if day_return < -0.05 and day_volume > vol_avg_val * 1.5:
                extreme_signals.append({
                    "type": "panic_selling",
                    "description": "恐慌性抛售",
                    "severity": "high"
                })
                break

        # 2. 疯狂买入
        for i in range(len(recent_5_days)):
            day_return = returns.iloc[-(5-i)]
            day_volume = volume.iloc[-(5-i)]
            vol_avg_val = vol_avg.iloc[-(5-i)]

            if day_return > 0.05 and day_volume > vol_avg_val * 2:
                extreme_signals.append({
                    "type": "frenzy_buying",
                    "description": "疯狂买入",
                    "severity": "high"
                })
                break

        # 3. 死寂市场（极低成交量）
        if volume.iloc[-1] < vol_avg.iloc[-1] * 0.3:
            extreme_signals.append({
                "type": "dead_market",
                "description": "市场死寂",
                "severity": "medium"
            })

        # 4. 连续涨跌停
        consecutive_limits = 0
        threshold = 0.08  # 8%涨跌幅

        for i in range(min(5, len(returns))):
            if abs(returns.iloc[-(i+1)]) > threshold:
                consecutive_limits += 1
            else:
                break

        if consecutive_limits >= 3:
            extreme_signals.append({
                "type": "consecutive_limits",
                "description": f"连续{consecutive_limits}日极端波动",
                "severity": "high"
            })

        return {
            "has_extreme_sentiment": len(extreme_signals) > 0,
            "signals_count": len(extreme_signals),
            "signals": extreme_signals
        }

    def _assess_risk_level(self, df: pd.DataFrame, volatility_sentiment: Dict, fear_greed: float) -> str:
        """
        评估风险水平
        """
        risk_score = 0

        # 1. 波动率风险
        if volatility_sentiment["sentiment"] in ["panic", "fear"]:
            risk_score += 3
        elif volatility_sentiment["sentiment"] == "calm":
            risk_score += 1

        # 2. 恐慌贪婪指数风险
        if fear_greed < 20 or fear_greed > 80:
            risk_score += 3  # 极端情绪高风险
        elif fear_greed < 30 or fear_greed > 70:
            risk_score += 2

        # 3. 价格波动风险
        close = df["close"]
        returns = close.pct_change()
        max_drawdown = (close / close.cummax() - 1).min()

        if max_drawdown < -0.20:
            risk_score += 3
        elif max_drawdown < -0.10:
            risk_score += 2
        elif max_drawdown < -0.05:
            risk_score += 1

        # 风险等级判断
        if risk_score >= 7:
            return "very_high"
        elif risk_score >= 5:
            return "high"
        elif risk_score >= 3:
            return "medium"
        elif risk_score >= 1:
            return "low"
        else:
            return "very_low"

    def _determine_overall_sentiment(
        self,
        volatility_sentiment: Dict,
        fear_greed: float,
        extreme_sentiment: Dict
    ) -> str:
        """
        确定整体情绪
        """
        # 基于恐慌贪婪指数
        if fear_greed >= 80:
            base_sentiment = "extreme_greed"
        elif fear_greed >= 65:
            base_sentiment = "greed"
        elif fear_greed >= 45:
            base_sentiment = "neutral_bullish"
        elif fear_greed >= 35:
            base_sentiment = "neutral_bearish"
        elif fear_greed >= 20:
            base_sentiment = "fear"
        else:
            base_sentiment = "extreme_fear"

        # 如果有极端情绪信号，调整判断
        if extreme_sentiment["has_extreme_sentiment"]:
            for signal in extreme_sentiment["signals"]:
                if signal["type"] == "panic_selling":
                    base_sentiment = "extreme_fear"
                elif signal["type"] == "frenzy_buying":
                    base_sentiment = "extreme_greed"

        return base_sentiment



    def _interpret_vix(self, vix_value: float) -> str:
        """
        解释VIX值
        """
        if vix_value < 12:
            return "极低恐慌，市场可能过度自满"
        elif vix_value < 20:
            return "低恐慌，市场情绪平稳"
        elif vix_value < 30:
            return "中等恐慌，市场有所担忧"
        elif vix_value < 40:
            return "高恐慌，市场恐慌情绪较重"
        else:
            return "极度恐慌，市场极度恐慌"
