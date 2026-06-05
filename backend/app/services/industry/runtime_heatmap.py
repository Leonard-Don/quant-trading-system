"""Pure heatmap / industry-rank response builders.

Extracted verbatim from ``runtime.py``. These are stateless transforms over
provider/analyzer output: they build ``IndustryRankResponse`` rows, derive the
leading-stock symbol lookup from an industry DataFrame, collect hot-leader
candidate rows, and size-trim the heatmap-history payload. None of them touch
the runtime caches, locks, executors or singletons, and they never call back
into ``runtime.py`` — so there is no import cycle. ``runtime.py`` re-imports
each name.

``SIX_DIGIT_SYMBOL_PATTERN`` is re-declared here as an identical
``re.compile(r"\\d{6}")`` constant (only ever read via ``.fullmatch``);
``runtime.py`` keeps its own module-level copy because the ``_compat`` test
state-sync targets ``runtime.SIX_DIGIT_SYMBOL_PATTERN`` specifically.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.app.schemas.industry import IndustryRankResponse
from src.analytics.industry_stock_details import normalize_symbol

SIX_DIGIT_SYMBOL_PATTERN = re.compile(r"\d{6}")

_HEATMAP_HISTORY_MAX_ITEMS = 48

_HEATMAP_HISTORY_MAX_FILE_BYTES = 2 * 1024 * 1024


def _build_hot_industry_rank_responses(
    analyzer, hot_industries: list[dict[str, Any]]
) -> list[IndustryRankResponse]:
    return [
        IndustryRankResponse(
            rank=ind.get("rank", 0),
            industry_name=ind.get("industry_name", ""),
            score=ind.get("score", 0),
            momentum=ind.get("momentum", 0),
            change_pct=ind.get("change_pct", 0),
            money_flow=ind.get("money_flow", 0),
            flow_strength=ind.get("flow_strength", 0),
            industryVolatility=ind.get("industry_volatility", 0),
            industryVolatilitySource=ind.get("industry_volatility_source", "unavailable"),
            stock_count=ind.get("stock_count", 0),
            total_market_cap=ind.get("total_market_cap", 0),
            marketCapSource=ind.get("market_cap_source", "unknown"),
            mini_trend=ind.get("mini_trend", []),
            score_breakdown=analyzer.build_rank_score_breakdown(ind),
        )
        for ind in hot_industries
    ]


def _extract_leading_stock_symbol_lookup(industries) -> dict[str, str]:
    if (
        industries is None
        or industries.empty
        or not {"leading_stock_name", "leading_stock_code"}.issubset(industries.columns)
    ):
        return {}

    filtered = industries.loc[:, ["leading_stock_name", "leading_stock_code"]].copy()
    filtered["leading_stock_name"] = (
        filtered["leading_stock_name"].fillna("").astype(str).str.strip()
    )
    filtered["leading_stock_code"] = filtered["leading_stock_code"].map(
        lambda value: normalize_symbol(value or "")
    )
    filtered = filtered[
        filtered["leading_stock_name"].ne("")
        & filtered["leading_stock_code"].map(
            lambda value: bool(SIX_DIGIT_SYMBOL_PATTERN.fullmatch(value or ""))
        )
    ]
    if filtered.empty:
        return {}
    filtered = filtered.drop_duplicates(subset=["leading_stock_name"], keep="first")
    return dict(zip(filtered["leading_stock_name"], filtered["leading_stock_code"]))


def _collect_hot_leader_candidates(
    heatmap_df,
    top_industry_names: set[str],
    top_n: int,
) -> list[dict[str, Any]]:
    if heatmap_df is None or heatmap_df.empty or "leading_stock" not in heatmap_df.columns:
        return []

    sort_col = "main_net_inflow" if "main_net_inflow" in heatmap_df.columns else "change_pct"
    hot_candidate_limit = max(1, int(top_n * 1.2))
    sorted_df = heatmap_df.sort_values(sort_col, ascending=False)
    filtered_df = sorted_df[
        sorted_df["leading_stock"].map(lambda value: isinstance(value, str) and bool(value))
    ]
    if top_industry_names:
        filtered_df = filtered_df[filtered_df["industry_name"].isin(top_industry_names)]
    if filtered_df.empty:
        return []
    return (
        filtered_df.drop_duplicates(subset=["leading_stock"], keep="first")
        .head(hot_candidate_limit)
        .to_dict("records")
    )


def _trim_heatmap_history_payload(payload: list[dict]) -> list[dict]:
    trimmed = list(payload[:_HEATMAP_HISTORY_MAX_ITEMS])
    while trimmed:
        encoded = json.dumps(trimmed, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) <= _HEATMAP_HISTORY_MAX_FILE_BYTES:
            break
        trimmed = trimmed[:-1]
    return trimmed


__all__ = [
    "_build_hot_industry_rank_responses",
    "_collect_hot_leader_candidates",
    "_extract_leading_stock_symbol_lookup",
    "_trim_heatmap_history_payload",
]
