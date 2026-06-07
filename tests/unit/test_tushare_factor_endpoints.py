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
