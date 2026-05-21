"""Tests for the akshare-backed ETF historical price loader."""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timedelta
from typing import Any, Dict

import pandas as pd
import pytest

from src.data import etf_price_history

# ---------------------------------------------------------------------------
# Proxy blackout
# ---------------------------------------------------------------------------


def test_proxy_blackout_restores_env(monkeypatch) -> None:
    """Proxy env vars are cleared during the fetch but restored on exit."""

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.com:8080")
    monkeypatch.setenv("NO_PROXY", "internal")
    original_get = __import__("urllib.request", fromlist=["request"]).getproxies

    with etf_price_history._proxy_blackout():
        assert os.environ["HTTPS_PROXY"] == ""
        assert os.environ["NO_PROXY"] == "*"

    assert os.environ["HTTPS_PROXY"] == "http://proxy.example.com:8080"
    assert os.environ["NO_PROXY"] == "internal"
    # urllib.request.getproxies must be restored to whatever was active.
    import urllib.request
    assert urllib.request.getproxies is original_get


def test_proxy_blackout_handles_unset_vars(monkeypatch) -> None:
    """Variables that were unset must remain unset after exit."""

    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)

    with etf_price_history._proxy_blackout():
        pass

    assert "HTTP_PROXY" not in os.environ
    assert "NO_PROXY" not in os.environ


# ---------------------------------------------------------------------------
# fetch_etf_history error paths
# ---------------------------------------------------------------------------


def test_fetch_etf_history_empty_codes_returns_empty() -> None:
    assert etf_price_history.fetch_etf_history([]).empty


def test_fetch_etf_history_returns_empty_when_akshare_missing(monkeypatch) -> None:
    monkeypatch.setattr(etf_price_history, "_import_akshare", lambda: None)
    assert etf_price_history.fetch_etf_history(["510300"]).empty


# ---------------------------------------------------------------------------
# Sina endpoint normalization
# ---------------------------------------------------------------------------


def _fake_sina_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14"],
        "open": [4.90, 4.92, 4.95, 4.97, 5.04],
        "high": [4.95, 4.98, 5.00, 5.02, 5.04],
        "low": [4.88, 4.91, 4.93, 4.94, 4.93],
        "close": [4.92, 4.95, 4.96, 5.02, 4.94],
        "volume": [10000, 10100, 10200, 10300, 10400],
    })


def test_fetch_etf_history_prefers_sina_endpoint(monkeypatch) -> None:
    calls: Dict[str, Any] = {"sina": 0, "em": 0}

    def fake_sina(symbol: str) -> pd.DataFrame:
        calls["sina"] += 1
        calls["last_symbol"] = symbol
        return _fake_sina_frame()

    def fake_em(**_: Any) -> pd.DataFrame:
        calls["em"] += 1
        return pd.DataFrame()

    fake_ak = types.SimpleNamespace(
        fund_etf_hist_sina=fake_sina,
        fund_etf_hist_em=fake_em,
        __version__="fake-1.0",
    )
    monkeypatch.setattr(etf_price_history, "_import_akshare", lambda: fake_ak)

    matrix = etf_price_history.fetch_etf_history(["510300"])

    assert calls["sina"] == 1
    assert calls["em"] == 0  # Sina succeeded, EM untouched
    assert calls["last_symbol"] == "sh510300"  # prefix derived correctly
    assert list(matrix.columns) == ["510300"]
    assert matrix.iloc[-1]["510300"] == pytest.approx(4.94)


def test_fetch_etf_history_falls_back_to_eastmoney(monkeypatch) -> None:
    """When Sina raises, the EM endpoint should be tried instead."""

    def failing_sina(symbol: str) -> pd.DataFrame:
        raise RuntimeError("simulated sina outage")

    em_frame = pd.DataFrame({
        "日期": ["2026-05-13", "2026-05-14"],
        "收盘": [5.02, 4.94],
    })

    def fake_em(**_: Any) -> pd.DataFrame:
        return em_frame

    fake_ak = types.SimpleNamespace(
        fund_etf_hist_sina=failing_sina,
        fund_etf_hist_em=fake_em,
        __version__="fake-1.0",
    )
    monkeypatch.setattr(etf_price_history, "_import_akshare", lambda: fake_ak)

    matrix = etf_price_history.fetch_etf_history(["510300"])
    assert not matrix.empty
    assert matrix.iloc[-1]["510300"] == pytest.approx(4.94)


def test_fetch_etf_history_returns_empty_when_both_endpoints_fail(monkeypatch) -> None:
    def failing(*_: Any, **__: Any) -> pd.DataFrame:
        raise RuntimeError("network down")

    fake_ak = types.SimpleNamespace(
        fund_etf_hist_sina=failing,
        fund_etf_hist_em=failing,
        __version__="fake-1.0",
    )
    monkeypatch.setattr(etf_price_history, "_import_akshare", lambda: fake_ak)

    matrix = etf_price_history.fetch_etf_history(["510300", "159985"])
    assert matrix.empty


def test_fetch_etf_history_trims_to_requested_window(monkeypatch) -> None:
    """When the upstream returns wider history than requested, the result
    must be trimmed to ``[start_date, end_date]``."""

    def fake_sina(symbol: str) -> pd.DataFrame:
        return pd.DataFrame({
            "date": pd.bdate_range("2024-01-02", periods=60).strftime("%Y-%m-%d"),
            "close": [4.0 + i * 0.01 for i in range(60)],
        })

    fake_ak = types.SimpleNamespace(fund_etf_hist_sina=fake_sina, __version__="fake")
    monkeypatch.setattr(etf_price_history, "_import_akshare", lambda: fake_ak)

    matrix = etf_price_history.fetch_etf_history(
        ["510300"],
        start_date=datetime(2024, 2, 1),
        end_date=datetime(2024, 2, 28),
    )
    # All dates inside the requested window only.
    assert matrix.index.min() >= pd.Timestamp("2024-02-01")
    assert matrix.index.max() <= pd.Timestamp("2024-02-28")


# ---------------------------------------------------------------------------
# Sina symbol mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, expected",
    [
        ("510300", "sh510300"),  # 5* → SH
        ("588000", "sh588000"),  # 5* → SH
        ("159985", "sz159985"),  # 1*9 → SZ (Shenzhen ETF)
        ("600519", "sh600519"),  # 6* → SH
        ("000001", "sz000001"),  # 0* → SZ
        ("sh510300", "sh510300"),  # already prefixed
    ],
)
def test_sina_symbol_mapping(code: str, expected: str) -> None:
    assert etf_price_history._sina_symbol(code) == expected
