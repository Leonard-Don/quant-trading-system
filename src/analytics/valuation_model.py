"""
内在价值估值模型
实现 DCF（现金流折现）和可比公司估值法，提供公允价值区间分析
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from src.data.data_manager import DataManager

logger = logging.getLogger(__name__)

DEFAULT_SECTOR_BENCHMARKS = {
    "Technology": {"pe": 28, "pb": 6.0, "ps": 7.0, "ev_ebitda": 20, "ev_revenue": 8.0, "peg": 1.8},
    "Healthcare": {"pe": 22, "pb": 4.0, "ps": 5.0, "ev_ebitda": 15, "ev_revenue": 5.5, "peg": 1.6},
    "Financial Services": {"pe": 14, "pb": 1.5, "ps": 3.0, "ev_ebitda": 10, "ev_revenue": 4.0, "peg": 1.3},
    "Consumer Cyclical": {"pe": 20, "pb": 3.5, "ps": 2.5, "ev_ebitda": 14, "ev_revenue": 2.8, "peg": 1.5},
    "Consumer Defensive": {"pe": 22, "pb": 4.0, "ps": 2.8, "ev_ebitda": 15, "ev_revenue": 3.2, "peg": 1.7},
    "Energy": {"pe": 12, "pb": 1.8, "ps": 1.6, "ev_ebitda": 7, "ev_revenue": 1.7, "peg": 1.1},
    "Industrials": {"pe": 18, "pb": 3.0, "ps": 2.2, "ev_ebitda": 12, "ev_revenue": 2.5, "peg": 1.4},
    "Real Estate": {"pe": 30, "pb": 2.0, "ps": 4.0, "ev_ebitda": 18, "ev_revenue": 6.0, "peg": 1.5},
    "Utilities": {"pe": 18, "pb": 2.0, "ps": 2.3, "ev_ebitda": 12, "ev_revenue": 3.0, "peg": 1.2},
    "Communication Services": {"pe": 20, "pb": 3.0, "ps": 3.2, "ev_ebitda": 12, "ev_revenue": 3.6, "peg": 1.5},
    "Basic Materials": {"pe": 15, "pb": 2.0, "ps": 1.8, "ev_ebitda": 9, "ev_revenue": 2.0, "peg": 1.2},
}
DEFAULT_BENCHMARK = {"pe": 20, "pb": 3.0, "ps": 2.5, "ev_ebitda": 13, "ev_revenue": 3.0, "peg": 1.5}
DEFAULT_PEER_BENCHMARK_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AMD", "AVGO", "NFLX",
    "PLTR", "SNOW", "CRM", "ORCL", "ADBE", "TSLA", "JPM", "GS", "XOM",
    "CVX", "NEE", "UNH", "PFE", "LLY", "COST", "WMT", "HD", "CAT",
]


class ValuationModel:
    """
    内在价值估值引擎
    整合 DCF 和可比估值法，输出公允价值区间
    """

    def __init__(self):
        self.data_manager = DataManager()

    def analyze(self, symbol: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

            price_info = self._resolve_current_price(symbol, fundamentals)
            current_price = price_info.get("price", 0)
            if current_price <= 0:
                return self._empty_result("无法获取当前价格")

            # DCF 估值
            dcf_result = self._dcf_valuation(fundamentals, current_price, overrides=overrides)
            monte_carlo_result = self._monte_carlo_valuation(fundamentals, current_price, dcf_result)

            # 可比估值法
            comparable_result = self._comparable_valuation(symbol, fundamentals, current_price)

            # 综合估值
            fair_value = self._composite_valuation(dcf_result, comparable_result, overrides=overrides)

            # 估值判断
            valuation_status = self._assess_valuation_status(current_price, fair_value)

            return {
                "symbol": symbol,
                "company_name": fundamentals.get("company_name", ""),
                "sector": fundamentals.get("sector", ""),
                "industry": fundamentals.get("industry", ""),
                "current_price": round(current_price, 2),
                "current_price_source": price_info.get("source", "unavailable"),
                "analysis_overrides": overrides or {},
                "dcf": dcf_result,
                "monte_carlo": monte_carlo_result,
                "comparable": comparable_result,
                "fair_value": fair_value,
                "valuation_status": valuation_status,
                "summary": self._generate_summary(current_price, fair_value, valuation_status)
            }

        except Exception as e:
            logger.error(f"估值分析出错 {symbol}: {e}", exc_info=True)
            return self._empty_result(str(e))

    def _resolve_current_price(self, symbol: str, fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a usable spot price without falling back to 52-week extremes."""
        try:
            latest = self.data_manager.get_latest_price(symbol)
            if "error" not in latest:
                latest_price = float(latest.get("price") or 0)
                if latest_price > 0:
                    return {"price": latest_price, "source": "live"}
        except Exception:
            logger.debug("Latest price lookup failed for %s", symbol, exc_info=True)

        for key, source in (
            ("current_price", "fundamental_current_price"),
            ("regular_market_price", "fundamental_regular_market_price"),
            ("previous_close", "fundamental_previous_close"),
        ):
            value = float(fundamentals.get(key) or 0)
            if value > 0:
                return {"price": value, "source": source}

        try:
            recent_data = self.data_manager.get_historical_data(symbol, period="5d")
            if not recent_data.empty and "close" in recent_data.columns:
                close_series = recent_data["close"].dropna()
                if not close_series.empty:
                    return {"price": float(close_series.iloc[-1]), "source": "historical_close"}
        except Exception:
            logger.debug("Historical close fallback failed for %s", symbol, exc_info=True)

        return {"price": 0.0, "source": "unavailable"}

    def _dcf_valuation(self, fundamentals: Dict, current_price: float, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            beta = fundamentals.get("beta", 1.0)

            if market_cap <= 0 or pe <= 0:
                return {"error": "缺少关键财务数据（市值或PE）", "intrinsic_value": None}

            # 估算当前净利润
            earnings = market_cap / pe if pe > 0 else 0
            if earnings <= 0:
                return {"error": "净利润为负，DCF不适用", "intrinsic_value": None}

            overrides = overrides or {}

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
            base_wacc = float(overrides.get("wacc", wacc))
            base_growth = float(overrides.get("initial_growth", growth_rate))
            base_terminal_growth = float(overrides.get("terminal_growth", terminal_growth))
            base_fcf_margin = float(overrides.get("fcf_margin", 0.80))
            scenario_configs = [
                {
                    "name": "bear",
                    "label": "悲观",
                    "description": "更高折现率、更慢增长和更保守的现金流转化率",
                    "wacc": base_wacc + 0.015,
                    "initial_growth": max(base_growth - 0.04, 0.02),
                    "terminal_growth": max(base_terminal_growth - 0.005, 0.015),
                    "fcf_margin": max(base_fcf_margin - 0.05, 0.55),
                },
                {
                    "name": "base",
                    "label": "基准",
                    "description": "沿用当前默认假设的基础情景",
                    "wacc": base_wacc,
                    "initial_growth": base_growth,
                    "terminal_growth": base_terminal_growth,
                    "fcf_margin": base_fcf_margin,
                },
                {
                    "name": "bull",
                    "label": "乐观",
                    "description": "更低折现率、更快增长和更积极的现金流转化率",
                    "wacc": max(base_wacc - 0.01, 0.055),
                    "initial_growth": min(base_growth + 0.04, 0.35),
                    "terminal_growth": min(base_terminal_growth + 0.005, 0.035),
                    "fcf_margin": min(base_fcf_margin + 0.05, 0.92),
                },
            ]

            scenario_results = [
                self._run_dcf_case(
                    earnings=earnings,
                    market_cap=market_cap,
                    current_price=current_price,
                    scenario=config,
                )
                for config in scenario_configs
            ]
            base_case = next((item for item in scenario_results if item["name"] == "base"), scenario_results[0])

            return {
                "intrinsic_value": base_case["intrinsic_value"],
                "enterprise_value": base_case["enterprise_value"],
                "pv_fcfs": base_case["pv_fcfs"],
                "pv_terminal": base_case["pv_terminal"],
                "terminal_pct": base_case["terminal_pct"],
                "assumptions": base_case["assumptions"],
                "projected_fcfs": base_case["projected_fcfs"],
                "premium_discount": base_case["premium_discount"],
                "scenarios": [
                    {
                        "name": item["name"],
                        "label": item["label"],
                        "description": item["description"],
                        "intrinsic_value": item["intrinsic_value"],
                        "premium_discount": item["premium_discount"],
                        "assumptions": item["assumptions"],
                    }
                    for item in scenario_results
                ],
                "scenario_range": {
                    "low": min(item["intrinsic_value"] for item in scenario_results if item["intrinsic_value"] is not None),
                    "high": max(item["intrinsic_value"] for item in scenario_results if item["intrinsic_value"] is not None),
                },
                "confidence_weight": 0.55,
                "sensitivity_anchor": {
                    "wacc": round(base_wacc, 4),
                    "initial_growth": round(base_growth, 4),
                    "terminal_growth": round(base_terminal_growth, 4),
                    "fcf_margin": round(base_fcf_margin, 2),
                },
            }

        except Exception as e:
            logger.error(f"DCF 估值出错: {e}")
            return {"error": str(e), "intrinsic_value": None}

    def _run_dcf_case(self, earnings: float, market_cap: float, current_price: float, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single DCF scenario with its own growth, discount and cash conversion assumptions."""
        fcf = earnings * float(scenario["fcf_margin"])
        wacc = max(float(scenario["wacc"]), float(scenario["terminal_growth"]) + 0.02)
        terminal_growth = min(float(scenario["terminal_growth"]), wacc - 0.02)
        initial_growth = float(scenario["initial_growth"])

        pv_fcfs = 0.0
        projected_fcfs = []
        for year in range(1, 6):
            decay = initial_growth * (1 - (year - 1) * 0.15)
            yearly_growth = max(decay, terminal_growth)
            fcf *= (1 + yearly_growth)
            pv = fcf / ((1 + wacc) ** year)
            pv_fcfs += pv
            projected_fcfs.append({
                "year": year,
                "fcf": round(fcf, 0),
                "growth_rate": round(yearly_growth, 4),
                "pv": round(pv, 0),
            })

        terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** 5)
        enterprise_value = pv_fcfs + pv_terminal
        intrinsic_value = (enterprise_value / market_cap) * current_price if market_cap > 0 else 0

        return {
            "name": scenario["name"],
            "label": scenario["label"],
            "description": scenario["description"],
            "intrinsic_value": round(intrinsic_value, 2),
            "enterprise_value": round(enterprise_value, 0),
            "pv_fcfs": round(pv_fcfs, 0),
            "pv_terminal": round(pv_terminal, 0),
            "terminal_pct": round(pv_terminal / enterprise_value * 100, 1) if enterprise_value > 0 else 0,
            "assumptions": {
                "wacc": round(wacc, 4),
                "initial_growth": round(initial_growth, 4),
                "terminal_growth": round(terminal_growth, 4),
                "fcf_margin": round(float(scenario["fcf_margin"]), 2),
            },
            "projected_fcfs": projected_fcfs,
            "premium_discount": round((current_price - intrinsic_value) / intrinsic_value * 100, 1) if intrinsic_value > 0 else None,
        }

    def _monte_carlo_valuation(self, fundamentals: Dict[str, Any], current_price: float, dcf_result: Dict[str, Any]) -> Dict[str, Any]:
        """基于 DCF 锚点做轻量蒙特卡洛估值分布。"""
        try:
            anchor = dcf_result.get("sensitivity_anchor", {}) or {}
            market_cap = fundamentals.get("market_cap", 0)
            pe = fundamentals.get("pe_ratio", 0)
            if not anchor or market_cap <= 0 or pe <= 0:
                return {"error": "缺少 Monte Carlo 所需锚点", "distribution": []}

            earnings = market_cap / pe if pe > 0 else 0
            if earnings <= 0:
                return {"error": "净利润为负，Monte Carlo 不适用", "distribution": []}

            rng = np.random.default_rng(42)
            sample_count = 200
            simulations = []
            for _ in range(sample_count):
                scenario = {
                    "name": "simulation",
                    "label": "模拟",
                    "description": "Monte Carlo simulation",
                    "wacc": float(np.clip(rng.normal(anchor.get("wacc", 0.08), 0.008), 0.055, 0.16)),
                    "initial_growth": float(np.clip(rng.normal(anchor.get("initial_growth", 0.10), 0.03), 0.02, 0.35)),
                    "terminal_growth": float(np.clip(rng.normal(anchor.get("terminal_growth", 0.025), 0.004), 0.01, 0.04)),
                    "fcf_margin": float(np.clip(rng.normal(anchor.get("fcf_margin", 0.8), 0.06), 0.5, 0.95)),
                }
                case = self._run_dcf_case(earnings, market_cap, current_price, scenario)
                if case.get("intrinsic_value"):
                    simulations.append(float(case["intrinsic_value"]))

            if not simulations:
                return {"error": "Monte Carlo 模拟失败", "distribution": []}

            series = pd.Series(simulations)
            bins = pd.cut(series, bins=10)
            histogram = (
                pd.DataFrame({"bucket": bins.astype(str), "value": series})
                .groupby("bucket", observed=False)
                .size()
                .reset_index(name="count")
                .to_dict("records")
            )

            return {
                "sample_count": len(simulations),
                "mean": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
                "p10": round(float(series.quantile(0.10)), 2),
                "p50": round(float(series.quantile(0.50)), 2),
                "p90": round(float(series.quantile(0.90)), 2),
                "std": round(float(series.std(ddof=0)), 2),
                "distribution": histogram,
            }
        except Exception as e:
            logger.error(f"Monte Carlo 估值出错: {e}")
            return {"error": str(e), "distribution": []}

    def _comparable_valuation(self, symbol: str, fundamentals: Dict, current_price: float) -> Dict[str, Any]:
        """
        可比公司估值法
        使用 P/E、EV/EBITDA、EV/Revenue、PEG、P/B 等倍数法
        """
        try:
            pe = fundamentals.get("pe_ratio", 0)
            forward_pe = fundamentals.get("forward_pe", 0)
            peg = fundamentals.get("peg_ratio", 0)
            pb = fundamentals.get("price_to_book", 0)
            ps = fundamentals.get("price_to_sales", 0)
            ev_ebitda = fundamentals.get("enterprise_to_ebitda", 0)
            ev_revenue = fundamentals.get("enterprise_to_revenue", 0)
            market_cap = fundamentals.get("market_cap", 0)
            sector = fundamentals.get("sector", "")
            benchmark = self._benchmark_for_sector(symbol, fundamentals)

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

            if ps > 0:
                ps_fair_value = (benchmark["ps"] / ps) * current_price
                valuations.append({
                    "method": "P/S 倍数法",
                    "current_multiple": round(ps, 2),
                    "benchmark_multiple": benchmark["ps"],
                    "fair_value": round(ps_fair_value, 2),
                    "weight": 0.2,
                })

            if ev_ebitda > 0:
                ev_fair_value = (benchmark["ev_ebitda"] / ev_ebitda) * current_price
                valuations.append({
                    "method": "EV/EBITDA 倍数法",
                    "current_multiple": round(ev_ebitda, 2),
                    "benchmark_multiple": benchmark["ev_ebitda"],
                    "fair_value": round(ev_fair_value, 2),
                    "weight": 0.25,
                })

            if ev_revenue > 0:
                ev_revenue_fair_value = (benchmark["ev_revenue"] / ev_revenue) * current_price
                valuations.append({
                    "method": "EV/Revenue 倍数法",
                    "current_multiple": round(ev_revenue, 2),
                    "benchmark_multiple": benchmark["ev_revenue"],
                    "fair_value": round(ev_revenue_fair_value, 2),
                    "weight": 0.22,
                })

            if peg and peg > 0:
                peg_fair_value = (benchmark["peg"] / peg) * current_price
                valuations.append({
                    "method": "PEG 倍数法",
                    "current_multiple": round(peg, 2),
                    "benchmark_multiple": benchmark["peg"],
                    "fair_value": round(peg_fair_value, 2),
                    "weight": 0.18,
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
                "benchmark_source": benchmark.get("source_key", "static_sector_template"),
                "benchmark_peer_count": benchmark.get("peer_count", 0),
                "benchmark_peer_symbols": benchmark.get("peer_symbols", []),
                "methods": valuations,
                "confidence_weight": round(min(0.65, 0.18 * len(valuations)), 2),
                "warnings": self._benchmark_warnings(benchmark),
                "premium_discount": round((current_price - weighted_fv) / weighted_fv * 100, 1) if weighted_fv > 0 else None
            }

        except Exception as e:
            logger.error(f"可比估值出错: {e}")
            return {"error": str(e), "fair_value": None}

    def _composite_valuation(self, dcf: Dict, comparable: Dict, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """综合估值：整合 DCF 和可比估值"""
        overrides = overrides or {}
        values = []
        weights = []

        dcf_val = dcf.get("intrinsic_value")
        if dcf_val and dcf_val > 0:
            values.append(dcf_val)
            weights.append(float(overrides.get("dcf_weight", dcf.get("confidence_weight", 0.5))))

        comp_val = comparable.get("fair_value")
        if comp_val and comp_val > 0:
            values.append(comp_val)
            weights.append(float(overrides.get("comparable_weight", comparable.get("confidence_weight", 0.5))))

        if not values:
            return {"mid": None, "low": None, "high": None, "method": "无可用估值数据"}

        # 归一化权重
        total_w = sum(weights)
        fair_value = sum(v * w for v, w in zip(values, weights)) / total_w

        dcf_scenario_values = [
            float(item.get("intrinsic_value"))
            for item in (dcf.get("scenarios") or [])
            if item.get("intrinsic_value")
        ]
        comparable_values = [
            float(item.get("fair_value"))
            for item in (comparable.get("methods") or [])
            if item.get("fair_value")
        ]
        range_candidates = dcf_scenario_values + comparable_values
        if not range_candidates:
            range_candidates = [float(fair_value)]

        if len(range_candidates) == 1:
            low = round(fair_value * 0.85, 2)
            high = round(fair_value * 1.15, 2)
            range_basis = "fallback_band"
        else:
            low = round(min(range_candidates), 2)
            high = round(max(range_candidates), 2)
            if dcf_scenario_values and comparable_values:
                range_basis = "dcf_scenarios_and_multiples"
            elif dcf_scenario_values:
                range_basis = "dcf_scenarios"
            elif len(comparable_values) > 1:
                range_basis = "comparable_method_span"
            else:
                range_basis = "valuation_span"

        return {
            "mid": round(fair_value, 2),
            "low": low,
            "high": high,
            "method": "DCF + 可比估值加权" if len(values) == 2 else ("DCF" if dcf_val else "可比估值"),
            "dcf_weight": round((weights[0] / total_w), 2) if dcf_val else 0,
            "comparable_weight": round((weights[-1] / total_w), 2) if comp_val else 0,
            "range_basis": range_basis,
        }

    def build_sensitivity_analysis(self, symbol: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        valuation = self.analyze(symbol, overrides=overrides)
        dcf = valuation.get("dcf", {}) or {}
        anchor = dcf.get("sensitivity_anchor", {}) or {}
        if "error" in dcf or not anchor:
            return {
                "symbol": symbol,
                "error": dcf.get("error", "DCF 估值不可用"),
            }

        wacc_anchor = float(anchor.get("wacc") or 0)
        growth_anchor = float(anchor.get("initial_growth") or 0)
        matrix = []
        for growth_shift in (-0.02, 0.0, 0.02):
            row = {
                "growth": round(growth_anchor + growth_shift, 4),
                "cases": [],
            }
            for wacc_shift in (-0.01, 0.0, 0.01):
                case = self.analyze(
                    symbol,
                    overrides={
                        **(overrides or {}),
                        "wacc": round(wacc_anchor + wacc_shift, 4),
                        "initial_growth": round(growth_anchor + growth_shift, 4),
                    },
                )
                row["cases"].append({
                    "wacc": round(wacc_anchor + wacc_shift, 4),
                    "fair_value": case.get("fair_value", {}).get("mid"),
                })
            matrix.append(row)

        return {
            "symbol": symbol,
            "base": valuation,
            "applied_overrides": valuation.get("analysis_overrides", {}),
            "sensitivity_matrix": matrix,
        }

    def _benchmark_for_sector(self, symbol: str, fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        sector = fundamentals.get("sector", "")
        industry = fundamentals.get("industry", "")
        static_benchmark = DEFAULT_SECTOR_BENCHMARKS.get(sector, DEFAULT_BENCHMARK)
        metrics = {
            "pe": [],
            "pb": [],
            "ps": [],
            "ev_ebitda": [],
            "ev_revenue": [],
            "peg": [],
        }
        peer_symbols = []

        for peer_symbol in DEFAULT_PEER_BENCHMARK_SYMBOLS:
            if peer_symbol == symbol:
                continue
            peer = self.data_manager.get_fundamental_data(peer_symbol)
            if "error" in peer:
                continue
            if sector and peer.get("sector") != sector:
                continue
            if industry and peer.get("industry") and peer.get("industry") != industry and len(peer_symbols) >= 5:
                continue

            peer_symbols.append(peer_symbol)
            if float(peer.get("pe_ratio") or 0) > 0:
                metrics["pe"].append(float(peer["pe_ratio"]))
            if float(peer.get("price_to_book") or 0) > 0:
                metrics["pb"].append(float(peer["price_to_book"]))
            if float(peer.get("price_to_sales") or 0) > 0:
                metrics["ps"].append(float(peer["price_to_sales"]))
            if float(peer.get("enterprise_to_ebitda") or 0) > 0:
                metrics["ev_ebitda"].append(float(peer["enterprise_to_ebitda"]))
            if float(peer.get("enterprise_to_revenue") or 0) > 0:
                metrics["ev_revenue"].append(float(peer["enterprise_to_revenue"]))
            if float(peer.get("peg_ratio") or 0) > 0:
                metrics["peg"].append(float(peer["peg_ratio"]))

        dynamic = {}
        for key, fallback in static_benchmark.items():
            values = metrics.get(key, [])
            if len(values) >= 3:
                dynamic[key] = round(float(np.median(values)), 2)
            else:
                dynamic[key] = fallback

        has_dynamic = any(len(metrics[key]) >= 3 for key in metrics)
        return {
            **dynamic,
            "sector": sector or "Unknown",
            "industry": industry or "Unknown",
            "source_label": "Dynamic peer median" if has_dynamic else "Static sector template",
            "source_key": "dynamic_peer_median" if has_dynamic else "static_sector_template",
            "peer_count": len(peer_symbols),
            "peer_symbols": peer_symbols[:6],
        }

    def _benchmark_warnings(self, benchmark: Dict[str, Any]) -> list[str]:
        if benchmark.get("source_key") == "dynamic_peer_median":
            peers = ", ".join(benchmark.get("peer_symbols", [])[:4])
            return [f"行业基准倍数优先使用同行中位数；本次参考同行包括 {peers or '若干同板块标的'}。"]
        return ["行业基准倍数当前仍采用静态模板，应结合同行数据复核。"]

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
            "current_price_source": "unavailable",
            "dcf": {"error": reason, "intrinsic_value": None},
            "comparable": {"error": reason, "fair_value": None},
            "fair_value": {"mid": None, "low": None, "high": None},
            "valuation_status": {"status": "unknown", "label": reason},
            "summary": reason
        }
