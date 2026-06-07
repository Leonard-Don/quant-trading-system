import pandas as pd

from src.data.factor_panel import FactorPanel, build_panel


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
