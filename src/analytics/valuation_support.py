"""
估值模型 support helpers
提取 DCF / Monte Carlo / 现价解析 / 同行基准等纯辅助逻辑，
让主模型更聚焦在分析编排。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd


def resolve_current_price(data_manager: Any, symbol: str, fundamentals: Dict[str, Any], logger: Any) -> Dict[str, Any]:
    """Resolve a usable spot price without falling back to 52-week extremes."""
    try:
        latest = data_manager.get_latest_price(symbol)
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
        recent_data = data_manager.get_historical_data(symbol, period="5d")
        if not recent_data.empty and "close" in recent_data.columns:
            close_series = recent_data["close"].dropna()
            if not close_series.empty:
                return {"price": float(close_series.iloc[-1]), "source": "historical_close"}
    except Exception:
        logger.debug("Historical close fallback failed for %s", symbol, exc_info=True)

    return {"price": 0.0, "source": "unavailable"}


def build_dcf_scenario_configs(
    *,
    base_wacc: float,
    base_growth: float,
    base_terminal_growth: float,
    base_fcf_margin: float,
) -> list[Dict[str, Any]]:
    return [
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


def run_dcf_case(
    *,
    normalized_fcf: float,
    revenue_base: float,
    operating_margin: float,
    current_price: float,
    scenario: Dict[str, Any],
    equity_bridge: Dict[str, Any],
) -> Dict[str, Any]:
    """Run a single DCF scenario with its own growth, discount and cash conversion assumptions."""
    revenue = float(revenue_base)
    fcf = float(normalized_fcf) * float(scenario["fcf_margin"])
    wacc = max(float(scenario["wacc"]), float(scenario["terminal_growth"]) + 0.02)
    terminal_growth = min(float(scenario["terminal_growth"]), wacc - 0.02)
    initial_growth = float(scenario["initial_growth"])
    capex_ratio = float(equity_bridge.get("capex_ratio") or 0.04)
    wc_intensity = float(equity_bridge.get("working_capital_intensity") or 0.03)

    pv_fcfs = 0.0
    projected_fcfs = []
    for year in range(1, 6):
        decay = initial_growth * (1 - (year - 1) * 0.15)
        yearly_growth = max(decay, terminal_growth)
        previous_revenue = revenue
        revenue *= (1 + yearly_growth)
        incremental_revenue = max(revenue - previous_revenue, 0.0)
        operating_cash_flow = revenue * max(operating_margin, 0.05) * float(scenario["fcf_margin"])
        capex_drag = revenue * capex_ratio
        working_capital_drag = incremental_revenue * wc_intensity
        fcf = max(fcf * (1 + yearly_growth), operating_cash_flow - capex_drag - working_capital_drag)
        pv = fcf / ((1 + wacc) ** year)
        pv_fcfs += pv
        projected_fcfs.append({
            "year": year,
            "fcf": round(fcf, 0),
            "growth_rate": round(yearly_growth, 4),
            "pv": round(pv, 0),
            "revenue": round(revenue, 0),
            "capex": round(capex_drag, 0),
            "working_capital_investment": round(working_capital_drag, 0),
        })

    terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** 5)
    enterprise_value = pv_fcfs + pv_terminal
    net_debt = float(equity_bridge.get("net_debt") or 0.0)
    shares_outstanding = float(equity_bridge.get("shares_outstanding") or 0.0)
    equity_value = enterprise_value - net_debt
    intrinsic_value = equity_value / shares_outstanding if shares_outstanding > 0 else current_price

    return {
        "name": scenario["name"],
        "label": scenario["label"],
        "description": scenario["description"],
        "intrinsic_value": round(intrinsic_value, 2),
        "enterprise_value": round(enterprise_value, 0),
        "equity_value": round(equity_value, 0),
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


def monte_carlo_valuation(
    fundamentals: Dict[str, Any],
    current_price: float,
    dcf_result: Dict[str, Any],
    logger: Any,
) -> Dict[str, Any]:
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

        revenue = float(fundamentals.get("revenue") or 0)
        operating_margin = float(fundamentals.get("operating_margin") or fundamentals.get("profit_margin") or 0.18)
        free_cash_flow = float(fundamentals.get("free_cash_flow") or 0)
        operating_cash_flow = float(fundamentals.get("operating_cash_flow") or 0)
        capital_expenditure = abs(float(fundamentals.get("capital_expenditure") or 0))
        normalized_fcf = free_cash_flow
        if normalized_fcf <= 0 and operating_cash_flow > 0:
            normalized_fcf = operating_cash_flow - capital_expenditure
        if normalized_fcf <= 0:
            normalized_fcf = earnings * anchor.get("fcf_margin", 0.8)
        shares_outstanding = float(fundamentals.get("shares_outstanding") or 0)
        if shares_outstanding <= 0 and current_price > 0:
            shares_outstanding = market_cap / current_price
        equity_bridge = {
            "net_debt": float(fundamentals.get("total_debt") or 0) - float(fundamentals.get("total_cash") or 0),
            "shares_outstanding": shares_outstanding,
            "capex_ratio": max(0.01, min(0.18, (capital_expenditure / revenue) if revenue > 0 and capital_expenditure > 0 else 0.04)),
            "working_capital_intensity": max(
                0.0,
                min(
                    0.25,
                    (
                        (float(fundamentals.get("current_assets") or 0) - float(fundamentals.get("current_liabilities") or 0))
                        / revenue
                    ) if revenue > 0 else 0.03,
                ),
            ),
        }
        revenue_base = revenue if revenue > 0 else max(earnings / max(fundamentals.get("profit_margin") or 0.2, 0.05), 1.0)

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
            case = run_dcf_case(
                normalized_fcf=normalized_fcf,
                revenue_base=revenue_base,
                operating_margin=operating_margin,
                current_price=current_price,
                scenario=scenario,
                equity_bridge=equity_bridge,
            )
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
    except Exception as exc:
        logger.error(f"Monte Carlo 估值出错: {exc}")
        return {"error": str(exc), "distribution": []}


def compute_peer_benchmark(
    *,
    symbol: str,
    fundamentals: Dict[str, Any],
    cached_fundamentals: Callable[[str], Dict[str, Any]],
    static_sector_benchmarks: Dict[str, Dict[str, Any]],
    default_benchmark: Dict[str, Any],
    peer_symbols: list[str],
) -> Dict[str, Any]:
    sector = fundamentals.get("sector", "")
    industry = fundamentals.get("industry", "")
    static_benchmark = static_sector_benchmarks.get(sector, default_benchmark)
    metrics = {
        "pe": [],
        "pb": [],
        "ps": [],
        "ev_ebitda": [],
        "ev_revenue": [],
        "peg": [],
    }
    benchmark_peer_symbols = []

    for peer_symbol in peer_symbols:
        if peer_symbol == symbol:
            continue
        peer = cached_fundamentals(peer_symbol)
        if "error" in peer:
            continue
        if sector and peer.get("sector") != sector:
            continue
        if industry and peer.get("industry") and peer.get("industry") != industry and len(benchmark_peer_symbols) >= 5:
            continue

        benchmark_peer_symbols.append(peer_symbol)
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
        dynamic[key] = round(float(np.median(values)), 2) if len(values) >= 3 else fallback

    has_dynamic = any(len(metrics[key]) >= 3 for key in metrics)
    return {
        **dynamic,
        "sector": sector or "Unknown",
        "industry": industry or "Unknown",
        "source_label": "Dynamic peer median" if has_dynamic else "Static sector template",
        "source_key": "dynamic_peer_median" if has_dynamic else "static_sector_template",
        "peer_count": len(benchmark_peer_symbols),
        "peer_symbols": benchmark_peer_symbols[:6],
    }


def benchmark_warnings(benchmark: Dict[str, Any]) -> list[str]:
    if benchmark.get("source_key") == "dynamic_peer_median":
        peers = ", ".join(benchmark.get("peer_symbols", [])[:4])
        return [f"行业基准倍数优先使用同行中位数；本次参考同行包括 {peers or '若干同板块标的'}。"]
    return ["行业基准倍数当前仍采用静态模板，应结合同行数据复核。"]


def build_sensitivity_matrix(
    *,
    symbol: str,
    overrides: Optional[Dict[str, Any]],
    anchor: Dict[str, Any],
    analyze_fn: Callable[[str, Optional[Dict[str, Any]]], Dict[str, Any]],
) -> list[Dict[str, Any]]:
    wacc_anchor = float(anchor.get("wacc") or 0)
    growth_anchor = float(anchor.get("initial_growth") or 0)
    matrix = []
    for growth_shift in (-0.02, 0.0, 0.02):
        row = {
            "growth": round(growth_anchor + growth_shift, 4),
            "cases": [],
        }
        for wacc_shift in (-0.01, 0.0, 0.01):
            case = analyze_fn(
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
    return matrix


def cached_peer_benchmark(
    *,
    symbol: str,
    fundamentals: Dict[str, Any],
    peer_benchmark_cache: Dict[str, Dict[str, Any]],
    benchmark_cache_ttl: int,
    cached_fundamentals: Callable[[str], Dict[str, Any]],
    static_sector_benchmarks: Dict[str, Dict[str, Any]],
    default_benchmark: Dict[str, Any],
    peer_symbols: list[str],
    now: Optional[float] = None,
) -> Dict[str, Any]:
    sector = fundamentals.get("sector", "")
    industry = fundamentals.get("industry", "")
    cache_key = f"{sector}::{industry}".strip(":")
    current_ts = now if now is not None else time.time()
    cached = peer_benchmark_cache.get(cache_key)
    if cached and (current_ts - cached.get("ts", 0)) < benchmark_cache_ttl:
        return cached["value"]

    benchmark = compute_peer_benchmark(
        symbol=symbol,
        fundamentals=fundamentals,
        cached_fundamentals=cached_fundamentals,
        static_sector_benchmarks=static_sector_benchmarks,
        default_benchmark=default_benchmark,
        peer_symbols=peer_symbols,
    )
    peer_benchmark_cache[cache_key] = {"ts": current_ts, "value": benchmark}
    return benchmark
