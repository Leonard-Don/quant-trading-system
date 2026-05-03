"""Unit tests for the paper trading store and HTTP surface (v0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.services.paper_trading import (
    PaperTradingError,
    PaperTradingStore,
)


# ---------------------------------------------------------------------------
# Service-level tests (PaperTradingStore)
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> PaperTradingStore:
    return PaperTradingStore(storage_path=tmp_path)


def test_default_account_starts_at_initial_capital(store):
    account = store.get_account(profile_id="alice")
    assert account["initial_capital"] == 10000.0
    assert account["cash"] == 10000.0
    assert account["positions"] == []
    assert account["orders_count"] == 0
    assert account["profile_id"] == "alice"


def test_buy_decreases_cash_and_opens_position(store):
    result = store.submit_order(
        {"symbol": "aapl", "side": "BUY", "quantity": 10, "fill_price": 150.0},
        profile_id="alice",
    )
    account = result["account"]
    assert account["cash"] == pytest.approx(10000.0 - 1500.0)
    assert len(account["positions"]) == 1
    position = account["positions"][0]
    assert position["symbol"] == "AAPL"
    assert position["quantity"] == 10
    assert position["avg_cost"] == 150.0


def test_repeated_buys_use_weighted_avg_cost(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 200.0},
        profile_id="alice",
    )
    account = store.get_account(profile_id="alice")
    position = account["positions"][0]
    assert position["quantity"] == 20
    assert position["avg_cost"] == pytest.approx(150.0)


def test_partial_sell_reduces_position(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 4, "fill_price": 120.0},
        profile_id="alice",
    )
    account = store.get_account(profile_id="alice")
    assert account["cash"] == pytest.approx(10000.0 - 1000.0 + 480.0)
    assert account["positions"][0]["quantity"] == 6
    # avg_cost survives a partial sell
    assert account["positions"][0]["avg_cost"] == pytest.approx(100.0)


def test_full_sell_removes_position_key(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 10, "fill_price": 120.0},
        profile_id="alice",
    )
    account = store.get_account(profile_id="alice")
    assert account["positions"] == []


def test_buy_rejects_when_cash_insufficient(store):
    with pytest.raises(PaperTradingError, match="insufficient cash"):
        store.submit_order(
            {"symbol": "AAPL", "side": "BUY", "quantity": 1000, "fill_price": 200.0},
            profile_id="alice",
        )
    # Account state unchanged
    account = store.get_account(profile_id="alice")
    assert account["cash"] == 10000.0
    assert account["positions"] == []


def test_sell_rejects_when_position_insufficient(store):
    with pytest.raises(PaperTradingError, match="insufficient position"):
        store.submit_order(
            {"symbol": "AAPL", "side": "SELL", "quantity": 5, "fill_price": 100.0},
            profile_id="alice",
        )


def test_reset_returns_to_initial_capital(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    reset_account = store.reset(initial_capital=20000.0, profile_id="alice")
    assert reset_account["cash"] == 20000.0
    assert reset_account["initial_capital"] == 20000.0
    assert reset_account["positions"] == []
    # And the file on disk is also reset
    fetched = store.get_account(profile_id="alice")
    assert fetched["cash"] == 20000.0


def test_per_profile_isolation(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    bob_account = store.get_account(profile_id="bob")
    assert bob_account["cash"] == 10000.0
    assert bob_account["positions"] == []


def test_persistence_round_trip(store, tmp_path):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    # New store on the same path should see the existing account
    fresh = PaperTradingStore(storage_path=tmp_path)
    account = fresh.get_account(profile_id="alice")
    assert account["positions"][0]["symbol"] == "AAPL"
    assert account["cash"] == pytest.approx(9000.0)


def test_orders_returned_newest_first(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 1, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "MSFT", "side": "BUY", "quantity": 1, "fill_price": 200.0},
        profile_id="alice",
    )
    orders = store.list_orders(profile_id="alice")
    assert len(orders) == 2
    assert orders[0]["symbol"] == "MSFT"
    assert orders[1]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# HTTP-level tests (FastAPI endpoints)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """Wire the API to a temp-storage store so test runs don't touch real data/."""
    isolated_store = PaperTradingStore(storage_path=tmp_path)
    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.paper_trading.paper_trading_store",
        isolated_store,
    )
    from backend.main import app

    return TestClient(app), tmp_path


def test_endpoint_get_account_default(client):
    api, _ = client
    response = api.get("/paper/account")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cash"] == 10000.0
    assert data["positions"] == []


def test_endpoint_submit_buy_then_sell(client):
    api, _ = client
    buy = api.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
    )
    assert buy.status_code == 200
    sell = api.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "SELL", "quantity": 5, "fill_price": 110.0},
    )
    assert sell.status_code == 200
    account = api.get("/paper/account").json()["data"]
    assert account["positions"] == []
    assert account["cash"] == pytest.approx(10000.0 + 50.0)


def test_endpoint_business_error_returns_422(client):
    api, _ = client
    response = api.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 1000, "fill_price": 200.0},
    )
    assert response.status_code == 422
    body = response.json()
    # Backend wraps HTTPException in a {success, error: {code, message}} envelope
    message = (body.get("error") or {}).get("message") or body.get("detail") or ""
    assert "insufficient cash" in message.lower()


def test_endpoint_reset(client):
    api, _ = client
    api.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
    )
    reset = api.post("/paper/reset", json={"initial_capital": 50000})
    assert reset.status_code == 200
    data = reset.json()["data"]
    assert data["cash"] == 50000.0
    assert data["positions"] == []


def test_endpoint_profile_header_isolation(client, tmp_path):
    api, storage = client
    api.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        headers={"X-Research-Profile": "alice"},
    )
    bob_account = api.get(
        "/paper/account", headers={"X-Research-Profile": "bob"}
    ).json()["data"]
    assert bob_account["cash"] == 10000.0
    assert bob_account["positions"] == []
    # alice's file should exist on disk
    assert (storage / "alice.json").exists()
    with open(storage / "alice.json", encoding="utf-8") as file:
        persisted = json.load(file)
    assert "AAPL" in persisted["positions"]
