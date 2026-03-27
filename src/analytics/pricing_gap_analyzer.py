"""
定价差异分析器
整合因子模型和估值模型，分析二级市场价格与内在价值之间的偏差及其驱动因素
"""

import logging
from typing import Dict, Any

from .asset_pricing import AssetPricingEngine
from .valuation_model import ValuationModel

logger = logging.getLogger(__name__)


class PricingGapAnalyzer:
    """
    定价差异分析器
    打通一级市场估值逻辑（DCF/可比估值）和二级市场定价（因子模型），
    识别错误定价并分析偏差来源
    """

    def __init__(self):
        self.pricing_engine = AssetPricingEngine()
        self.valuation_model = ValuationModel()

    def analyze(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """
        完整的定价差异分析

        Args:
            symbol: 股票代码
            period: 因子模型分析周期

        Returns:
            综合定价差异分析结果
        """
        try:
            # 1. 因子模型分析 (二级市场定价逻辑)
            factor_result = self.pricing_engine.analyze(symbol, period)

            # 2. 估值模型分析 (一级市场估值逻辑)
            valuation_result = self.valuation_model.analyze(symbol)

            # 3. 定价差异分析
            gap_analysis = self._analyze_gap(factor_result, valuation_result)

            # 4. 偏差归因
            deviation_drivers = self._analyze_deviation_drivers(factor_result, valuation_result)

            # 5. 投资含义
            implications = self._derive_implications(gap_analysis, factor_result, valuation_result)

            return {
                "symbol": symbol,
                "factor_model": factor_result,
                "valuation": valuation_result,
                "gap_analysis": gap_analysis,
                "deviation_drivers": deviation_drivers,
                "implications": implications,
                "summary": self._generate_summary(gap_analysis, valuation_result)
            }

        except Exception as e:
            logger.error(f"定价差异分析出错 {symbol}: {e}", exc_info=True)
            return {
                "symbol": symbol,
                "error": str(e),
                "factor_model": {},
                "valuation": {},
                "gap_analysis": {},
                "deviation_drivers": {},
                "implications": {},
                "summary": f"分析失败: {e}"
            }

    def _analyze_gap(self, factor: Dict, valuation: Dict) -> Dict[str, Any]:
        """
        分析市价与内在价值之间的差距

        核心指标：mispricing_ratio = (市价 - 内在价值) / 内在价值
        """
        current_price = valuation.get("current_price", 0)
        fair_value = valuation.get("fair_value", {})
        mid_value = fair_value.get("mid")
        val_status = valuation.get("valuation_status", {})

        if not mid_value or mid_value <= 0 or current_price <= 0:
            return {
                "mispricing_ratio": None,
                "gap_absolute": None,
                "gap_pct": None,
                "severity": "unknown",
                "label": "数据不足，无法计算定价差异"
            }

        mispricing = (current_price - mid_value) / mid_value
        gap_abs = current_price - mid_value

        # 严重程度
        abs_mis = abs(mispricing)
        if abs_mis > 0.30:
            severity = "extreme"
            severity_label = "极端偏离"
        elif abs_mis > 0.20:
            severity = "high"
            severity_label = "显著偏离"
        elif abs_mis > 0.10:
            severity = "moderate"
            severity_label = "中度偏离"
        elif abs_mis > 0.05:
            severity = "mild"
            severity_label = "轻度偏离"
        else:
            severity = "negligible"
            severity_label = "定价合理"

        direction = "溢价(高估)" if mispricing > 0 else "折价(低估)" if mispricing < 0 else "持平"

        return {
            "current_price": round(current_price, 2),
            "fair_value_mid": round(mid_value, 2),
            "fair_value_low": fair_value.get("low"),
            "fair_value_high": fair_value.get("high"),
            "mispricing_ratio": round(mispricing, 4),
            "gap_absolute": round(gap_abs, 2),
            "gap_pct": round(mispricing * 100, 1),
            "direction": direction,
            "severity": severity,
            "severity_label": severity_label,
            "valuation_label": val_status.get("label", ""),
            "in_fair_range": val_status.get("in_fair_range", False)
        }

    def _analyze_deviation_drivers(self, factor: Dict, valuation: Dict) -> Dict[str, Any]:
        """
        分析定价偏差的驱动因素
        将偏差归因为：市场情绪、风格因子、基本面差异
        """
        drivers = []

        # 1. 因子驱动分析
        capm = factor.get("capm", {})
        ff3 = factor.get("fama_french", {})

        if "error" not in capm:
            beta = capm.get("beta", 1)
            alpha_pct = capm.get("alpha_pct", 0)

            if abs(alpha_pct) > 5:
                drivers.append({
                    "factor": "Alpha 超额收益",
                    "impact": "positive" if alpha_pct > 0 else "negative",
                    "magnitude": abs(alpha_pct),
                    "description": f"CAPM Alpha 为 {alpha_pct:.1f}%，{'存在未被市场风险解释的超额收益' if alpha_pct > 0 else '风险调整后收益不佳'}"
                })

            if beta > 1.3:
                drivers.append({
                    "factor": "高系统性风险",
                    "impact": "risk",
                    "magnitude": beta,
                    "description": f"Beta={beta:.2f}，系统性风险溢价可能推高估值"
                })
            elif beta < 0.7:
                drivers.append({
                    "factor": "低系统性风险",
                    "impact": "defensive",
                    "magnitude": beta,
                    "description": f"Beta={beta:.2f}，防御性定价可能享受安全溢价"
                })

        if "error" not in ff3:
            loadings = ff3.get("factor_loadings", {})

            size_loading = loadings.get("size", 0)
            if abs(size_loading) > 0.3:
                style = "小盘" if size_loading > 0 else "大盘"
                drivers.append({
                    "factor": f"规模因子({style}风格)",
                    "impact": "style",
                    "magnitude": abs(size_loading),
                    "description": f"SMB loading={size_loading:.2f}，{style}股溢价/折价效应"
                })

            value_loading = loadings.get("value", 0)
            if abs(value_loading) > 0.3:
                style = "价值" if value_loading > 0 else "成长"
                drivers.append({
                    "factor": f"价值因子({style}风格)",
                    "impact": "style",
                    "magnitude": abs(value_loading),
                    "description": f"HML loading={value_loading:.2f}，{style}股定价效应"
                })

        # 2. 估值驱动分析
        comparable = valuation.get("comparable", {})
        if "error" not in comparable:
            methods = comparable.get("methods", [])
            for m in methods:
                current = m.get("current_multiple", 0)
                bench = m.get("benchmark_multiple", 0)
                if current > 0 and bench > 0:
                    ratio = current / bench
                    if ratio > 1.3:
                        drivers.append({
                            "factor": f"{m['method']}溢价",
                            "impact": "overvalued",
                            "magnitude": round(ratio, 2),
                            "description": f"当前{m['method']}为{current:.1f}，行业基准为{bench:.1f}，溢价{(ratio-1)*100:.0f}%"
                        })
                    elif ratio < 0.7:
                        drivers.append({
                            "factor": f"{m['method']}折价",
                            "impact": "undervalued",
                            "magnitude": round(ratio, 2),
                            "description": f"当前{m['method']}为{current:.1f}，行业基准为{bench:.1f}，折价{(1-ratio)*100:.0f}%"
                        })

        sorted_drivers = self._sort_drivers(drivers)
        return {
            "drivers": sorted_drivers,
            "primary_driver": sorted_drivers[0] if sorted_drivers else None,
            "driver_count": len(sorted_drivers)
        }

    def _sort_drivers(self, drivers):
        """Sort candidate drivers by impact strength instead of insertion order."""
        if not drivers:
            return []

        ranked = sorted(
            drivers,
            key=lambda item: (
                self._driver_signal_strength(item),
                abs(float(item.get("magnitude") or 0)),
                item.get("factor", ""),
            ),
            reverse=True,
        )
        enriched = []
        for index, item in enumerate(ranked, start=1):
            enriched.append({
                **item,
                "rank": index,
                "signal_strength": self._driver_signal_strength(item),
                "ranking_reason": self._driver_ranking_reason(item),
            })
        return enriched

    def _driver_signal_strength(self, driver: Dict[str, Any]) -> float:
        """Normalize heterogeneous driver magnitudes onto a comparable ranking scale."""
        if "_signal_strength" in driver:
            return float(driver["_signal_strength"])

        magnitude = abs(float(driver.get("magnitude") or 0))
        impact = driver.get("impact")

        if impact in {"positive", "negative"}:
            score = magnitude / 5.0
        elif impact in {"risk", "defensive"}:
            score = abs(magnitude - 1.0) / 0.3
        elif impact == "style":
            score = magnitude / 0.3
        elif impact in {"overvalued", "undervalued"}:
            score = abs(magnitude - 1.0) / 0.3
        else:
            score = magnitude

        return round(score, 4)

    def _driver_ranking_reason(self, driver: Dict[str, Any]) -> str:
        """Explain the dimension used to rank this driver."""
        impact = driver.get("impact")
        if impact in {"positive", "negative"}:
            return "按 Alpha 绝对值排序"
        if impact in {"risk", "defensive"}:
            return "按 Beta 偏离 1 的幅度排序"
        if impact == "style":
            return "按风格因子暴露绝对值排序"
        if impact in {"overvalued", "undervalued"}:
            return "按估值倍数偏离行业基准幅度排序"
        return "按信号幅度排序"

    def _derive_implications(self, gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, Any]:
        """推导投资含义和建议"""
        severity = gap.get("severity", "unknown")
        gap_pct = gap.get("gap_pct", 0)
        direction = gap.get("direction", "")

        # 因子模型中的 Alpha
        capm_alpha = factor.get("capm", {}).get("alpha_pct", 0)
        ff3_alpha = factor.get("fama_french", {}).get("alpha_pct", 0)

        insights = []
        risk_level = "medium"

        if severity in ["extreme", "high"]:
            if "低估" in direction:
                insights.append("存在显著低估，市场可能尚未充分反映内在价值")
                insights.append("建议深入研究是否有'价值陷阱'风险（基本面恶化导致的低估）")
                risk_level = "medium"
            else:
                insights.append("存在显著高估，市场定价远超基本面支撑")
                insights.append("高估值可能由乐观预期驱动，注意估值回归风险")
                risk_level = "high"
        elif severity == "moderate":
            if "低估" in direction:
                insights.append("存在中度低估，可能存在交易机会")
            else:
                insights.append("存在中度高估，关注基本面能否支撑当前估值")
            risk_level = "medium"
        else:
            insights.append("定价基本合理，市场有效定价")
            risk_level = "low"

        # Alpha 信号
        if capm_alpha > 5:
            insights.append(f"CAPM Alpha {capm_alpha:.1f}%，历史上持续超越市场，可能具有定价优势")
        elif capm_alpha < -5:
            insights.append(f"CAPM Alpha {capm_alpha:.1f}%，历史上持续跑输市场，即使低估也需谨慎")

        # 一级 vs 二级视角
        val_status = valuation.get("valuation_status", {}).get("status", "")
        if val_status in ["undervalued", "severely_undervalued"]:
            insights.append("一级市场视角（基本面估值）认为当前价格偏低")
        elif val_status in ["overvalued", "severely_overvalued"]:
            insights.append("一级市场视角（基本面估值）认为当前价格偏高")

        confidence_meta = self._assess_confidence(gap, factor, valuation)

        return {
            "insights": insights,
            "risk_level": risk_level,
            "primary_view": "低估" if gap_pct and gap_pct < -10 else "高估" if gap_pct and gap_pct > 10 else "合理",
            "confidence": confidence_meta["level"],
            "confidence_score": confidence_meta["score"],
            "confidence_reasons": confidence_meta["reasons"],
        }

    def _assess_confidence(self, gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, Any]:
        """Estimate confidence from data quality, model coverage and valuation consistency."""
        score = 0.0
        reasons = []

        fair_value = valuation.get("fair_value", {}) or {}
        if gap.get("gap_pct") is not None and fair_value.get("mid"):
            score += 0.15
        else:
            reasons.append("缺少完整的价格偏差锚点")

        capm = factor.get("capm", {}) or {}
        ff3 = factor.get("fama_french", {}) or {}
        if "error" not in capm:
            score += 0.12
        else:
            reasons.append("CAPM 模型不可用")

        if "error" not in ff3:
            score += 0.12
        else:
            reasons.append("FF3 模型不可用")

        factor_points = max(
            int(factor.get("data_points") or 0),
            int(capm.get("data_points") or 0),
            int(ff3.get("data_points") or 0),
        )
        if factor_points >= 180:
            score += 0.16
        elif factor_points >= 120:
            score += 0.12
        elif factor_points >= 60:
            score += 0.08
            reasons.append("因子样本窗口偏短")
        else:
            reasons.append("因子样本不足")

        dcf = valuation.get("dcf", {}) or {}
        comparable = valuation.get("comparable", {}) or {}
        dcf_value = dcf.get("intrinsic_value")
        comparable_value = comparable.get("fair_value")
        dcf_ok = "error" not in dcf and dcf_value and dcf_value > 0
        comparable_ok = "error" not in comparable and comparable_value and comparable_value > 0
        valuation_methods = int(bool(dcf_ok)) + int(bool(comparable_ok))

        if valuation_methods == 2:
            score += 0.16
        elif valuation_methods == 1:
            score += 0.08
            reasons.append("仅有单一估值方法支撑")
        else:
            reasons.append("缺少可用估值方法")

        price_source = valuation.get("current_price_source", "unavailable")
        if price_source == "live":
            score += 0.09
        elif price_source in {"fundamental_current_price", "fundamental_regular_market_price"}:
            score += 0.07
        elif price_source in {"fundamental_previous_close", "historical_close"}:
            score += 0.04
            reasons.append("当前价格使用回退值")
        else:
            reasons.append("当前价格来源不可确认")

        if dcf_ok and comparable_ok:
            midpoint = (float(dcf_value) + float(comparable_value)) / 2
            divergence = abs(float(dcf_value) - float(comparable_value)) / midpoint if midpoint > 0 else None
            if divergence is not None:
                if divergence <= 0.15:
                    score += 0.10
                elif divergence <= 0.30:
                    score += 0.05
                    reasons.append("DCF 与可比估值存在一定分歧")
                else:
                    reasons.append("DCF 与可比估值分歧较大")

        score = max(0.0, min(score, 1.0))
        if score >= 0.72:
            level = "high"
        elif score >= 0.45:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": round(score, 2),
            "reasons": reasons[:3],
        }

    def _generate_summary(self, gap: Dict, valuation: Dict) -> str:
        """生成定价差异摘要"""
        severity_label = gap.get("severity_label", "未知")
        gap_pct = gap.get("gap_pct")
        current = gap.get("current_price")
        fair = gap.get("fair_value_mid")
        val_label = valuation.get("valuation_status", {}).get("label", "")

        if gap_pct is None:
            return "数据不足，无法进行定价差异分析"

        direction = "溢价" if gap_pct > 0 else "折价"
        return f"市价${current}，公允价值${fair}，{direction}{abs(gap_pct):.1f}%（{severity_label}），估值状态：{val_label}"
