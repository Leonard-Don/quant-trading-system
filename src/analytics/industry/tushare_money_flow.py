"""Pure Tushare after-close money-flow normalization for IndustryAnalyzer.

Lifted out of ``IndustryAnalyzer._normalize_tushare_industry_money_flow`` (a
classmethod that only depended on the ``_tushare_normalize`` leaf helpers, not on
instance state). Maps Tushare after-close industry frames (moneyflow + DC board
status) into the analyzer's money-flow contract.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.data.providers import _tushare_normalize


def normalize_tushare_industry_money_flow(
    moneyflow_df: Optional[pd.DataFrame],
    board_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Map Tushare after-close industry frames into the analyzer contract."""
    moneyflow = _tushare_normalize.normalize_columns(moneyflow_df)
    board = _tushare_normalize.normalize_columns(board_df)
    if moneyflow.empty and board.empty:
        return pd.DataFrame()

    records: dict[str, dict[str, Any]] = {}

    for _, row in moneyflow.iterrows():
        industry_name = _tushare_normalize.name_from_row(row)
        if not industry_name:
            continue
        record = records.setdefault(industry_name, {"industry_name": industry_name})
        change_pct = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(row, ["change_pct", "pct_change", "涨跌幅"])
        )
        if change_pct is not None:
            record["change_pct"] = change_pct

        net_amount = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(
                row,
                [
                    "main_net_inflow",
                    "net_amount",
                    "net_mf_amount",
                    "net_main_amount",
                    "主力净流入-净额",
                    "净额",
                ],
            ),
            0.0,
        )
        if net_amount is not None and abs(net_amount) < 1e8 and abs(net_amount) > 0:
            net_amount *= 10000
        record["main_net_inflow"] = net_amount or 0.0

        net_ratio = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(
                row,
                [
                    "main_net_ratio",
                    "net_amount_rate",
                    "net_mf_ratio",
                    "net_main_rate",
                    "主力净流入-净占比",
                ],
            )
        )
        if net_ratio is not None:
            record["main_net_ratio"] = net_ratio
            record["flow_strength"] = max(min(net_ratio / 100.0, 1.0), -1.0)

        _tushare_normalize.append_source(record, "tushare_moneyflow_ind_ths")

    for _, row in board.iterrows():
        industry_name = _tushare_normalize.name_from_row(row)
        if not industry_name:
            continue
        record = records.setdefault(industry_name, {"industry_name": industry_name})
        board_change = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(row, ["change_pct", "pct_change", "涨跌幅"])
        )
        if board_change is not None:
            record["change_pct"] = board_change

        total_mv = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(row, ["total_market_cap", "total_mv", "总市值"])
        )
        if total_mv is not None and total_mv > 0:
            if total_mv < 1e10:
                total_mv *= 10000
            record["total_market_cap"] = total_mv
            record["market_cap_source"] = "tushare_dc_board"

        turnover_rate = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(row, ["turnover_rate", "换手率"]),
            0.0,
        )
        record["turnover_rate"] = turnover_rate or 0.0

        up_num = (
            _tushare_normalize.coerce_numeric(
                _tushare_normalize.first_value(row, ["up_num", "上涨家数"]), 0.0
            )
            or 0.0
        )
        down_num = (
            _tushare_normalize.coerce_numeric(
                _tushare_normalize.first_value(row, ["down_num", "下跌家数"]), 0.0
            )
            or 0.0
        )
        if up_num or down_num:
            record["stock_count"] = int(up_num + down_num)

        leading = _tushare_normalize.first_value(row, ["leading_stock", "leading", "领涨股"])
        if leading:
            record["leading_stock"] = str(leading).strip()
        leading_pct = _tushare_normalize.coerce_numeric(
            _tushare_normalize.first_value(
                row, ["leading_stock_change", "leading_pct", "领涨股涨跌幅"]
            )
        )
        if leading_pct is not None:
            record["leading_stock_change"] = leading_pct

        _tushare_normalize.append_source(record, "tushare_dc_index")

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records.values())
    if "market_cap_source" not in result.columns:
        result["market_cap_source"] = "unknown"
    result["market_cap_source"] = result["market_cap_source"].fillna("unknown")
    return result


__all__ = ["normalize_tushare_industry_money_flow"]
