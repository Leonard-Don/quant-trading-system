import pandas as pd

from src.data.factor_panel import (
    FactorPanel,
    build_eligible_by_date,
    build_panel,
    build_survivorship_free_universe,
)


class _FakeProvider:
    def get_historical_data(self, symbol, start, end, interval="1d"):
        dates = pd.bdate_range("2024-01-01", periods=10)
        c = [10 + i for i in range(10)]
        return pd.DataFrame(
            {"open": c, "high": c, "low": c, "close": c, "volume": [1e6] * 10}, index=dates
        )

    def get_financial_indicators(self, symbol, start, end):
        return pd.DataFrame({"ann_date": ["20240103"], "end_date": ["20231231"], "roe": [11.0]})

    def get_moneyflow(self, symbol, start, end):
        d = pd.bdate_range("2024-01-01", periods=10)
        return pd.DataFrame(
            {"trade_date": [x.strftime("%Y%m%d") for x in d], "net_mf_amount": [100] * 10}
        )


def test_build_panel_assembles_and_caches(tmp_path):
    prov = _FakeProvider()
    panel = build_panel(["AAA", "BBB"], "20240101", "20240115", prov, cache_dir=tmp_path)
    assert isinstance(panel, FactorPanel)
    assert set(panel.symbols) == {"AAA", "BBB"}
    assert not panel.history("AAA", pd.Timestamp("2024-01-05")).empty
    assert panel.latest_fundamental("AAA", pd.Timestamp("2024-01-04"))["roe"] == 11.0
    # cache files written (pickle, dependency-free; see build_panel docstring)
    assert any(tmp_path.rglob("*.pkl"))


def test_build_panel_uses_cache_on_rerun(tmp_path):
    calls = {"n": 0}
    prov = _FakeProvider()
    orig = prov.get_historical_data

    def counted(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    prov.get_historical_data = counted
    build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)
    first = calls["n"]
    build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)  # rerun
    assert calls["n"] == first  # no extra fetch; served from cache


class _AsOfProvider:
    """Provider whose constituents/suspensions vary by date (point-in-time)."""

    def __init__(self, constituents_by_date, suspended_by_date=None):
        self.constituents_by_date = constituents_by_date
        self.suspended_by_date = suspended_by_date or {}
        self.constituent_calls = []
        self.suspend_calls = []

    def get_index_constituents(self, index_code, trade_date=None):
        self.constituent_calls.append(trade_date)
        # Latest as-of <= trade_date.
        if trade_date is None:
            # current = the latest configured snapshot
            key = max(self.constituents_by_date)
            return list(self.constituents_by_date[key])
        eligible = [d for d in self.constituents_by_date if d <= str(trade_date)]
        if not eligible:
            return []
        return list(self.constituents_by_date[max(eligible)])

    def get_suspended_symbols(self, trade_date):
        self.suspend_calls.append(str(trade_date))
        return set(self.suspended_by_date.get(str(trade_date), set()))


def test_survivorship_free_universe_unions_history():
    # H1 2020 has AAA,BBB; H2 2020 swaps BBB->CCC. The union must include all three.
    prov = _AsOfProvider(
        {
            "20200101": ["AAA.SH", "BBB.SZ"],
            "20200701": ["AAA.SH", "CCC.SZ"],
        }
    )
    universe = build_survivorship_free_universe(
        prov, "000300.SH", "20200101", "20201231", sample_freq_days=90
    )
    assert set(universe) == {"AAA.SH", "BBB.SZ", "CCC.SZ"}
    # queried point-in-time (a trade_date was passed each sample)
    assert all(d is not None for d in prov.constituent_calls)


def test_eligible_by_date_subtracts_suspended():
    prov = _AsOfProvider(
        constituents_by_date={"20200101": ["AAA.SH", "BBB.SZ", "CCC.SZ"]},
        suspended_by_date={"20200115": {"BBB.SZ"}},
    )
    dates = [pd.Timestamp("2020-01-15")]
    eligible = build_eligible_by_date(prov, "000300.SH", dates)
    # BBB suspended on that date -> excluded; AAA/CCC remain.
    assert eligible[pd.Timestamp("2020-01-15")] == {"AAA.SH", "CCC.SZ"}
    # one suspend_d call per rebalance date
    assert prov.suspend_calls == ["20200115"]


def test_eligible_by_date_no_suspensions_keeps_all():
    prov = _AsOfProvider(constituents_by_date={"20200101": ["AAA.SH", "BBB.SZ"]})
    dates = [pd.Timestamp("2020-02-03")]
    eligible = build_eligible_by_date(prov, "000300.SH", dates)
    assert eligible[pd.Timestamp("2020-02-03")] == {"AAA.SH", "BBB.SZ"}
