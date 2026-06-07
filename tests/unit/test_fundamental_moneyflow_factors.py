import pandas as pd

from src.analytics.factors.fundamental import ProfitGrowthFactor, ROEFactor
from src.analytics.factors.moneyflow import NetInflowFactor
from src.data.factor_panel import FactorPanel


def _px(dates):
    c = [10 + i for i in range(len(dates))]
    return pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": [1e6] * len(dates)}, index=dates
    )


def test_roe_factor_uses_ann_date_gated_value():
    dates = pd.bdate_range("2024-01-01", periods=10)
    fa = pd.DataFrame(
        {
            "ann_date": pd.to_datetime(["2024-01-03"]),
            "end_date": pd.to_datetime(["2023-12-31"]),
            "roe": [15.0],
        }
    )
    fa2 = pd.DataFrame(
        {
            "ann_date": pd.to_datetime(["2024-01-03"]),
            "end_date": pd.to_datetime(["2023-12-31"]),
            "roe": [5.0],
        }
    )
    panel = FactorPanel(prices={"HI": _px(dates), "LO": _px(dates)}, fundamentals={"HI": fa, "LO": fa2})
    vals = ROEFactor().compute(panel, as_of=dates[5])
    assert vals["HI"] > vals["LO"]


def test_fundamental_factor_invisible_before_ann_date():
    dates = pd.bdate_range("2024-01-01", periods=10)
    fa = pd.DataFrame(
        {
            "ann_date": pd.to_datetime(["2024-01-08"]),
            "end_date": pd.to_datetime(["2023-12-31"]),
            "roe": [15.0],
        }
    )
    panel = FactorPanel(prices={"HI": _px(dates)}, fundamentals={"HI": fa})
    vals = ROEFactor().compute(panel, as_of=dates[2])  # before 2024-01-08 announcement
    assert "HI" not in vals.index  # not yet visible -> excluded


def test_profit_growth_factor_reads_netprofit_yoy():
    dates = pd.bdate_range("2024-01-01", periods=10)
    fa = pd.DataFrame(
        {
            "ann_date": pd.to_datetime(["2024-01-03"]),
            "end_date": pd.to_datetime(["2023-12-31"]),
            "netprofit_yoy": [25.0],
        }
    )
    panel = FactorPanel(prices={"HI": _px(dates)}, fundamentals={"HI": fa})
    vals = ProfitGrowthFactor().compute(panel, as_of=dates[5])
    assert vals["HI"] == 25.0


def test_net_inflow_factor_ranks_inflow_higher():
    dates = pd.bdate_range("2024-01-01", periods=10)
    mf_in = pd.DataFrame({"net_mf_amount": [100.0] * 10}, index=dates)
    mf_out = pd.DataFrame({"net_mf_amount": [-100.0] * 10}, index=dates)
    panel = FactorPanel(prices={"IN": _px(dates), "OUT": _px(dates)}, moneyflow={"IN": mf_in, "OUT": mf_out})
    vals = NetInflowFactor(window=5).compute(panel, as_of=dates[-1])
    assert vals["IN"] > vals["OUT"]
