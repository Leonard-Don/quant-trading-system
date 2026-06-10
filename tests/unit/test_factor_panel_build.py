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


class _NullDateProvider(_FakeProvider):
    """Fresh Tushare fetches can carry a None/malformed ann_date or trade_date.
    That must NOT crash the whole panel build (it used to: strptime ValueError on
    the literal string 'None')."""

    def get_financial_indicators(self, symbol, start, end):
        return pd.DataFrame(
            {"ann_date": ["20240103", None], "end_date": ["20231231", "20230930"], "roe": [11.0, 9.0]}
        )

    def get_moneyflow(self, symbol, start, end):
        d = pd.bdate_range("2024-01-01", periods=3)
        td = [d[0].strftime("%Y%m%d"), None, d[2].strftime("%Y%m%d")]
        return pd.DataFrame({"trade_date": td, "net_mf_amount": [100, 200, 300]})


def test_build_panel_survives_null_ann_date_and_trade_date(tmp_path):
    # Regression: a None ann_date / trade_date is coerced to NaT and dropped,
    # not raised — the rest of the panel still builds.
    panel = build_panel(["AAA"], "20240101", "20240115", _NullDateProvider(), cache_dir=tmp_path)
    assert "AAA" in panel.symbols
    # the good fundamental row survives; the None-ann_date row was dropped
    fund = panel.latest_fundamental("AAA", pd.Timestamp("2024-01-10"))
    assert fund is not None and fund["roe"] == 11.0
    # moneyflow keeps only the valid-dated rows (no NaT index)
    mf = panel.moneyflow_history("AAA", pd.Timestamp("2024-01-10"))
    assert not mf.empty and bool(mf.index.notna().all())


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


class _AdjProvider(_FakeProvider):
    def __init__(self):
        self.adj_calls = 0

    def get_adj_factor(self, symbol, start, end):
        self.adj_calls += 1
        dates = pd.bdate_range("2024-01-01", periods=10)
        return pd.Series([1.0] * 5 + [2.0] * 5, index=dates, name="adj_factor")


def test_build_panel_fetches_and_caches_adj_factor(tmp_path):
    # Panel must carry adj_factor (total-return measurement needs it), fetched
    # via the provider, pickle-cached as {sym}_adj.pkl (same format the lowvol
    # portfolio backtest already writes), and served from cache on rerun.
    prov = _AdjProvider()
    panel = build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)
    assert "AAA" in panel.adj
    assert float(panel.adj["AAA"].iloc[-1]) == 2.0
    assert (tmp_path / "AAA_adj.pkl").exists()
    first = prov.adj_calls
    build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)
    assert prov.adj_calls == first  # cache hit, no refetch


def test_build_panel_tolerates_provider_without_adj_factor(tmp_path):
    # Legacy/stub providers (no get_adj_factor) must still build a panel; the
    # adj map is simply empty and forward returns fall back to raw closes.
    panel = build_panel(["AAA"], "20240101", "20240115", _FakeProvider(), cache_dir=tmp_path)
    assert "AAA" in panel.symbols
    assert panel.adj == {}


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
