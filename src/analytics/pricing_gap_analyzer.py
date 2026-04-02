"""
定价差异分析器
整合因子模型和估值模型，分析二级市场价格与内在价值之间的偏差及其驱动因素
"""

import logging
from typing import Dict, Any, Optional, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

from .asset_pricing import AssetPricingEngine
from .pricing_gap_support import (
    assess_confidence,
    assess_factor_valuation_alignment,
    build_alignment_meta,
    build_trade_setup,
    resolve_factor_view,
    resolve_valuation_view,
)
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
            with ThreadPoolExecutor(max_workers=2) as executor:
                factor_future = executor.submit(self.pricing_engine.analyze, symbol, period)
                valuation_future = executor.submit(self.valuation_model.analyze, symbol)
                factor_result = factor_future.result()
                valuation_result = valuation_future.result()

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

    def screen(self, symbols: Iterable[str], period: str = "1y", limit: int = 10, max_workers: int = 4) -> Dict[str, Any]:
        """Run pricing analysis for a candidate universe and return ranked opportunities."""
        normalized_symbols = []
        seen = set()
        for raw_symbol in symbols or []:
            symbol = str(raw_symbol or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized_symbols.append(symbol)

        results = []
        failures = []
        with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers or 1), 8))) as executor:
            future_map = {
                executor.submit(self.analyze, symbol, period): symbol
                for symbol in normalized_symbols
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    analysis = future.result()
                except Exception as exc:
                    failures.append({"symbol": symbol, "error": str(exc)})
                    continue

                row = self._build_screening_row(analysis, period)
                if row.get("error"):
                    failures.append({
                        "symbol": symbol,
                        "error": row["error"],
                    })
                    continue
                results.append(row)

        ranked_results = sorted(
            results,
            key=lambda item: (
                float(item.get("screening_score") or 0),
                abs(float(item.get("gap_pct") or 0)),
                str(item.get("symbol") or ""),
            ),
            reverse=True,
        )[: max(int(limit or 0), 0)]

        for index, item in enumerate(ranked_results, start=1):
            item["rank"] = index

        return {
            "period": period,
            "total_input": len(normalized_symbols),
            "analyzed_count": len(results),
            "result_count": len(ranked_results),
            "results": ranked_results,
            "failures": failures,
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

    def build_gap_history(self, symbol: str, period: str = "1y", points: int = 60) -> Dict[str, Any]:
        """Build a historical series of market price versus current fair value anchor."""
        analysis = self.analyze(symbol, period)
        gap = analysis.get("gap_analysis", {}) or {}
        fair_value_mid = gap.get("fair_value_mid")
        if not fair_value_mid:
            return {
                "symbol": symbol,
                "period": period,
                "history": [],
                "error": "缺少公允价值锚点，无法构建历史偏差序列",
            }

        days = {"6mo": 180, "1y": 365, "2y": 730, "3y": 1095}.get(period, 365)
        history = self.pricing_engine.data_manager.get_historical_data(symbol, period=period or "1y")
        if history.empty or "close" not in history.columns:
            return {
                "symbol": symbol,
                "period": period,
                "history": [],
                "error": "缺少价格历史数据",
            }

        close_series = history["close"].dropna()
        if close_series.empty:
            return {
                "symbol": symbol,
                "period": period,
                "history": [],
                "error": "缺少有效收盘价序列",
            }

        sampled = close_series if len(close_series) <= points else close_series.iloc[
            pd.Index(np.linspace(0, len(close_series) - 1, points).astype(int)).unique()
        ]
        gap_history = []
        for index, price in sampled.items():
            gap_pct = ((float(price) - float(fair_value_mid)) / float(fair_value_mid)) * 100
            gap_history.append({
                "date": pd.Timestamp(index).strftime("%Y-%m-%d"),
                "price": round(float(price), 2),
                "fair_value_mid": round(float(fair_value_mid), 2),
                "gap_pct": round(gap_pct, 2),
            })

        return {
            "symbol": symbol,
            "period": period,
            "history": gap_history,
            "summary": {
                "max_gap_pct": max(item["gap_pct"] for item in gap_history),
                "min_gap_pct": min(item["gap_pct"] for item in gap_history),
                "latest_gap_pct": gap_history[-1]["gap_pct"],
            },
        }

    def build_peer_comparison(
        self,
        symbol: str,
        candidate_symbols: Iterable[str],
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Build a lightweight peer set using sector/industry similarity and valuation context."""
        data_manager = self.valuation_model.data_manager
        target_fundamentals = data_manager.get_fundamental_data(symbol)
        if "error" in target_fundamentals:
            return {
                "symbol": symbol,
                "peers": [],
                "error": target_fundamentals["error"],
            }

        target_sector = target_fundamentals.get("sector", "")
        target_industry = target_fundamentals.get("industry", "")

        target_market_cap = float(target_fundamentals.get("market_cap") or 0)

        def build_row(peer_symbol: str) -> Optional[Dict[str, Any]]:
            peer_symbol = str(peer_symbol or "").strip().upper()
            if not peer_symbol:
                return None

            fundamentals = target_fundamentals if peer_symbol == symbol else data_manager.get_fundamental_data(peer_symbol)
            if "error" in fundamentals:
                return None

            same_sector = not target_sector or fundamentals.get("sector") == target_sector
            same_industry = target_industry and fundamentals.get("industry") == target_industry
            if peer_symbol != symbol and not same_sector and not same_industry:
                return None

            valuation = self.valuation_model.analyze(peer_symbol)
            fair_value = valuation.get("fair_value", {}) or {}
            current_price = valuation.get("current_price")
            fair_value_mid = fair_value.get("mid")
            premium_discount = None
            if fair_value_mid and current_price:
                premium_discount = round(((float(current_price) - float(fair_value_mid)) / float(fair_value_mid)) * 100, 1)

            market_cap = fundamentals.get("market_cap")
            market_cap_value = float(market_cap or 0)
            same_sector = fundamentals.get("sector", "") == target_sector if target_sector else True
            same_industry = fundamentals.get("industry", "") == target_industry if target_industry else False
            size_distance = 99.0
            if target_market_cap > 0 and market_cap_value > 0:
                size_distance = abs(np.log(market_cap_value / target_market_cap))

            return {
                "symbol": peer_symbol,
                "company_name": fundamentals.get("company_name", ""),
                "sector": fundamentals.get("sector", ""),
                "industry": fundamentals.get("industry", ""),
                "market_cap": market_cap,
                "current_price": current_price,
                "fair_value": fair_value_mid,
                "premium_discount": premium_discount,
                "pe_ratio": fundamentals.get("pe_ratio"),
                "price_to_book": fundamentals.get("price_to_book"),
                "price_to_sales": fundamentals.get("price_to_sales"),
                "enterprise_to_ebitda": fundamentals.get("enterprise_to_ebitda"),
                "is_target": peer_symbol == symbol,
                "same_sector": same_sector,
                "same_industry": same_industry,
                "size_distance": round(float(size_distance), 4) if size_distance != 99.0 else None,
            }

        normalized = []
        seen = set()
        for raw_symbol in [symbol, *(candidate_symbols or [])]:
            peer_symbol = str(raw_symbol or "").strip().upper()
            if not peer_symbol or peer_symbol in seen:
                continue
            seen.add(peer_symbol)
            normalized.append(peer_symbol)

        rows = []
        with ThreadPoolExecutor(max_workers=max(1, min(len(normalized), 6))) as executor:
            future_map = {executor.submit(build_row, peer_symbol): peer_symbol for peer_symbol in normalized}
            for future in as_completed(future_map):
                row = future.result()
                if row:
                    rows.append(row)

        peers = sorted(
            [row for row in rows if not row.get("is_target")],
            key=lambda item: (
                int(bool(item.get("same_industry"))),
                int(bool(item.get("same_sector"))),
                -(float(item.get("size_distance")) if item.get("size_distance") is not None else 999.0),
                float(item.get("market_cap") or 0),
                item.get("symbol", ""),
            ),
            reverse=True,
        )[: max(int(limit or 0), 0)]
        target_row = next((row for row in rows if row.get("is_target")), build_row(symbol))

        return {
            "symbol": symbol,
            "target": target_row,
            "peers": peers,
            "sector": target_sector,
            "industry": target_industry,
            "summary": {
                "peer_count": len(peers),
                "median_peer_pe": round(float(pd.Series([item.get("pe_ratio") for item in peers]).dropna().median()), 2)
                if peers and pd.Series([item.get("pe_ratio") for item in peers]).dropna().size
                else None,
                "median_peer_ps": round(float(pd.Series([item.get("price_to_sales") for item in peers]).dropna().median()), 2)
                if peers and pd.Series([item.get("price_to_sales") for item in peers]).dropna().size
                else None,
                "same_industry_count": sum(1 for item in peers if item.get("same_industry")),
            },
            "candidate_count": len(normalized) - 1 if normalized else 0,
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

    def _build_screening_row(self, analysis: Dict[str, Any], period: str) -> Dict[str, Any]:
        """Create a compact screener row from a full pricing analysis result."""
        if analysis.get("error"):
            return {
                "symbol": analysis.get("symbol"),
                "error": analysis.get("error"),
            }

        gap = analysis.get("gap_analysis", {}) or {}
        implications = analysis.get("implications", {}) or {}
        valuation = analysis.get("valuation", {}) or {}
        drivers_meta = analysis.get("deviation_drivers", {}) or {}
        primary_driver = drivers_meta.get("primary_driver") or {}
        alignment = implications.get("factor_alignment", {}) or {}
        confidence_score = float(implications.get("confidence_score") or 0)
        gap_pct = gap.get("gap_pct")
        score = self._screening_score(
            gap_pct=gap_pct,
            confidence_score=confidence_score,
            primary_view=implications.get("primary_view"),
            alignment_status=alignment.get("status"),
        )

        return {
            "symbol": analysis.get("symbol"),
            "company_name": valuation.get("company_name"),
            "period": period,
            "screening_score": score,
            "current_price": gap.get("current_price"),
            "fair_value": gap.get("fair_value_mid"),
            "gap_pct": gap_pct,
            "direction": gap.get("direction"),
            "severity": gap.get("severity"),
            "severity_label": gap.get("severity_label"),
            "primary_view": implications.get("primary_view"),
            "confidence": implications.get("confidence"),
            "confidence_score": confidence_score,
            "factor_alignment_status": alignment.get("status"),
            "factor_alignment_label": alignment.get("label"),
            "factor_alignment_summary": alignment.get("summary"),
            "price_source": valuation.get("current_price_source"),
            "primary_driver": primary_driver.get("factor"),
            "primary_driver_reason": primary_driver.get("ranking_reason"),
            "summary": analysis.get("summary"),
        }

    def _screening_score(
        self,
        gap_pct: Optional[float],
        confidence_score: float,
        primary_view: Optional[str],
        alignment_status: Optional[str],
    ) -> float:
        """Estimate how actionable a pricing opportunity is for rank ordering."""
        base_score = abs(float(gap_pct or 0)) * max(float(confidence_score or 0), 0.2)
        alignment_bonus = {
            "aligned": 4.0,
            "partial": 1.5,
            "neutral": 0.0,
            "conflict": -4.0,
        }.get(alignment_status, 0.0)
        actionable_bonus = 2.0 if primary_view in {"高估", "低估"} else 0.0
        return round(max(base_score + alignment_bonus + actionable_bonus, 0.0), 2)

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
        """Return a user-facing explanation for why this driver is primary."""
        impact = driver.get("impact")
        factor = driver.get("factor", "该因素")
        if impact in {"positive", "negative"}:
            if impact == "positive":
                return "Alpha 贡献最显著，说明超额收益是当前定价偏差的主要来源"
            return "负 Alpha 拖累最明显，说明风险调整后收益承压是当前定价偏差的主要来源"
        if impact in {"risk", "defensive"}:
            if impact == "risk":
                return "Beta 明显高于市场中性水平，说明系统性风险溢价是当前定价偏差的核心来源"
            return "Beta 明显低于市场中性水平，说明防御属性带来的安全溢价是当前定价偏差的核心来源"
        if impact == "style":
            return f"{factor} 暴露最突出，说明风格定价是当前偏差的主要来源"
        if impact in {"overvalued", "undervalued"}:
            if impact == "overvalued":
                return "相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源"
            return "相对行业基准的估值折价最显著，说明倍数压缩是当前定价偏差的主要来源"
        return "该信号的影响幅度最大，因此被识别为当前定价偏差的主要来源"

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
        alignment_meta = self._build_alignment_meta(gap, factor, valuation)
        trade_setup = self._build_trade_setup(gap, valuation, alignment_meta, confidence_meta)

        return {
            "insights": insights,
            "risk_level": risk_level,
            "primary_view": "低估" if gap_pct and gap_pct < -10 else "高估" if gap_pct and gap_pct > 10 else "合理",
            "confidence": confidence_meta["level"],
            "confidence_score": confidence_meta["score"],
            "confidence_reasons": confidence_meta["reasons"],
            "confidence_breakdown": confidence_meta["components"],
            "factor_alignment": alignment_meta,
            "trade_setup": trade_setup,
        }

    def _assess_confidence(self, gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, Any]:
        """Estimate confidence from data quality, model coverage and valuation consistency."""
        return assess_confidence(gap, factor, valuation)

    def _build_trade_setup(
        self,
        gap: Dict,
        valuation: Dict,
        alignment_meta: Dict[str, Any],
        confidence_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a research-style scenario with target, risk boundary and reward ratio."""
        return build_trade_setup(gap, valuation, alignment_meta, confidence_meta)

    def _assess_factor_valuation_alignment(self, gap: Dict, factor: Dict, valuation: Dict) -> Optional[str]:
        """Check whether factor signal direction supports the valuation conclusion."""
        return assess_factor_valuation_alignment(gap, factor, valuation)

    def _resolve_valuation_view(self, gap: Dict, valuation: Dict) -> Optional[str]:
        return resolve_valuation_view(gap, valuation)

    def _resolve_factor_view(self, factor: Dict) -> Optional[str]:
        return resolve_factor_view(factor)

    def _build_alignment_meta(self, gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, str]:
        return build_alignment_meta(gap, factor, valuation)

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
