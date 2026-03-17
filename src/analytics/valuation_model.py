"""
内在价值估值模型
实现 DCF（现金流折现）和可比公司估值法，提供公允价值区间分析
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

from src.data.data_manager import DataManager

logger = logging.getLogger(__name__)


class ValuationModel:
    """
    内在价值估值引擎
    整合 DCF 和可比估值法，输出公允价值区间
    """

    def __init__(self):
        self.data_manager = DataManager()

    def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        综合估值分析

        Args:
            symbol: 股票代码

        Returns:
            包含 DCF、可比估值和综合公允价值的字典
        """
        try:
            fundamentals = self.data_manager.get_fundamental_data(symbol)

            if "error" in fundamentals:
                return self._empty_result(f"基本面数据获取失败: {fundamentals['error']}")

            current_price = fundamentals.get("52w_high", 0)
            # 尝试获取实时价格
            try:
                latest = self.data_manager.get_latest_price(symbol)
                if "error" not in latest:
                    current_price = latest.get("price", current_price)
            except Exception:
                pass

            if current_price <= 0:
                return self._empty_result("无法获取当前价格")

            # DCF 估值
            dcf_result = self._dcf_valuation(fundamentals, current_price)

            # 可比估值法
            comparable_result = self._comparable_valuation(fundamentals, current_price)

            # 综合估值
            fair_value = self._composite_valuation(dcf_result, comparable_result)

            # 估值判断
            valuation_status = self._assess_valuation_status(current_price, fair_value)

            return {
                "symbol": symbol,
                "company_name": fundamentals.get("company_name", ""),
                "sector": fundamentals.get("sector", ""),
                "industry": fundamentals.get("industry", ""),
                "current_price": round(current_price, 2),
                "dcf": dcf_result,
                "comparable": comparable_result,
                "fair_value": fair_value,
                "valuation_status": valuation_status,
                "summary": self._generate_summary(current_price, fair_value, valuation_status)
            }

        except Exception as e:
            logger.error(f"估值分析出错 {symbol}: {e}", exc_info=True)
            return self._empty_result(str(e))

    def _dcf_valuation(self, fundamentals: Dict, current_price: float) -> Dict[str, Any]:
        """
        DCF 现金流折现估值

        使用简化的两阶段 DCF 模型:
        - 阶段1: 高增长期 (5年)
        - 阶段2: 永续增长期 (终值)
        """
        try:
            market_cap = fundamentals.get("market_cap", 0)
            pe = fundamentals.get("pe_ratio", 0)
            revenue_growth = fundamentals.get("revenue_growth", 0)
            profit_margin = fundamentals.get("profit_margin", 0)
            beta = fundamentals.get("beta", 1.0)

            if market_cap <= 0 or pe <= 0:
                return {"error": "缺少关键财务数据（市值或PE）", "intrinsic_value": None}

            # 估算当前净利润
            earnings = market_cap / pe if pe > 0 else 0
            if earnings <= 0:
                return {"error": "净利润为负，DCF不适用", "intrinsic_value": None}

            # 估算自由现金流 (FCF ≈ 净利润 * 0.8，粗略估计)
            fcf = earnings * 0.8

            # WACC 估算
            risk_free_rate = 0.04        # 无风险利率 (10年期美债)
            market_premium = 0.06        # 市场溢价
            cost_of_equity = risk_free_rate + beta * market_premium
            wacc = max(cost_of_equity * 0.85, 0.06)  # 简化WACC (假设少量债务)

            # 增长率
            if revenue_growth and revenue_growth > 0:
                growth_rate = min(revenue_growth, 0.30)  # 上限30%
            else:
                growth_rate = 0.05  # 默认5%

            terminal_growth = 0.025  # 永续增长率 2.5%

            # 阶段1: 5年高增长期 FCF 折现
            pv_fcfs = 0
            projected_fcfs = []
            for year in range(1, 6):
                # 增长率逐年衰减
                decay = growth_rate * (1 - (year - 1) * 0.15)
                yearly_growth = max(decay, terminal_growth)
                fcf *= (1 + yearly_growth)
                pv = fcf / ((1 + wacc) ** year)
                pv_fcfs += pv
                projected_fcfs.append({
                    "year": year,
                    "fcf": round(fcf, 0),
                    "growth_rate": round(yearly_growth, 4),
                    "pv": round(pv, 0)
                })

            # 阶段2: 终值 (Gordon Growth Model)
            terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
            pv_terminal = terminal_value / ((1 + wacc) ** 5)

            # 企业价值
            enterprise_value = pv_fcfs + pv_terminal

            # 转换为每股价值 (企业价值 / 市值 * 当前价格)
            intrinsic_value = (enterprise_value / market_cap) * current_price if market_cap > 0 else 0

            return {
                "intrinsic_value": round(intrinsic_value, 2),
                "enterprise_value": round(enterprise_value, 0),
                "pv_fcfs": round(pv_fcfs, 0),
                "pv_terminal": round(pv_terminal, 0),
                "terminal_pct": round(pv_terminal / enterprise_value * 100, 1) if enterprise_value > 0 else 0,
                "assumptions": {
                    "wacc": round(wacc, 4),
                    "initial_growth": round(growth_rate, 4),
                    "terminal_growth": terminal_growth,
                    "fcf_margin": 0.8
                },
                "projected_fcfs": projected_fcfs,
                "premium_discount": round((current_price - intrinsic_value) / intrinsic_value * 100, 1) if intrinsic_value > 0 else None
            }

        except Exception as e:
            logger.error(f"DCF 估值出错: {e}")
            return {"error": str(e), "intrinsic_value": None}

    def _comparable_valuation(self, fundamentals: Dict, current_price: float) -> Dict[str, Any]:
        """
        可比公司估值法
        使用 P/E、EV/EBITDA、P/B 倍数法
        """
        try:
            pe = fundamentals.get("pe_ratio", 0)
            forward_pe = fundamentals.get("forward_pe", 0)
            pb = fundamentals.get("price_to_book", 0)
            market_cap = fundamentals.get("market_cap", 0)
            sector = fundamentals.get("sector", "")

            # 行业基准估值倍数 (简化版，实际应根据行业细分)
            sector_benchmarks = {
                "Technology": {"pe": 28, "pb": 6.0, "ev_ebitda": 20},
                "Healthcare": {"pe": 22, "pb": 4.0, "ev_ebitda": 15},
                "Financial Services": {"pe": 14, "pb": 1.5, "ev_ebitda": 10},
                "Consumer Cyclical": {"pe": 20, "pb": 3.5, "ev_ebitda": 14},
                "Consumer Defensive": {"pe": 22, "pb": 4.0, "ev_ebitda": 15},
                "Energy": {"pe": 12, "pb": 1.8, "ev_ebitda": 7},
                "Industrials": {"pe": 18, "pb": 3.0, "ev_ebitda": 12},
                "Real Estate": {"pe": 30, "pb": 2.0, "ev_ebitda": 18},
                "Utilities": {"pe": 18, "pb": 2.0, "ev_ebitda": 12},
                "Communication Services": {"pe": 20, "pb": 3.0, "ev_ebitda": 12},
                "Basic Materials": {"pe": 15, "pb": 2.0, "ev_ebitda": 9},
            }

            benchmark = sector_benchmarks.get(sector, {"pe": 20, "pb": 3.0, "ev_ebitda": 13})

            valuations = []

            # P/E 倍数估值
            if pe > 0 and market_cap > 0:
                earnings = market_cap / pe
                pe_fair_value = (benchmark["pe"] / pe) * current_price
                valuations.append({
                    "method": "P/E 倍数法",
                    "current_multiple": round(pe, 2),
                    "benchmark_multiple": benchmark["pe"],
                    "fair_value": round(pe_fair_value, 2),
                    "weight": 0.4
                })

            # Forward P/E 估值
            if forward_pe > 0:
                fpe_fair_value = (benchmark["pe"] * 0.9 / forward_pe) * current_price  # Forward通常打折
                valuations.append({
                    "method": "Forward P/E 倍数法",
                    "current_multiple": round(forward_pe, 2),
                    "benchmark_multiple": round(benchmark["pe"] * 0.9, 2),
                    "fair_value": round(fpe_fair_value, 2),
                    "weight": 0.3
                })

            # P/B 倍数估值
            if pb > 0:
                pb_fair_value = (benchmark["pb"] / pb) * current_price
                valuations.append({
                    "method": "P/B 倍数法",
                    "current_multiple": round(pb, 2),
                    "benchmark_multiple": benchmark["pb"],
                    "fair_value": round(pb_fair_value, 2),
                    "weight": 0.3
                })

            if not valuations:
                return {"error": "缺少估值所需的财务指标", "fair_value": None}

            # 加权计算公允价值
            total_weight = sum(v["weight"] for v in valuations)
            weighted_fv = sum(v["fair_value"] * v["weight"] for v in valuations) / total_weight

            return {
                "fair_value": round(weighted_fv, 2),
                "sector": sector,
                "sector_benchmark": benchmark,
                "methods": valuations,
                "premium_discount": round((current_price - weighted_fv) / weighted_fv * 100, 1) if weighted_fv > 0 else None
            }

        except Exception as e:
            logger.error(f"可比估值出错: {e}")
            return {"error": str(e), "fair_value": None}

    def _composite_valuation(self, dcf: Dict, comparable: Dict) -> Dict[str, Any]:
        """综合估值：整合 DCF 和可比估值"""
        values = []
        weights = []

        dcf_val = dcf.get("intrinsic_value")
        if dcf_val and dcf_val > 0:
            values.append(dcf_val)
            weights.append(0.5)

        comp_val = comparable.get("fair_value")
        if comp_val and comp_val > 0:
            values.append(comp_val)
            weights.append(0.5)

        if not values:
            return {"mid": None, "low": None, "high": None, "method": "无可用估值数据"}

        # 归一化权重
        total_w = sum(weights)
        fair_value = sum(v * w for v, w in zip(values, weights)) / total_w

        # 估值区间 (±15%)
        return {
            "mid": round(fair_value, 2),
            "low": round(fair_value * 0.85, 2),
            "high": round(fair_value * 1.15, 2),
            "method": "DCF + 可比估值加权" if len(values) == 2 else ("DCF" if dcf_val else "可比估值"),
            "dcf_weight": weights[0] if dcf_val else 0,
            "comparable_weight": weights[-1] if comp_val else 0
        }

    def _assess_valuation_status(self, current_price: float, fair_value: Dict) -> Dict[str, Any]:
        """评估估值状态"""
        mid = fair_value.get("mid")
        if not mid or mid <= 0:
            return {"status": "unknown", "deviation": 0, "label": "数据不足"}

        deviation = (current_price - mid) / mid

        if deviation < -0.25:
            status, label = "severely_undervalued", "严重低估"
        elif deviation < -0.10:
            status, label = "undervalued", "低估"
        elif deviation < 0.10:
            status, label = "fairly_valued", "合理估值"
        elif deviation < 0.25:
            status, label = "overvalued", "高估"
        else:
            status, label = "severely_overvalued", "严重高估"

        return {
            "status": status,
            "deviation": round(deviation, 4),
            "deviation_pct": round(deviation * 100, 1),
            "label": label,
            "in_fair_range": fair_value.get("low", 0) <= current_price <= fair_value.get("high", float("inf"))
        }

    def _generate_summary(self, current_price: float, fair_value: Dict, status: Dict) -> str:
        """生成估值摘要"""
        mid = fair_value.get("mid")
        if not mid:
            return "估值数据不足"

        label = status.get("label", "未知")
        dev_pct = status.get("deviation_pct", 0)
        method = fair_value.get("method", "")

        if dev_pct > 0:
            return f"当前价格${current_price:.2f}，{method}公允价值${mid:.2f}，溢价{abs(dev_pct):.1f}%（{label}）"
        else:
            return f"当前价格${current_price:.2f}，{method}公允价值${mid:.2f}，折价{abs(dev_pct):.1f}%（{label}）"

    def _empty_result(self, reason: str) -> Dict[str, Any]:
        return {
            "symbol": "",
            "company_name": "",
            "current_price": 0,
            "dcf": {"error": reason, "intrinsic_value": None},
            "comparable": {"error": reason, "fair_value": None},
            "fair_value": {"mid": None, "low": None, "high": None},
            "valuation_status": {"status": "unknown", "label": reason},
            "summary": reason
        }
