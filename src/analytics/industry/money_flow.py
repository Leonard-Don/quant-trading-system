"""Pure money-flow DataFrame helpers for IndustryAnalyzer.

Lifted out of ``IndustryAnalyzer`` (``_ensure_industry_volatility``,
``_merge_momentum_and_flow``, ``_normalize_money_flow_dataframe``). Pure
functions with no instance state, so they can be tested without the analyzer.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def ensure_industry_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """为行业数据补齐统一的波动率字段。

    优先级:
    1. 真实/已有字段 `industry_volatility`
    2. 行业振幅 `amplitude`
    3. 行业换手率 `turnover_rate`
    4. 绝对涨跌幅 `abs(change_pct)` 作为最保守代理
    """
    if df.empty:
        return df

    result = df.copy()
    if "industry_volatility_source" not in result.columns:
        result["industry_volatility_source"] = None
    if "industry_volatility" in result.columns:
        result["industry_volatility"] = pd.to_numeric(result["industry_volatility"], errors="coerce").fillna(0.0)
        result["industry_volatility_source"] = result["industry_volatility_source"].fillna("industry_volatility")
        return result

    if "amplitude" in result.columns:
        result["industry_volatility"] = pd.to_numeric(result["amplitude"], errors="coerce").fillna(0.0)
        result["industry_volatility_source"] = "amplitude_proxy"
        return result

    if "turnover_rate" in result.columns and pd.to_numeric(result["turnover_rate"], errors="coerce").fillna(0).abs().sum() > 0:
        result["industry_volatility"] = pd.to_numeric(result["turnover_rate"], errors="coerce").fillna(0.0)
        result["industry_volatility_source"] = "turnover_rate_proxy"
        return result

    change_col = "change_pct" if "change_pct" in result.columns else ("weighted_change" if "weighted_change" in result.columns else None)
    if change_col:
        result["industry_volatility"] = pd.to_numeric(result[change_col], errors="coerce").fillna(0.0).abs()
        result["industry_volatility_source"] = "change_proxy"
    else:
        result["industry_volatility"] = 0.0
        result["industry_volatility_source"] = "unavailable"
    return result


def merge_momentum_and_flow(
    momentum_df: pd.DataFrame, money_flow_df: pd.DataFrame
) -> pd.DataFrame:
    """合并动量数据和资金流向数据的公共逻辑。

    Args:
        momentum_df: 动量 DataFrame
        money_flow_df: 资金流向 DataFrame

    Returns:
        合并后的 DataFrame，包含 change_pct, main_net_inflow, flow_strength 列
    """
    if not money_flow_df.empty:
        # 动态检测可用列，只合并存在的列
        merge_cols = ["industry_name"]
        optional_cols = [
            "change_pct", "main_net_inflow", "flow_strength",
            "turnover_rate", "main_net_ratio", "leading_stock",
            # THS 增强字段
            "industry_index", "total_inflow", "total_outflow",
            "leading_stock_change", "leading_stock_price",
            # AKShare 估值增强字段
            "pe_ttm", "pb", "dividend_yield",
            # 数据来源与质量标记
            "market_cap_source", "valuation_source", "valuation_quality", "data_sources",
        ]
        for col in optional_cols:
            if col in money_flow_df.columns and col not in momentum_df.columns:
                merge_cols.append(col)

        if len(merge_cols) > 1:
            merged_df = momentum_df.merge(
                money_flow_df[merge_cols],
                on="industry_name",
                how="left"
            )
        else:
            merged_df = momentum_df.copy()
    else:
        merged_df = momentum_df.copy()

    # 确保必要的列存在
    if "change_pct" not in merged_df.columns:
        merged_df["change_pct"] = merged_df.get("weighted_change", 0)
    if "main_net_inflow" not in merged_df.columns:
        merged_df["main_net_inflow"] = 0
    if "flow_strength" not in merged_df.columns:
        merged_df["flow_strength"] = 0

    # 仅对数值列 fillna(0)，保留字符串列（如 leading_stock）的 None
    numeric_cols = merged_df.select_dtypes(include="number").columns
    merged_df[numeric_cols] = merged_df[numeric_cols].fillna(0)
    return merged_df


def normalize_money_flow_dataframe(money_flow_df: pd.DataFrame, days: int) -> pd.DataFrame:
    """标准化不同数据源/不同周期下的行业资金流字段。

    统一输出字段:
    - industry_name
    - change_pct
    - main_net_inflow
    - flow_strength
    """
    if money_flow_df.empty:
        return money_flow_df

    df = money_flow_df.copy()

    # 统一行业名称字段
    if "industry_name" not in df.columns:
        for candidate in ["名称", "板块名称", "行业名称", "industry"]:
            if candidate in df.columns:
                df = df.rename(columns={candidate: "industry_name"})
                break

    if "industry_name" not in df.columns:
        logger.warning("money flow data missing industry_name column")
        return pd.DataFrame()

    period_prefix = "今日" if days <= 1 else f"{days}日"

    # 统一涨跌幅字段
    if "change_pct" not in df.columns:
        change_candidates = [
            f"{period_prefix}涨跌幅",
            "今日涨跌幅",
            "5日涨跌幅",
            "10日涨跌幅",
            "涨跌幅",
        ]
        for col in change_candidates:
            if col in df.columns:
                df["change_pct"] = df[col]
                break
        if "change_pct" not in df.columns:
            fuzzy_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
            if fuzzy_col is not None:
                df["change_pct"] = df[fuzzy_col]

    # 统一主力净流入字段
    if "main_net_inflow" not in df.columns:
        inflow_candidates = [
            f"{period_prefix}主力净流入-净额",
            "今日主力净流入-净额",
            "5日主力净流入-净额",
            "10日主力净流入-净额",
            "主力净流入-净额",
        ]
        for col in inflow_candidates:
            if col in df.columns:
                df["main_net_inflow"] = df[col]
                break
        if "main_net_inflow" not in df.columns:
            fuzzy_col = next(
                (c for c in df.columns if "主力净流入" in str(c) and "净额" in str(c)),
                None
            )
            if fuzzy_col is not None:
                df["main_net_inflow"] = df[fuzzy_col]

    # 数值化与缺省
    if "change_pct" in df.columns:
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
    else:
        df["change_pct"] = 0.0

    if "main_net_inflow" in df.columns:
        df["main_net_inflow"] = pd.to_numeric(df["main_net_inflow"], errors="coerce").fillna(0)
    else:
        df["main_net_inflow"] = 0.0

    # 统一资金强度字段，保证后续聚类/排行不会缺列。
    # 某些上游会返回全 0 的 flow_strength，这里需要根据可用字段重建，避免聚类图塌成一条线。
    recompute_flow_strength = "flow_strength" not in df.columns
    if not recompute_flow_strength:
        df["flow_strength"] = pd.to_numeric(df["flow_strength"], errors="coerce").fillna(0)
        recompute_flow_strength = (
            (df["flow_strength"].abs() <= 1e-9).all()
            and (df["main_net_inflow"].abs() > 1e-9).any()
        )

    if recompute_flow_strength:
        main_net_ratio = pd.to_numeric(df.get("main_net_ratio", 0), errors="coerce").fillna(0)
        if (main_net_ratio.abs() > 1e-9).any():
            df["flow_strength"] = (main_net_ratio / 100.0).clip(-1.0, 1.0)
        else:
            max_flow = df["main_net_inflow"].abs().max()
            if max_flow > 0:
                df["flow_strength"] = (df["main_net_inflow"] / max_flow).clip(-1.0, 1.0)
            else:
                df["flow_strength"] = 0.0

    # 统一换手率字段
    if "turnover_rate" in df.columns:
        df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce").fillna(0)
    else:
        df["turnover_rate"] = 0.0

    if "amplitude" in df.columns:
        df["amplitude"] = pd.to_numeric(df["amplitude"], errors="coerce").fillna(0)

    # 统一主力净占比字段
    if "main_net_ratio" not in df.columns:
        ratio_candidates = [
            f"{period_prefix}主力净流入-净占比",
            "今日主力净流入-净占比",
            "5日主力净流入-净占比",
            "10日主力净流入-净占比",
            "主力净流入-净占比",
        ]
        for col in ratio_candidates:
            if col in df.columns:
                df["main_net_ratio"] = df[col]
                break

    if "main_net_ratio" in df.columns:
        df["main_net_ratio"] = pd.to_numeric(df["main_net_ratio"], errors="coerce").fillna(0)
    else:
        df["main_net_ratio"] = 0.0

    # Uniform leading stock field
    if "leading_stock" not in df.columns:
        # Try to find leading stock column
        for col in df.columns:
            if "领涨" in str(col) or "最大股" in str(col):
                df["leading_stock"] = df[col]
                break

    if "leading_stock" not in df.columns:
        df["leading_stock"] = None
    else:
        # 防御性处理：确保 leading_stock 为字符串或 None (数据源可能返回整数 0)
        df["leading_stock"] = df["leading_stock"].apply(
            lambda x: str(x) if x and x != 0 and str(x).strip() else None
        )

    # 统一成分股数量字段
    if "stock_count" not in df.columns:
        for candidate in ["成分股数量", "个股数", "stock_count"]:
            if candidate in df.columns:
                df["stock_count"] = pd.to_numeric(df[candidate], errors="coerce").fillna(0).astype(int)
                break
        if "stock_count" not in df.columns:
            df["stock_count"] = 0

    # 统一总市值字段
    if "total_market_cap" not in df.columns:
        for candidate in ["总市值", "流通市值"]:
            if candidate in df.columns:
                df["total_market_cap"] = pd.to_numeric(df[candidate], errors="coerce").fillna(0)
                break
        if "total_market_cap" not in df.columns:
            df["total_market_cap"] = 0.0
    else:
        # 即使列已存在，也确保数值类型正确
        df["total_market_cap"] = pd.to_numeric(df["total_market_cap"], errors="coerce").fillna(0)

    # [Fallback] 当所有 total_market_cap 为 0 时，使用 main_net_inflow 绝对值估算相对大小
    if (df["total_market_cap"] == 0).all() and "main_net_inflow" in df.columns:
        abs_flow = df["main_net_inflow"].abs()
        if abs_flow.max() > 0:
            logger.info("All total_market_cap are 0, estimating from main_net_inflow")
            df["total_market_cap"] = abs_flow * 1000  # 缩放到合理量级

    return ensure_industry_volatility(df)


__all__ = [
    "ensure_industry_volatility",
    "merge_momentum_and_flow",
    "normalize_money_flow_dataframe",
]
