"""Tests for the deprecated /trade/* compat shim.

The four legacy routes now delegate to the persistent paper-trading engine
using the DEFAULT paper profile (no header / profile_id=None). These tests
assert (a) the shim mutates the same paper account a /paper/* caller sees,
and (b) each route preserves its legacy REST response shape so existing
callers keep working.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import paper_trading, trading
from backend.app.core.error_handler import register_exception_handlers
from backend.app.services.paper_trading import PaperTradingStore


@pytest.fixture
def trading_client(tmp_path: Path, monkeypatch):
    """Wire both the /trade shim and the /paper surface to one temp-path store
    so we can prove the shim and the paper engine share state."""
    isolated_store = PaperTradingStore(storage_path=tmp_path)
    monkeypatch.setattr(trading, "paper_trading_store", isolated_store)
    monkeypatch.setattr(paper_trading, "paper_trading_store", isolated_store)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(trading.router, prefix="/trade")
    app.include_router(paper_trading.router, prefix="/paper")
    return TestClient(app)


def test_execute_buy_uses_supplied_price_and_hits_paper_default_account(trading_client):
    response = trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 150.0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    # Legacy /trade/execute response shape (Trade dict).
    trade = payload["data"]
    assert trade["symbol"] == "AAPL"
    assert trade["action"] == "BUY"
    assert trade["quantity"] == 10
    assert trade["price"] == 150.0
    assert trade["total_amount"] == pytest.approx(1500.0)
    assert "id" in trade
    assert "timestamp" in trade
    assert trade["balance_after"] == pytest.approx(10000.0 - 1500.0)

    # The same default paper profile reflects the order.
    account = trading_client.get("/paper/account").json()["data"]
    assert account["profile_id"] == "default"
    assert account["cash"] == pytest.approx(10000.0 - 1500.0)
    assert len(account["positions"]) == 1
    assert account["positions"][0]["symbol"] == "AAPL"
    assert account["positions"][0]["quantity"] == 10


def test_execute_then_portfolio_reflects_state_via_paper_engine(trading_client):
    trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 150.0},
    )

    response = trading_client.get("/trade/portfolio")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    portfolio = payload["data"]
    # Legacy /trade/portfolio response shape.
    assert portfolio["balance"] == pytest.approx(10000.0 - 1500.0)
    assert "total_equity" in portfolio
    assert "total_market_value" in portfolio
    assert "total_pnl" in portfolio
    assert "total_pnl_percent" in portfolio
    assert portfolio["trade_count"] == 1
    assert len(portfolio["positions"]) == 1
    position = portfolio["positions"][0]
    assert position["symbol"] == "AAPL"
    assert position["quantity"] == 10
    assert position["avg_price"] == pytest.approx(150.0)
    # Position display fields preserved from legacy shape.
    assert "current_price" in position
    assert "market_value" in position
    assert "unrealized_pnl" in position
    assert "unrealized_pnl_percent" in position


def test_history_returns_legacy_trade_records_from_paper_engine(trading_client):
    trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 100.0},
    )
    trading_client.post(
        "/trade/execute",
        json={"symbol": "MSFT", "action": "BUY", "quantity": 5, "price": 200.0},
    )

    response = trading_client.get("/trade/history?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    history = payload["data"]
    assert isinstance(history, list)
    assert len(history) == 2
    # Newest first (paper list_orders sorts desc by submitted_at).
    symbols = {record["symbol"] for record in history}
    assert symbols == {"AAPL", "MSFT"}
    for record in history:
        # Legacy Trade record shape.
        assert "id" in record
        assert "timestamp" in record
        assert record["action"] in {"BUY", "SELL"}
        assert "quantity" in record
        assert "price" in record
        assert "total_amount" in record
        assert "balance_after" in record


def test_reset_clears_paper_default_account(trading_client):
    trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 150.0},
    )
    # Sanity: account changed.
    pre = trading_client.get("/paper/account").json()["data"]
    assert pre["cash"] != pytest.approx(10000.0)

    response = trading_client.post("/trade/reset")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "message" in payload

    account = trading_client.get("/paper/account").json()["data"]
    assert account["cash"] == pytest.approx(10000.0)
    assert account["positions"] == []
    assert account["orders_count"] == 0


def test_execute_without_price_falls_back_to_realtime_quote(trading_client, monkeypatch):
    monkeypatch.setattr(
        trading.realtime_manager,
        "get_quote_dict",
        lambda symbol, use_cache=True: {"symbol": symbol, "price": 321.45},
    )

    response = trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 1},
    )
    assert response.status_code == 200
    trade = response.json()["data"]
    assert trade["price"] == pytest.approx(321.45)


def test_execute_missing_price_keeps_400_response(trading_client, monkeypatch):
    monkeypatch.setattr(
        trading.realtime_manager,
        "get_quote_dict",
        lambda symbol, use_cache=True: None,
    )
    monkeypatch.setattr(trading.data_manager, "get_latest_price", lambda symbol: None)

    response = trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 10},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "HTTP_ERROR"
    assert payload["error"]["message"] == "无法获取 AAPL 的最新价格"


def test_execute_insufficient_cash_returns_400(trading_client):
    response = trading_client.post(
        "/trade/execute",
        json={"symbol": "AAPL", "action": "BUY", "quantity": 1000, "price": 150.0},
    )
    # Paper engine raises PaperTradingError (a ValueError) -> mapped to 400.
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False


def test_routes_are_marked_deprecated(trading_client):
    """All four /trade routes carry deprecated=True in the OpenAPI schema."""
    schema = trading_client.get("/openapi.json").json()
    paths = schema["paths"]
    assert paths["/trade/portfolio"]["get"]["deprecated"] is True
    assert paths["/trade/execute"]["post"]["deprecated"] is True
    assert paths["/trade/history"]["get"]["deprecated"] is True
    assert paths["/trade/reset"]["post"]["deprecated"] is True
