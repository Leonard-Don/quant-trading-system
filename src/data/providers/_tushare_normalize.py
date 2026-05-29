"""Shared Tushare after-close frame-normalization helpers.

Both :class:`~src.analytics.industry_analyzer.IndustryAnalyzer` and
:class:`~src.data.providers.sina_ths_adapter.SinaIndustryAdapter` consume the
same Tushare ``moneyflow_ind_ths`` / ``dc_index`` shapes and used to carry
byte-identical copies of these leaf helpers — copies that had begun to drift.
They live here as pure, dependency-light functions so a fix lands in exactly one
place. The two classes expose them under their historical method names via
``staticmethod`` aliases, so call sites are unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

# Candidate column names (English + 中文) that carry an industry/board name.
_NAME_CANDIDATES = ["industry_name", "name", "industry", "板块名称", "行业名称", "名称"]


def coerce_numeric(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Best-effort float coercion; returns ``default`` for None/NaN/garbage."""
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_columns(frame: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Return a copy of ``frame`` with lower-cased, stripped column names."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    return result


def first_value(row: pd.Series, candidates: list[str]) -> Any:
    """First present, non-null value among ``candidates`` in ``row``."""
    for candidate in candidates:
        if candidate in row.index:
            value = row.get(candidate)
            if value is not None and not pd.isna(value):
                return value
    return None


def name_from_row(row: pd.Series) -> str:
    """Resolve the industry/board name from a normalized row."""
    return str(first_value(row, _NAME_CANDIDATES) or "").strip()


def append_source(record: dict[str, Any], source: str) -> None:
    """Append ``source`` to ``record['data_sources']`` (created/coerced to a list)."""
    sources = record.setdefault("data_sources", [])
    if not isinstance(sources, list):
        sources = [sources]
        record["data_sources"] = sources
    if source not in sources:
        sources.append(source)
