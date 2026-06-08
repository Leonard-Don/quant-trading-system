from unittest.mock import MagicMock

import pandas as pd

import src.data.providers.tushare_provider as tp


def _provider_with_mock(monkeypatch, df):
    monkeypatch.setenv("TUSHARE_TOKEN", "")  # isolation
    p = tp.TushareProvider()
    # Reset class-level / instance throttle + cache state (repo test-isolation convention).
    p.clear_cache()
    p.reset_throttle()
    fake_pro = MagicMock()
    fake_pro.fina_indicator.return_value = df
    fake_pro.moneyflow.return_value = df
    # The real pro-client accessor is _get_pro_client (see tushare_provider.py).
    monkeypatch.setattr(p, "_get_pro_client", lambda: fake_pro, raising=False)
    return p, fake_pro


def test_get_financial_indicators_keeps_ann_date(monkeypatch):
    df = pd.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "ann_date": ["20240101"],
            "end_date": ["20231231"],
            "roe": [12.0],
            "netprofit_yoy": [5.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_financial_indicators("600000.SH", "20230101", "20240101")
    assert "ann_date" in out.columns and "roe" in out.columns
    assert len(out) == 1


def test_get_moneyflow_returns_frame(monkeypatch):
    df = pd.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "trade_date": ["20240101"],
            "net_mf_amount": [1234.0],
            "buy_lg_amount": [50.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_moneyflow("600000.SH", "20230101", "20240101")
    assert "net_mf_amount" in out.columns


def _provider_with_suspend_mock(monkeypatch, suspend_df):
    monkeypatch.setenv("TUSHARE_TOKEN", "")  # isolation
    p = tp.TushareProvider()
    p.clear_cache()
    p.reset_throttle()
    fake_pro = MagicMock()
    fake_pro.suspend_d.return_value = suspend_df
    monkeypatch.setattr(p, "_get_pro_client", lambda: fake_pro, raising=False)
    return p, fake_pro


def test_get_suspended_symbols_returns_set(monkeypatch):
    df = pd.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ", "300750.SZ"],
            "trade_date": ["20200701"] * 3,
            "suspend_type": ["S"] * 3,
        }
    )
    p, fake_pro = _provider_with_suspend_mock(monkeypatch, df)
    out = p.get_suspended_symbols("20200701")
    assert out == {"600000.SH", "000001.SZ", "300750.SZ"}
    # suspend_d queried by date with suspend_type='S' (currently suspended).
    _, kwargs = fake_pro.suspend_d.call_args
    assert kwargs.get("suspend_type") == "S"
    assert kwargs.get("trade_date") == "20200701"


def test_get_suspended_symbols_empty_on_no_data(monkeypatch):
    p, _ = _provider_with_suspend_mock(monkeypatch, pd.DataFrame())
    assert p.get_suspended_symbols("20200701") == set()


def test_get_suspended_symbols_empty_on_error(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    p = tp.TushareProvider()
    p.clear_cache()
    p.reset_throttle()
    fake_pro = MagicMock()
    fake_pro.suspend_d.side_effect = RuntimeError("tushare boom")
    monkeypatch.setattr(p, "_get_pro_client", lambda: fake_pro, raising=False)
    # Any client error degrades to an empty set (never raises).
    assert p.get_suspended_symbols("20200701") == set()
