"""纯函数型解析 / 归一化叶子助手。

从 ``AKShareProvider`` 机械抽取的无状态助手（不读写类级缓存、不发起网络调用）。
``akshare_provider`` 以 ``staticmethod`` 别名重新绑定这些函数，沿用历史方法名，
调用点保持不变，行为逐字节一致。
"""

import logging
from datetime import datetime
from typing import Any

import pandas as pd

# Use the provider module's logger name so log records emitted from these
# extracted leaf helpers are byte-for-byte identical to the pre-refactor output.
logger = logging.getLogger("src.data.providers.akshare_provider")


def safe_float(value: Any) -> float:
    """
    安全转换为浮点数

    支持格式:
    - 普通数字: 3.14, 100
    - 百分号: '8.32%' → 8.32
    - 中文单位: '3000.48万' → 30004800, '2.68亿' → 268000000
    - 布尔值 False、'--'、空值 → 0.0
    """
    if value is None or value is False or value == "--" or value == "":
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass

    # 数字类型直接转
    if isinstance(value, (int, float)):
        return float(value)

    # 字符串类型需要解析
    s = str(value).strip()
    if not s:
        return 0.0

    try:
        # 去掉百分号
        if s.endswith("%"):
            return float(s[:-1])
        # 中文单位
        if s.endswith("万亿"):
            return float(s[:-2]) * 1e12
        if s.endswith("亿"):
            return float(s[:-1]) * 1e8
        if s.endswith("万"):
            return float(s[:-1]) * 1e4
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_heatmap_history_payload(
    payload: Any,
) -> tuple[pd.DataFrame | None, datetime | None]:
    """从 heatmap-history JSON payload（快照列表）解析行业 metadata 兜底 DataFrame。

    纯函数：输入已读取/解析的 payload，输出 ``(df, updated_at)``。不读取磁盘、
    不触类级状态。返回值与原 ``_load_heatmap_history_metadata_fallback`` 在拿到
    payload 之后的逻辑逐字节一致。
    """
    if not isinstance(payload, list) or not payload:
        return None, None

    for snapshot in payload:
        industries = snapshot.get("industries") or []
        rows = []
        for item in industries:
            source = str(item.get("marketCapSource", "unknown") or "unknown").strip()
            total_market_cap = pd.to_numeric(item.get("size"), errors="coerce")
            turnover_rate = pd.to_numeric(item.get("turnoverRate"), errors="coerce")
            industry_name = str(item.get("name") or "").strip()
            if (
                not industry_name
                or not pd.notna(total_market_cap)
                or float(total_market_cap) <= 0
            ):
                continue
            if (
                source == "unknown"
                or source.startswith("estimated")
                or source == "constant_fallback"
            ):
                continue

            rows.append(
                {
                    "industry_name": industry_name,
                    "original_name": industry_name,
                    "total_market_cap": float(total_market_cap),
                    "turnover_rate": float(turnover_rate)
                    if pd.notna(turnover_rate)
                    else 0.0,
                    "market_cap_source": source,
                }
            )

        if rows:
            updated_at_raw = snapshot.get("captured_at") or snapshot.get("update_time")
            updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
            df = pd.DataFrame(rows).drop_duplicates(subset=["industry_name"], keep="first")
            logger.info(
                "Loaded heatmap-history metadata fallback with %s industries", len(df)
            )
            return df, updated_at

    return None, None


def parse_industry_metadata_frame(df_meta: pd.DataFrame) -> pd.DataFrame:
    """对原始东方财富行业 metadata DataFrame 执行去重 + 名称清洗 + 列名映射。

    纯函数：输入 ``ak.stock_board_industry_name_em`` 的原始非空 DataFrame，
    输出可用于 merge 的标准化 DataFrame。逻辑与原 ``_get_industry_metadata``
    内的过滤/清洗/重命名块逐字节一致；不触类级缓存、不写盘。
    """
    # [Filter Duplicate Industries]
    # Logic:
    # 1. Remove names ending with 'III' (usually redundant L3)
    # 2. Remove names ending with 'II' ONLY IF the base name exists

    df_meta["base_name"] = df_meta["板块名称"].astype(str)
    all_names = set(df_meta["base_name"].tolist())

    filter_indices = []
    for idx, row in df_meta.iterrows():
        name = row["base_name"]
        keep = True

        if name.endswith("Ⅲ"):
            keep = False
        elif name.endswith("Ⅱ"):
            base = name[:-1]
            if base in all_names:
                keep = False

        if keep:
            filter_indices.append(idx)

    df_meta = df_meta.loc[filter_indices].drop(columns=["base_name"])

    # Preserve original name for matching
    df_meta["original_name"] = df_meta["板块名称"]

    # [Clean Names] Remove Roman numerals from the display name
    # e.g., "白酒Ⅱ" -> "白酒", "证券Ⅱ" -> "证券"
    df_meta["板块名称"] = df_meta["板块名称"].str.replace(r"[ⅡⅢⅢ]$", "", regex=True)

    # Rename columns to match for merge
    df_meta = df_meta.rename(
        columns={
            "板块名称": "industry_name",
            "总市值": "total_market_cap",
            "换手率": "turnover_rate",
            "涨跌幅": "change_pct_meta",  # Avoid conflict
        }
    )
    if "market_cap_source" not in df_meta.columns:
        df_meta["market_cap_source"] = "akshare_metadata"

    return df_meta
