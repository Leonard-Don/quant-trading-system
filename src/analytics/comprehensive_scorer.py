"""
综合评分系统
整合多维度分析结果，给出综合评分和投资建议
"""

import pandas as pd
from typing import Dict, List, Any
import logging
from .trend_analyzer import TrendAnalyzer
from .volume_price_analyzer import VolumePriceAnalyzer
from .sentiment_analyzer import SentimentAnalyzer
from .pattern_recognizer import PatternRecognizer
from .fundamental_analyzer import FundamentalAnalyzer

logger = logging.getLogger(__name__)


class ComprehensiveScorer:
    """
    综合评分系统
    整合趋势分析、量价分析、情绪分析等多个维度，给出综合评分
    """

    def __init__(self):
        self.trend_analyzer = TrendAnalyzer()
        self.volume_analyzer = VolumePriceAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.pattern_recognizer = PatternRecognizer()
        self.fundamental_analyzer = FundamentalAnalyzer()

    def comprehensive_analysis(
        self,
        df: pd.DataFrame,
        symbol: str = None,
        include_pattern: bool = True
    ) -> Dict[str, Any]:
        """
        综合分析

        Args:
            df: 股票OHLCV数据
            symbol: 股票代码

        Returns:
            综合分析结果
        """
        if df.empty or len(df) < 50:
            return {
                "overall_score": 50,
                "recommendation": "观望",
                "confidence": "low",
                "error": "数据不足，至少需要50个交易日数据"
            }

        # 1. 趋势分析
        trend_result = self.trend_analyzer.analyze_trend(df)

        # 2. 量价分析
        volume_result = self.volume_analyzer.analyze(df)

        # 3. 情绪分析
        sentiment_result = self.sentiment_analyzer.analyze(df, symbol)

        # 4. 基本面分析
        fundamental_result = self.fundamental_analyzer.analyze(symbol)

        # 5. 形态识别（可选）
        pattern_result = {"candlestick_patterns": [], "chart_patterns": []}
        if include_pattern:
            try:
                pattern_result = self.pattern_recognizer.recognize_patterns(df)
            except Exception as e:
                logger.warning(f"形态识别失败: {e}")

        # 6. 计算各维度得分
        trend_score = self._calculate_trend_score(trend_result)
        volume_score = self._calculate_volume_score(volume_result)
        sentiment_score = self._calculate_sentiment_score(sentiment_result)
        technical_score = self._calculate_technical_score(trend_result)
        fundamental_score = self._calculate_fundamental_score(fundamental_result)

        # 7. 综合评分 (加权平均)
        weights = {
            "trend": 0.30,      # 趋势权重30%
            "volume": 0.20,     # 量价权重20%
            "sentiment": 0.20,  # 情绪权重20%
            "technical": 0.10,   # 技术指标权重10%
            "fundamental": 0.20 # 基本面权重20%
        }

        overall_score = (
            trend_score * weights["trend"] +
            volume_score * weights["volume"] +
            sentiment_score * weights["sentiment"] +
            technical_score * weights["technical"] +
            fundamental_score * weights["fundamental"]
        )

        # 8. 生成投资建议
        recommendation = self._generate_recommendation(overall_score, trend_result, volume_result, sentiment_result)

        # 9. 评估置信度
        confidence = self._assess_confidence(trend_result, volume_result, sentiment_result)

        # 10. 关键信号总结
        key_signals = self._summarize_key_signals(trend_result, volume_result, sentiment_result)

        # 11. 风险提示
        risk_warnings = self._generate_risk_warnings(trend_result, volume_result, sentiment_result)

        # 12. 生成评分解释
        score_explanation = self._generate_score_explanation(
            trend_score, volume_score, sentiment_score, technical_score, fundamental_score,
            trend_result, volume_result, sentiment_result
        )

        # 13. 生成推荐原因
        recommendation_reasons = self._generate_recommendation_reasons(
            trend_result, volume_result, sentiment_result
        )

        return {
            "overall_score": round(overall_score, 1),
            "recommendation": recommendation,
            "confidence": confidence,
            "scores": {
                "trend": round(trend_score, 1),
                "volume": round(volume_score, 1),
                "sentiment": round(sentiment_score, 1),
                "technical": round(technical_score, 1),
                "fundamental": round(fundamental_score, 1)
            },
            "score_explanation": score_explanation,
            "recommendation_reasons": recommendation_reasons,
            "trend_analysis": trend_result,
            "volume_analysis": volume_result,
            "sentiment_analysis": sentiment_result,
            "pattern_analysis": pattern_result,
            "fundamental_analysis": fundamental_result,
            "key_signals": key_signals,
            "risk_warnings": risk_warnings
        }

    def _calculate_fundamental_score(self, fundamental_result: Dict[str, Any]) -> float:
        """计算基本面得分"""
        # 取各个维度的平均分
        v_score = fundamental_result.get("valuation", {}).get("score", 50)
        h_score = fundamental_result.get("financial_health", {}).get("score", 50)
        g_score = fundamental_result.get("growth", {}).get("score", 50)
        
        return (v_score + h_score + g_score) / 3

    def _calculate_trend_score(self, trend_result: Dict[str, Any]) -> float:
        """
        计算趋势得分 (0-100)
        """
        score = 50.0  # 基准分

        # 1. 趋势方向
        trend = trend_result.get("trend", "neutral")
        if trend == "strong_bullish":
            score += 30
        elif trend == "bullish":
            score += 20
        elif trend == "strong_bearish":
            score -= 30
        elif trend == "bearish":
            score -= 20

        # 2. 趋势强度
        strength = trend_result.get("trend_strength", 50)
        if strength > 70:
            score += 10
        elif strength > 50:
            score += 5
        elif strength < 30:
            score -= 10
        elif strength < 50:
            score -= 5

        # 3. 信号强度
        signal = trend_result.get("signal_strength", {})
        signal_type = signal.get("signal", "neutral")
        if signal_type == "strong_buy":
            score += 10
        elif signal_type == "buy":
            score += 5
        elif signal_type == "strong_sell":
            score -= 10
        elif signal_type == "sell":
            score -= 5

        return max(0, min(100, score))

    def _calculate_volume_score(self, volume_result: Dict[str, Any]) -> float:
        """
        计算量价得分 (0-100)
        """
        score = 50.0  # 基准分

        # 1. OBV趋势
        obv = volume_result.get("obv_analysis", {})
        obv_trend = obv.get("obv_trend", "neutral")
        if obv_trend == "bullish":
            score += 20
        elif obv_trend == "bearish":
            score -= 20

        # 2. 资金流向
        money_flow = volume_result.get("money_flow", {})
        flow_status = money_flow.get("status", "neutral")
        if flow_status == "strong_inflow":
            score += 15
        elif flow_status == "strong_outflow":
            score -= 15
        elif flow_status == "overbought":
            score -= 10  # 超买是风险信号
        elif flow_status == "oversold":
            score += 10  # 超卖是机会信号

        # 3. 累积/派发
        ad = volume_result.get("accumulation_distribution", {})
        ad_trend = ad.get("ad_trend", "neutral")
        if ad_trend == "accumulation":
            score += 10
        elif ad_trend == "distribution":
            score -= 10

        # 4. 量价背离
        divergence = volume_result.get("divergence", {})
        divergences = divergence.get("divergences", [])
        for div in divergences:
            if div["signal"] == "bullish":
                score += 5
            elif div["signal"] == "bearish":
                score -= 5

        return max(0, min(100, score))

    def _calculate_sentiment_score(self, sentiment_result: Dict[str, Any]) -> float:
        """
        计算情绪得分 (0-100)
        """
        # 直接使用恐慌贪婪指数作为基准
        score = sentiment_result.get("fear_greed_index", 50)

        # 根据风险等级调整
        risk_level = sentiment_result.get("risk_level", "medium")
        if risk_level == "very_high":
            score = min(score, 30)  # 高风险限制分数
        elif risk_level == "high":
            score = min(score, 50)

        # 极端情绪调整
        extreme = sentiment_result.get("extreme_sentiment", {})
        if extreme.get("has_extreme_sentiment", False):
            signals = extreme.get("signals", [])
            for signal in signals:
                if signal["type"] == "panic_selling":
                    score = max(score - 10, 0)  # 恐慌性抛售降低分数
                elif signal["type"] == "frenzy_buying":
                    score = min(score - 10, 100)  # 疯狂买入也是风险

        return max(0, min(100, score))

    def _calculate_technical_score(self, trend_result: Dict[str, Any]) -> float:
        """
        计算技术指标得分 (0-100)
        """
        # 使用趋势分析中的技术评分
        score = trend_result.get("score", 50)

        # 多时间周期一致性加分
        multi_timeframe = trend_result.get("multi_timeframe", {})
        consistent_trends = 0
        total_timeframes = 0

        for tf_key, tf_data in multi_timeframe.items():
            if isinstance(tf_data, dict) and "trend" in tf_data:
                total_timeframes += 1
                if tf_data["trend"] == "上涨":
                    consistent_trends += 1

        if total_timeframes > 0:
            consistency_ratio = consistent_trends / total_timeframes
            if consistency_ratio >= 1.0:  # 所有周期一致上涨
                score += 10
            elif consistency_ratio >= 0.66:  # 2/3周期上涨
                score += 5
            elif consistency_ratio <= 0:  # 所有周期一致下跌
                score -= 10
            elif consistency_ratio <= 0.33:  # 2/3周期下跌
                score -= 5

        return max(0, min(100, score))

    def _generate_recommendation(
        self,
        overall_score: float,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> str:
        """
        生成投资建议
        """
        if overall_score >= 75:
            return "强烈买入"
        elif overall_score >= 60:
            return "买入"
        elif overall_score >= 45:
            return "持有"
        elif overall_score >= 30:
            return "卖出"
        else:
            return "强烈卖出"

    def _assess_confidence(
        self,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> str:
        """
        评估置信度
        """
        confidence_score = 0

        # 1. 趋势强度
        strength = trend_result.get("trend_strength", 0)
        if strength > 70:
            confidence_score += 3
        elif strength > 50:
            confidence_score += 2
        elif strength > 30:
            confidence_score += 1

        # 2. 信号一致性
        signal_strength = trend_result.get("signal_strength", {})
        buy_strength = signal_strength.get("buy_strength", 0)
        sell_strength = signal_strength.get("sell_strength", 0)

        if max(buy_strength, sell_strength) > 75:
            confidence_score += 3
        elif max(buy_strength, sell_strength) > 50:
            confidence_score += 2

        # 3. 量价一致性
        price_vol_corr = volume_result.get("price_volume_correlation", {})
        corr_value = abs(price_vol_corr.get("correlation", 0))
        if corr_value > 0.5:
            confidence_score += 2
        elif corr_value > 0.3:
            confidence_score += 1

        # 置信度判断
        if confidence_score >= 7:
            return "very_high"
        elif confidence_score >= 5:
            return "high"
        elif confidence_score >= 3:
            return "medium"
        else:
            return "low"

    def _summarize_key_signals(
        self,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> List[Dict[str, str]]:
        """
        总结关键信号
        """
        signals = []

        # 1. 趋势信号
        trend = trend_result.get("trend", "")
        if trend in ["strong_bullish", "strong_bearish"]:
            signals.append({
                "type": "趋势",
                "signal": "强趋势" if "bullish" in trend else "强势下跌",
                "importance": "high"
            })

        # 2. 量价信号
        patterns = volume_result.get("volume_patterns", {}).get("patterns", [])
        for pattern in patterns:
            signals.append({
                "type": "量价",
                "signal": pattern["description"],
                "importance": "medium"
            })

        # 3. 情绪信号
        overall_sentiment = sentiment_result.get("overall_sentiment", "")
        if "extreme" in overall_sentiment:
            signals.append({
                "type": "情绪",
                "signal": "极端情绪" + ("（贪婪）" if "greed" in overall_sentiment else "（恐慌）"),
                "importance": "high"
            })

        # 4. 技术指标信号
        indicators = trend_result.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        if rsi > 70:
            signals.append({
                "type": "技术",
                "signal": "RSI超买",
                "importance": "medium"
            })
        elif rsi < 30:
            signals.append({
                "type": "技术",
                "signal": "RSI超卖",
                "importance": "medium"
            })

        return signals

    def _generate_risk_warnings(
        self,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> List[str]:
        """
        生成风险提示
        """
        warnings = []

        # 1. 高风险等级
        risk_level = sentiment_result.get("risk_level", "")
        risk_map = {
            "very_high": "极高",
            "high": "高",
            "medium": "中",
            "low": "低",
            "very_low": "极低"
        }
        
        if risk_level in ["high", "very_high"]:
            cn_risk = risk_map.get(risk_level, risk_level)
            warnings.append(f"当前市场风险等级为{cn_risk}，建议谨慎操作")

        # 2. 量价背离
        divergences = volume_result.get("divergence", {}).get("divergences", [])
        if divergences:
            for div in divergences:
                warnings.append(f"检测到{div['description']}，可能预示趋势反转")

        # 3. 极端情绪
        extreme = sentiment_result.get("extreme_sentiment", {})
        if extreme.get("has_extreme_sentiment", False):
            warnings.append("市场出现极端情绪，波动加剧")

        # 4. 高波动率
        volatility = trend_result.get("volatility", {})
        if volatility.get("level") == "high":
            warnings.append("当前波动率较高，注意控制仓位")

        # 5. 趋势弱化
        strength = trend_result.get("trend_strength", 100)
        if strength < 30:
            warnings.append("趋势强度较弱，方向不明确")

        return warnings

    def _generate_score_explanation(
        self,
        trend_score: float,
        volume_score: float,
        sentiment_score: float,
        technical_score: float,
        fundamental_score: float,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> List[Dict[str, Any]]:
        """生成评分解释"""
        explanations = []

        # 1. 趋势解释
        trend_desc = trend_result.get("trend", "neutral")
        trend_reason = "趋势不明朗"
        if "bullish" in trend_desc:
            trend_reason = f"处于{'强' if 'strong' in trend_desc else ''}上升趋势 (强度: {trend_result.get('trend_strength', 0)})"
        elif "bearish" in trend_desc:
            trend_reason = f"处于{'强' if 'strong' in trend_desc else ''}下跌趋势 (强度: {trend_result.get('trend_strength', 0)})"
        
        explanations.append({
            "dimension": "趋势面",
            "score": round(trend_score, 1),
            "reason": trend_reason
        })

        # 2. 量价解释
        money_flow = volume_result.get("money_flow", {}).get("status", "neutral")
        volume_reason = "资金流向平稳"
        if money_flow == "strong_inflow":
            volume_reason = "主力资金强劲流入"
        elif money_flow == "strong_outflow":
            volume_reason = "主力资金大幅流出"
        elif money_flow == "overbought":
            volume_reason = "资金超买，需警惕回调"
        elif money_flow == "oversold":
            volume_reason = "资金超卖，可能反弹"
        
        explanations.append({
            "dimension": "资金面",
            "score": round(volume_score, 1),
            "reason": volume_reason
        })

        # 3. 情绪解释
        fg_index = sentiment_result.get("fear_greed_index", 50)
        sentiment_str = sentiment_result.get("overall_sentiment", "neutral")
        sentiment_map = {
            "extreme_greed": "极度贪婪", "greed": "贪婪", 
            "neutral": "中性", 
            "fear": "恐慌", "extreme_fear": "极度恐慌"
        }
        sentiment_reason = f"恐慌贪婪指数 {fg_index} ({sentiment_map.get(sentiment_str, '中性')})"
        
        explanations.append({
            "dimension": "情绪面",
            "score": round(sentiment_score, 1),
            "reason": sentiment_reason
        })

        # 4. 技术解释
        indicators = trend_result.get("indicators", {})
        if not isinstance(indicators, dict):
            indicators = {}

        tech_reasons = []
        rsi = indicators.get("rsi", 50)
        # Ensure rsi is a number
        if not isinstance(rsi, (int, float)):
             rsi = 50

        if rsi > 70:
            tech_reasons.append("RSI超买")
        elif rsi < 30:
            tech_reasons.append("RSI超卖")
        
        macd = indicators.get("macd", {})
        if isinstance(macd, dict) and macd.get("histogram", 0) > 0:
            tech_reasons.append("MACD金叉")
        elif isinstance(macd, dict):
            tech_reasons.append("MACD死叉")
            
        explanations.append({
            "dimension": "技术面",
            "score": round(technical_score, 1),
            "reason": "，".join(tech_reasons) if tech_reasons else "技术指标无显著信号"
        })

        # 5. 基本面解释 (简化)
        fundamental_reason = "基本面稳健" if fundamental_score >= 60 else "基本面一般" if fundamental_score >= 40 else "基本面较弱"
        explanations.append({
            "dimension": "基本面",
            "score": round(fundamental_score, 1),
            "reason": fundamental_reason
        })

        return explanations

    def _generate_recommendation_reasons(
        self,
        trend_result: Dict,
        volume_result: Dict,
        sentiment_result: Dict
    ) -> List[str]:
        """生成推荐原因"""
        reasons = []

        # 趋势原因
        trend = trend_result.get("trend", "")
        if "bullish" in trend:
            reasons.append(f"价格处于{'强' if 'strong' in trend else ''}上升通道，均线多头排列")
        elif "bearish" in trend:
            reasons.append(f"价格处于{'强' if 'strong' in trend else ''}下降通道，需警惕风险")

        # 关键信号
        signals = trend_result.get("signal_strength", {})
        if signals.get("buy_strength", 0) > 60:
            reasons.append("多项技术指标发出买入信号")
        if signals.get("sell_strength", 0) > 60:
            reasons.append("多项技术指标发出卖出信号")

        # 量价原因
        volume_patterns = volume_result.get("volume_patterns", {}).get("patterns", [])
        for pattern in volume_patterns[:1]: # 取最重要的一个
            reasons.append(f"量价形态：{pattern['description']}")

        # 情绪原因
        sentiment = sentiment_result.get("overall_sentiment", "")
        if sentiment == "fear" or sentiment == "extreme_fear":
            reasons.append("市场恐慌，可能存在超跌反弹机会")
        elif sentiment == "greed" or sentiment == "extreme_greed":
            reasons.append("市场情绪高涨，注意追高风险")

        return reasons
