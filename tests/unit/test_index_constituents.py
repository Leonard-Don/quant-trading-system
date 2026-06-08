from unittest.mock import MagicMock

import pandas as pd

import src.data.providers.tushare_provider as tp


def _provider_with_mock(monkeypatch, weight_df):
    monkeypatch.setenv("TUSHARE_TOKEN", "")  # isolation
    p = tp.TushareProvider()
    # Reset class-level / instance throttle + cache state (repo test-isolation convention).
    p.clear_cache()
    p.reset_throttle()
    fake_pro = MagicMock()
    fake_pro.index_weight.return_value = weight_df
    # The real pro-client accessor is _get_pro_client (see tushare_provider.py).
    monkeypatch.setattr(p, "_get_pro_client", lambda: fake_pro, raising=False)
    return p, fake_pro


def test_get_index_constituents_returns_con_codes(monkeypatch):
    # index_weight returns one row per (trade_date, con_code).
    df = pd.DataFrame(
        {
            "index_code": ["000300.SH"] * 4,
            "con_code": ["600519.SH", "000858.SZ", "601318.SH", "300750.SZ"],
            "trade_date": ["20231229"] * 4,
            "weight": [5.2, 1.1, 2.3, 0.9],
        }
    )
    p, fake_pro = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH")
    assert out == ["600519.SH", "000858.SZ", "601318.SH", "300750.SZ"]
    # called the real tushare index_weight endpoint with the index code
    assert fake_pro.index_weight.called
    _, kwargs = fake_pro.index_weight.call_args
    assert kwargs.get("index_code") == "000300.SH"


def test_get_index_constituents_uses_latest_trade_date(monkeypatch):
    # Multiple periods present -> only the latest trade_date's constituents.
    df = pd.DataFrame(
        {
            "index_code": ["000300.SH"] * 4,
            "con_code": ["AAA.SH", "BBB.SZ", "600519.SH", "000858.SZ"],
            "trade_date": ["20231130", "20231130", "20231229", "20231229"],
            "weight": [1.0, 1.0, 5.0, 2.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH")
    assert set(out) == {"600519.SH", "000858.SZ"}  # only latest period
    assert "AAA.SH" not in out


def test_get_index_constituents_empty_frame(monkeypatch):
    p, _ = _provider_with_mock(monkeypatch, pd.DataFrame())
    assert p.get_index_constituents("000300.SH") == []


def test_get_index_constituents_dedupes_and_preserves_order(monkeypatch):
    df = pd.DataFrame(
        {
            "con_code": ["600519.SH", "000858.SZ", "600519.SH"],
            "trade_date": ["20231229"] * 3,
            "weight": [5.0, 2.0, 5.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH")
    assert out == ["600519.SH", "000858.SZ"]


def test_get_index_constituents_point_in_time_ends_at_asof(monkeypatch):
    # When a trade_date is given, index_weight must be queried AS-OF that date
    # (end_date == as-of) so the returned constituents are point-in-time.
    df = pd.DataFrame(
        {
            "con_code": ["AAA.SH", "BBB.SZ"],
            "trade_date": ["20200630", "20200630"],
            "weight": [1.0, 2.0],
        }
    )
    p, fake_pro = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH", trade_date="20200701")
    assert set(out) == {"AAA.SH", "BBB.SZ"}
    _, kwargs = fake_pro.index_weight.call_args
    assert kwargs.get("index_code") == "000300.SH"
    # The as-of query ends at the as-of date (point-in-time, no look-ahead).
    assert kwargs.get("end_date") == "20200701"


def test_get_index_constituents_point_in_time_keeps_latest_le_asof(monkeypatch):
    # index_weight may return several published periods inside the lookback;
    # the as-of query keeps only the latest published period.
    df = pd.DataFrame(
        {
            "con_code": ["OLD.SH", "NEW1.SH", "NEW2.SZ"],
            "trade_date": ["20200430", "20200630", "20200630"],
            "weight": [1.0, 5.0, 2.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH", trade_date="20200701")
    assert set(out) == {"NEW1.SH", "NEW2.SZ"}
    assert "OLD.SH" not in out


def test_get_index_constituents_default_still_latest(monkeypatch):
    # Back-compat: no trade_date -> current/latest behavior unchanged.
    df = pd.DataFrame(
        {
            "con_code": ["600519.SH", "000858.SZ"],
            "trade_date": ["20231229"] * 2,
            "weight": [5.0, 2.0],
        }
    )
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_index_constituents("000300.SH")
    assert out == ["600519.SH", "000858.SZ"]
