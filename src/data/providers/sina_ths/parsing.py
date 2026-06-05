"""纯函数型解析 / 归一化 / 数据质量叶子助手。

从 ``SinaIndustryAdapter`` 机械抽取的无状态助手（不读写类级缓存）。
``sina_ths_adapter`` 以 ``staticmethod`` 别名重新绑定这些函数，沿用历史方法名，
调用点保持不变，行为逐字节一致。
"""

import logging
import re
from typing import Any, Dict, List

import pandas as pd
from bs4 import BeautifulSoup

from .mappings import INDUSTRY_ENRICHMENT_ALIASES

# Use the adapter module's logger name so log records emitted from these
# extracted leaf helpers are byte-for-byte identical to the pre-refactor output.
logger = logging.getLogger("src.data.providers.sina_ths_adapter")


def numeric_series_or_default(
    df: pd.DataFrame, column: str, default: float = 0.0
) -> pd.Series:
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index, dtype="float64")


def build_name_aliases(raw_name: str) -> List[str]:
    import re

    normalized = str(raw_name or "").strip()
    if not normalized:
        return []

    aliases = {normalized}

    # 清理前缀 N/C/U/W/*ST/ST，兼容脱帽和上市首日名称变体。
    prefix_clean = re.sub(r"^[NCUW\*]*(ST)?", "", normalized, flags=re.IGNORECASE).strip()
    if prefix_clean:
        aliases.add(prefix_clean)

    # 清理科创/注册制后缀，如 "-U"、"-W"、"-A"。
    suffix_clean = re.sub(r"-[A-Z]+$", "", normalized, flags=re.IGNORECASE).strip()
    if suffix_clean:
        aliases.add(suffix_clean)

    # 组合清理前后缀，兼容类似 "N亚虹医药-U" 变体。
    combined_clean = re.sub(r"-[A-Z]+$", "", prefix_clean, flags=re.IGNORECASE).strip()
    if combined_clean:
        aliases.add(combined_clean)

    return [alias for alias in aliases if alias]


def normalize_industry_join_key(industry_name: str) -> str:
    cleaned = str(industry_name or "").strip().replace("Ⅲ", "").replace("Ⅱ", "")
    if cleaned.endswith("行业"):
        cleaned = cleaned[:-2]
    cleaned = cleaned.strip()
    return INDUSTRY_ENRICHMENT_ALIASES.get(cleaned, cleaned)


def append_data_source(df: pd.DataFrame, mask: pd.Series, source: str) -> None:
    if "data_sources" not in df.columns:
        df["data_sources"] = [[] for _ in range(len(df))]

    def append_source(current):
        items = list(current) if isinstance(current, list) else []
        if source not in items:
            items.append(source)
        return items

    df.loc[mask, "data_sources"] = df.loc[mask, "data_sources"].apply(append_source)


def ensure_data_quality_columns(df: pd.DataFrame, primary_source: str) -> pd.DataFrame:
    result = df.copy()
    if "data_sources" not in result.columns:
        result["data_sources"] = [[primary_source] for _ in range(len(result))]
    else:
        result["data_sources"] = result["data_sources"].apply(
            lambda value: list(value) if isinstance(value, list) and value else [primary_source]
        )

    if "market_cap_source" not in result.columns:
        result["market_cap_source"] = "unknown"
    if "valuation_source" not in result.columns:
        result["valuation_source"] = "unavailable"
    if "valuation_quality" not in result.columns:
        result["valuation_quality"] = "unavailable"
    return result


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() in {"", "nan", "None"}


def normalize_sina_stock_rows(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_rows: List[Dict[str, Any]] = []
    for stock in stocks or []:
        symbol = str(stock.get("code") or stock.get("symbol") or "").strip()
        if not symbol:
            continue
        turnover_rate = (
            stock.get("turnover_rate")
            or stock.get("turnover_ratio")
            or stock.get("turnoverRatio")
            or stock.get("turnoverratio")
            or 0
        )
        normalized_rows.append(
            {
                "symbol": symbol,
                "code": symbol,
                "name": stock.get("name", ""),
                "change_pct": stock.get("change_pct", 0),
                "market_cap": stock.get("mktcap", 0) * 10000,
                "volume": stock.get("volume", 0),
                "amount": stock.get("amount", 0),
                "turnover_rate": turnover_rate,
                "turnover": turnover_rate,
                "pe_ratio": stock.get("pe_ratio", 0),
                "pb_ratio": stock.get("pb_ratio", 0),
            }
        )
    return normalized_rows


def normalize_stock_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper().replace("_", ".")
    suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text)
    if suffix_match:
        return suffix_match.group(1)

    prefix_match = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", text)
    if prefix_match:
        return prefix_match.group(2)

    normalized = re.sub(r"^(SH|SZ|BJ)", "", text, flags=re.IGNORECASE)
    return normalized if re.fullmatch(r"\d{6}", normalized) else ""


def dedupe_table_headers(headers: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    normalized_headers: List[str] = []
    for header in headers:
        clean_header = re.sub(r"\s+", " ", str(header or "").strip())
        if not clean_header:
            clean_header = "unnamed"
        duplicate_index = seen.get(clean_header, 0)
        normalized_headers.append(
            clean_header if duplicate_index == 0 else f"{clean_header}.{duplicate_index}"
        )
        seen[clean_header] = duplicate_index + 1
    return normalized_headers


def parse_ths_flow_html(html: str) -> tuple[pd.DataFrame, int]:
    if not str(html or "").strip():
        return pd.DataFrame(), 1

    soup = BeautifulSoup(html, features="lxml")
    page_num = 1
    page_info = soup.find("span", class_="page_info")
    if page_info:
        try:
            page_num = int(str(page_info.get_text(strip=True)).split("/")[1])
        except Exception as exc:
            logger.debug("Could not parse THS page count, defaulting to 1: %s", exc)
            page_num = 1

    table = soup.select_one("table.J-ajax-table") or soup.find("table")
    if table is None:
        return pd.DataFrame(), page_num

    header_cells = table.select("thead th")
    if not header_cells:
        header_cells = table.select("tr th")
    headers = dedupe_table_headers(
        [cell.get_text(" ", strip=True) for cell in header_cells]
    )
    if not headers:
        return pd.DataFrame(), page_num

    rows: List[List[str]] = []
    body_rows = table.select("tbody tr") or table.select("tr")
    for row in body_rows:
        cell_nodes = row.find_all("td")
        if not cell_nodes:
            continue
        cell_text = [cell.get_text(" ", strip=True) for cell in cell_nodes]
        if len(cell_text) < len(headers):
            cell_text.extend([""] * (len(headers) - len(cell_text)))
        rows.append(cell_text[: len(headers)])

    if not rows:
        return pd.DataFrame(columns=headers), page_num

    return pd.DataFrame(rows, columns=headers), page_num
