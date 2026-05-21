"""Tests for industry.money_flow — pure money-flow helpers extracted from IndustryAnalyzer."""

import pandas as pd

from src.analytics.industry.money_flow import (
    ensure_industry_volatility,
    merge_momentum_and_flow,
    normalize_money_flow_dataframe,
)


def test_ensure_volatility_empty_df():
    assert ensure_industry_volatility(pd.DataFrame()).empty


def test_ensure_volatility_uses_existing_column():
    out = ensure_industry_volatility(pd.DataFrame({"industry_volatility": [1.5, 2.0]}))
    assert list(out["industry_volatility"]) == [1.5, 2.0]
    assert (out["industry_volatility_source"] == "industry_volatility").all()


def test_ensure_volatility_falls_back_to_amplitude():
    out = ensure_industry_volatility(pd.DataFrame({"amplitude": [3.0, 4.0]}))
    assert list(out["industry_volatility"]) == [3.0, 4.0]
    assert (out["industry_volatility_source"] == "amplitude_proxy").all()


def test_ensure_volatility_falls_back_to_abs_change():
    out = ensure_industry_volatility(pd.DataFrame({"change_pct": [-2.0, 3.0]}))
    assert list(out["industry_volatility"]) == [2.0, 3.0]
    assert (out["industry_volatility_source"] == "change_proxy").all()


def test_merge_empty_money_flow_keeps_momentum():
    momentum = pd.DataFrame({"industry_name": ["A", "B"], "weighted_change": [1.0, 2.0]})
    out = merge_momentum_and_flow(momentum, pd.DataFrame())
    assert list(out["industry_name"]) == ["A", "B"]
    for col in ("change_pct", "main_net_inflow", "flow_strength"):
        assert col in out.columns


def test_merge_brings_in_flow_columns():
    momentum = pd.DataFrame({"industry_name": ["A", "B"], "change_pct": [1.0, 2.0]})
    flow = pd.DataFrame(
        {
            "industry_name": ["A", "B"],
            "main_net_inflow": [100.0, 200.0],
            "flow_strength": [0.5, 0.8],
        }
    )
    out = merge_momentum_and_flow(momentum, flow)
    assert list(out["main_net_inflow"]) == [100.0, 200.0]
    assert list(out["flow_strength"]) == [0.5, 0.8]


def test_normalize_empty_returns_empty():
    assert normalize_money_flow_dataframe(pd.DataFrame(), days=5).empty


def test_normalize_missing_industry_name_returns_empty():
    out = normalize_money_flow_dataframe(pd.DataFrame({"涨跌幅": [1.0, 2.0]}), days=5)
    assert out.empty


def test_normalize_maps_chinese_columns_to_standard():
    df = pd.DataFrame(
        {
            "行业名称": ["电子", "医药"],
            "5日涨跌幅": [3.5, -1.2],
            "5日主力净流入-净额": [1e8, -5e7],
            "flow_strength": [0.6, -0.3],
        }
    )
    out = normalize_money_flow_dataframe(df, days=5)
    assert list(out["industry_name"]) == ["电子", "医药"]
    assert list(out["change_pct"]) == [3.5, -1.2]
    assert list(out["main_net_inflow"]) == [1e8, -5e7]
    assert "flow_strength" in out.columns
