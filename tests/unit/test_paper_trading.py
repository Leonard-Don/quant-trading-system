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


def test_buy_with_slippage_uses_effective_fill_price(store):
    # 10 bps = 0.1% — BUY pays a worse price than the user's fill_price.
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "slippage_bps": 10,
        },
        profile_id="alice",
    )
    order = result["order"]
    assert order["effective_fill_price"] == pytest.approx(100.10)
    assert order["slippage_bps"] == 10
    account = result["account"]
    # Cash debited at effective price × quantity (no commission)
    assert account["cash"] == pytest.approx(10000.0 - 1001.0)
    # Position avg_cost is the slipped (worse) price
    assert account["positions"][0]["avg_cost"] == pytest.approx(100.10)


def test_sell_with_slippage_credits_lower_proceeds(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    # 20 bps = 0.2% — SELL receives a worse price than the user's fill_price.
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 10,
            "fill_price": 110.0,
            "slippage_bps": 20,
        },
        profile_id="alice",
    )
    order = result["order"]
    assert order["effective_fill_price"] == pytest.approx(109.78)
    # Cash should reflect proceeds at slipped price: 10 × 109.78 = 1097.80
    expected_cash = 10000.0 - 1000.0 + 10 * 109.78
    assert result["account"]["cash"] == pytest.approx(expected_cash)


def test_zero_slippage_matches_pre_c2_behaviour(store):
    """Default slippage_bps=0 must give an order indistinguishable in
    cost / avg_cost / cash from the pre-C2 contract."""
    result_with_zero = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "slippage_bps": 0,
        },
        profile_id="alice",
    )
    assert result_with_zero["order"]["effective_fill_price"] == pytest.approx(100.0)
    assert result_with_zero["account"]["cash"] == pytest.approx(10000.0 - 500.0)
    assert result_with_zero["account"]["positions"][0]["avg_cost"] == pytest.approx(100.0)


def test_order_record_persists_both_fill_prices(store, tmp_path):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "fill_price": 200.0,
            "slippage_bps": 5,
        },
        profile_id="alice",
    )
    fresh = PaperTradingStore(storage_path=tmp_path)
    orders = fresh.list_orders(profile_id="alice")
    assert len(orders) == 1
    persisted = orders[0]
    assert persisted["fill_price"] == 200.0
    assert persisted["effective_fill_price"] == pytest.approx(200.10)
    assert persisted["slippage_bps"] == 5


def test_buy_with_stop_loss_pct_records_stop_loss_price_on_position(store):
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    position = result["account"]["positions"][0]
    assert position["stop_loss_pct"] == pytest.approx(0.05)
    assert position["stop_loss_price"] == pytest.approx(95.0)


def test_addon_buy_without_stop_loss_pct_keeps_old_pct_but_recomputes_price(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    # Add 10 more at 200 → new avg = 150, stop_loss should rebase to 150 × 0.95 = 142.5
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 200.0},
        profile_id="alice",
    )
    position = store.get_account(profile_id="alice")["positions"][0]
    assert position["stop_loss_pct"] == pytest.approx(0.05)
    assert position["avg_cost"] == pytest.approx(150.0)
    assert position["stop_loss_price"] == pytest.approx(142.5)


def test_addon_buy_with_new_stop_loss_pct_supersedes_old(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 200.0,
            "stop_loss_pct": 0.10,
        },
        profile_id="alice",
    )
    position = store.get_account(profile_id="alice")["positions"][0]
    assert position["stop_loss_pct"] == pytest.approx(0.10)
    assert position["stop_loss_price"] == pytest.approx(150.0 * 0.90)


def test_sell_ignores_stop_loss_pct_in_request(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    # SELL with stop_loss_pct shouldn't error or alter the (now-removed) position
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "fill_price": 110.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    assert result["account"]["positions"] == []


def test_buy_with_take_profit_pct_records_take_profit_price(store):
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    position = result["account"]["positions"][0]
    assert position["take_profit_pct"] == pytest.approx(0.10)
    assert position["take_profit_price"] == pytest.approx(110.0)


def test_addon_buy_recomputes_take_profit_price_against_new_avg(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "take_profit_pct": 0.20,
        },
        profile_id="alice",
    )
    # Add 10 more at 200 → new avg = 150, take_profit should rebase to 150 × 1.20 = 180
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 200.0},
        profile_id="alice",
    )
    position = store.get_account(profile_id="alice")["positions"][0]
    assert position["take_profit_pct"] == pytest.approx(0.20)
    assert position["take_profit_price"] == pytest.approx(180.0)


def test_buy_with_both_stop_loss_and_take_profit(store):
    """Both bands can coexist on the same position."""
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
        },
        profile_id="alice",
    )
    position = result["account"]["positions"][0]
    assert position["stop_loss_price"] == pytest.approx(95.0)
    assert position["take_profit_price"] == pytest.approx(115.0)


def test_limit_order_queues_into_pending_without_touching_cash(store):
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,  # ignored for LIMIT
            "limit_price": 95,
        },
        profile_id="alice",
    )
    account = result["account"]
    assert account["cash"] == pytest.approx(10000.0)  # cash untouched
    assert account["positions"] == []
    assert len(account["pending_orders"]) == 1
    pending = account["pending_orders"][0]
    assert pending["symbol"] == "AAPL"
    assert pending["side"] == "BUY"
    assert pending["limit_price"] == pytest.approx(95)
    assert pending["order_type"] == "LIMIT"
    assert pending["id"].startswith("ord-pending-")


def test_limit_order_without_limit_price_raises_business_error(store):
    with pytest.raises(PaperTradingError, match="limit_price is required"):
        store.submit_order(
            {
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 1,
                "order_type": "LIMIT",
                "fill_price": 100,
                # no limit_price
            },
            profile_id="alice",
        )


def test_cancel_pending_order_removes_it(store):
    result = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 95,
        },
        profile_id="alice",
    )
    pending_id = result["account"]["pending_orders"][0]["id"]
    after = store.cancel_order(pending_id, profile_id="alice")
    assert after["pending_orders"] == []


def test_cancel_already_filled_order_raises_business_error(store):
    result = store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 1, "fill_price": 100},
        profile_id="alice",
    )
    # The MARKET fill went to orders, not pending; trying to cancel by id
    # should give a clear "already filled" error.
    filled_id = store.list_orders(profile_id="alice")[0]["id"]
    with pytest.raises(PaperTradingError, match="already filled"):
        store.cancel_order(filled_id, profile_id="alice")


def test_cancel_unknown_order_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.cancel_order("ord-nonexistent", profile_id="alice")


def test_endpoint_delete_pending_order_returns_account_view(client):
    api, _ = client
    posted = api.post(
        "/paper/orders",
        json={
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 95,
        },
    ).json()
    pending_id = posted["data"]["account"]["pending_orders"][0]["id"]

    response = api.delete(f"/paper/orders/{pending_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["pending_orders"] == []


def test_endpoint_delete_unknown_order_returns_404(client):
    api, _ = client
    response = api.delete("/paper/orders/ord-doesnotexist")
    assert response.status_code == 404


def test_endpoint_rejects_excessive_take_profit_pct(client):
    api, _ = client
    response = api.post(
        "/paper/orders",
        json={
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "fill_price": 100,
            "take_profit_pct": 6.0,  # > 5.0 cap
        },
    )
    assert response.status_code == 422


def test_endpoint_rejects_excessive_stop_loss_pct(client):
    api, _ = client
    response = api.post(
        "/paper/orders",
        json={
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "fill_price": 100,
            "stop_loss_pct": 0.6,  # > 0.5 cap
        },
    )
    assert response.status_code == 422


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


def test_endpoint_rejects_excessive_slippage_bps(client):
    api, _ = client
    response = api.post(
        "/paper/orders",
        json={
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "fill_price": 100,
            "slippage_bps": 200,  # > 100 cap
        },
    )
    assert response.status_code == 422


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
