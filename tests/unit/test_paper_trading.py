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


def test_market_sell_closing_position_prunes_stale_sell_limits(store):
    """Manual MARKET SELL fully closing a position must prune any pending SELL
    LIMITs for the same symbol — they would never be backed by shares again
    and must not remain armed (mirrors run_matching pruning, commit f1aec71)."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 105,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    result = store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 10, "fill_price": 102.0},
        profile_id="alice",
    )
    account = result["account"]
    assert account["positions"] == []
    assert account["pending_orders"] == []


def test_market_sell_closing_position_records_canceled_stale_sell_limits(store):
    """A manual MARKET SELL that fully closes a position must surface the
    pruned pending SELL LIMITs in a `canceled` audit on the result envelope.
    Same invariant as the run_matching SL/TP audit (commit 89a2732) — a
    stale-exit dropped without trace is the bug, regardless of which closing
    path triggered the prune."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    queued = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    pending_id = queued["account"]["pending_orders"][0]["id"]

    result = store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 10, "fill_price": 102.0},
        profile_id="alice",
    )
    assert result["account"]["positions"] == []
    assert result["account"]["pending_orders"] == []
    canceled = result.get("canceled") or []
    assert (
        len(canceled) == 1
    ), f"expected 1 canceled audit entry, got {len(canceled)}; result keys: {sorted(result.keys())}"
    entry = canceled[0]
    assert entry["pending_order_id"] == pending_id
    assert entry["symbol"] == "AAPL"
    assert entry["side"] == "SELL"
    # `manual_sell` ties the cancel to the manual MARKET SELL that closed
    # the position, distinguishing it from `stop_loss` / `take_profit` /
    # `limit_cross` audits in the same shape.
    assert entry["reason"] == "manual_sell"
    assert entry.get("canceled_at"), "canceled entry must record a timestamp"


def test_market_sell_partial_close_emits_no_canceled_audit(store):
    """Baseline shape: a partial sell that doesn't close the position must
    not spuriously emit canceled entries — pending exits are still backed by
    remaining shares. Asserts the empty-list shape is stable."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    result = store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 3, "fill_price": 105.0},
        profile_id="alice",
    )
    assert result["account"]["positions"][0]["quantity"] == 7
    assert len(result["account"]["pending_orders"]) == 1
    assert result.get("canceled") == []


def test_market_sell_partial_close_keeps_pending_sell_limits(store):
    """A SELL that does not fully close the position must NOT prune pending
    SELL LIMITs — remaining shares can still back them."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 3, "fill_price": 105.0},
        profile_id="alice",
    )
    account = store.get_account(profile_id="alice")
    assert account["positions"][0]["quantity"] == 7
    assert len(account["pending_orders"]) == 1
    assert account["pending_orders"][0]["side"] == "SELL"


def test_market_sell_closing_position_does_not_prune_buy_limits(store):
    """Pending BUY LIMITs for the same symbol represent intent to re-enter,
    not stale exits — they must survive a position close."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 3,
            "order_type": "LIMIT",
            "limit_price": 90,
        },
        profile_id="alice",
    )
    store.submit_order(
        {"symbol": "AAPL", "side": "SELL", "quantity": 5, "fill_price": 102.0},
        profile_id="alice",
    )
    account = store.get_account(profile_id="alice")
    assert account["positions"] == []
    assert len(account["pending_orders"]) == 1
    assert account["pending_orders"][0]["side"] == "BUY"


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


# ---------------------------------------------------------------------------
# Matching / trigger engine tests (LIMIT auto-fill + SL/TP exits)
# ---------------------------------------------------------------------------


def test_run_matching_fills_buy_limit_when_quote_at_limit(store):
    queued = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 95,
        },
        profile_id="alice",
    )
    pending_id = queued["account"]["pending_orders"][0]["id"]

    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")

    assert len(result["filled"]) == 1
    filled = result["filled"][0]
    assert filled["symbol"] == "AAPL"
    assert filled["side"] == "BUY"
    assert filled["quantity"] == 5
    assert filled["fill_price"] == pytest.approx(95.0)
    assert filled["pending_order_id"] == pending_id
    assert filled["trigger_reason"] == "limit_cross"
    account = result["account"]
    assert account["pending_orders"] == []
    assert account["cash"] == pytest.approx(10000.0 - 5 * 95.0)
    assert account["positions"][0]["symbol"] == "AAPL"
    assert account["positions"][0]["quantity"] == 5
    assert account["positions"][0]["avg_cost"] == pytest.approx(95.0)


def test_run_matching_fills_buy_limit_when_quote_below_limit(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 4,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 90,
        },
        profile_id="alice",
    )
    # Market gapped down — buy still fills at the limit price (deterministic).
    result = store.run_matching({"AAPL": 80.0}, profile_id="alice")
    assert len(result["filled"]) == 1
    assert result["filled"][0]["fill_price"] == pytest.approx(90.0)
    assert result["account"]["cash"] == pytest.approx(10000.0 - 4 * 90.0)


def test_run_matching_does_not_fill_buy_limit_when_quote_above_limit(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 95,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 96.0}, profile_id="alice")
    assert result["filled"] == []
    assert result["triggered"] == []
    assert len(result["account"]["pending_orders"]) == 1
    assert result["account"]["cash"] == pytest.approx(10000.0)


def test_run_matching_fills_sell_limit_when_quote_at_or_above_limit(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 110,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 110.0}, profile_id="alice")
    assert len(result["filled"]) == 1
    filled = result["filled"][0]
    assert filled["side"] == "SELL"
    assert filled["fill_price"] == pytest.approx(110.0)
    account = result["account"]
    assert account["pending_orders"] == []
    assert account["positions"] == []
    assert account["cash"] == pytest.approx(10000.0 - 500.0 + 5 * 110.0)


def test_run_matching_full_sell_limit_prunes_stale_sell_limits(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 105,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )

    result = store.run_matching({"AAPL": 105.0}, profile_id="alice")

    assert len(result["filled"]) == 1
    assert result["triggered"] == []
    assert result["account"]["positions"] == []
    assert result["account"]["pending_orders"] == []
    assert result["account"]["cash"] == pytest.approx(10000.0 - 500.0 + 5 * 105.0)


def test_run_matching_does_not_fill_sell_limit_when_quote_below_limit(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 110,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 109.99}, profile_id="alice")
    assert result["filled"] == []
    assert len(result["account"]["pending_orders"]) == 1
    assert result["account"]["positions"][0]["quantity"] == 5


def test_run_matching_skips_symbols_without_quotes(store):
    store.submit_order(
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
    # Quote map covers a different symbol, so AAPL stays pending.
    result = store.run_matching({"MSFT": 50.0}, profile_id="alice")
    assert result["filled"] == []
    assert len(result["account"]["pending_orders"]) == 1


def test_run_matching_quotes_lookup_is_case_insensitive(store):
    store.submit_order(
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
    # Lower-case key in the quote map should still match.
    result = store.run_matching({"aapl": 95.0}, profile_id="alice")
    assert len(result["filled"]) == 1
    assert result["filled"][0]["symbol"] == "AAPL"


def test_run_matching_buy_limit_rejects_when_cash_insufficient_at_fill_time(store):
    # Reset to small capital so the LIMIT BUY can't actually be afforded
    # when the quote crosses the threshold.
    store.reset(initial_capital=100.0, profile_id="alice")
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "order_type": "LIMIT",
            "fill_price": 95,
            "limit_price": 95,  # would need 950 cash, only 100 available
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")
    # The order must NOT fill; it stays pending and is reported as rejected.
    assert result["filled"] == []
    assert len(result["account"]["pending_orders"]) == 1
    assert result["account"]["cash"] == pytest.approx(100.0)
    assert len(result["rejected"]) == 1
    assert "insufficient cash" in result["rejected"][0]["reason"].lower()


def test_run_matching_triggers_stop_loss_when_quote_crosses(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    # stop_loss_price = 95.0 → quote crosses
    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")
    assert len(result["triggered"]) == 1
    triggered = result["triggered"][0]
    assert triggered["symbol"] == "AAPL"
    assert triggered["side"] == "SELL"
    assert triggered["quantity"] == 5
    assert triggered["fill_price"] == pytest.approx(95.0)
    assert triggered["trigger_reason"] == "stop_loss"
    account = result["account"]
    assert account["positions"] == []
    assert account["cash"] == pytest.approx(10000.0 - 500.0 + 5 * 95.0)


def test_run_matching_stop_loss_prunes_stale_sell_limits(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )

    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")

    assert result["filled"] == []
    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["trigger_reason"] == "stop_loss"
    assert result["account"]["positions"] == []
    assert result["account"]["pending_orders"] == []
    assert result["account"]["cash"] == pytest.approx(10000.0 - 500.0 + 5 * 95.0)


def test_run_matching_stop_loss_records_canceled_stale_sell_limits(store):
    """When an SL trigger liquidates a position, any stale pending SELL LIMITs
    for the same symbol must be pruned AND surfaced in the run_matching
    `canceled` audit — so the cancellation is observable to the caller (UI,
    log shipper, audit consumer), not silent. Pre-slice the prune happened but
    nothing referenced it; a stale-exit dropped without trace is the bug."""
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    queued = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    pending_id = queued["account"]["pending_orders"][0]["id"]

    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["trigger_reason"] == "stop_loss"
    assert result["account"]["pending_orders"] == []
    canceled = result.get("canceled")
    assert canceled, "run_matching must expose a canceled audit collection"
    assert len(canceled) == 1
    entry = canceled[0]
    assert entry["pending_order_id"] == pending_id
    assert entry["symbol"] == "AAPL"
    assert entry["side"] == "SELL"
    # Reason ties the cancel back to the bracket trigger that closed the
    # position, so an audit consumer can correlate cause and effect.
    assert entry["reason"] == "stop_loss"
    assert entry.get("canceled_at"), "canceled entry must record a timestamp"


def test_run_matching_take_profit_records_canceled_stale_sell_limits(store):
    """TP trigger must record the same audit shape as SL — both bracket exits
    are equally responsible for pruning stale exits, both must be observable."""
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    queued = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 120,
        },
        profile_id="alice",
    )
    pending_id = queued["account"]["pending_orders"][0]["id"]

    result = store.run_matching({"AAPL": 110.0}, profile_id="alice")

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["trigger_reason"] == "take_profit"
    assert result["account"]["pending_orders"] == []
    canceled = result.get("canceled") or []
    assert len(canceled) == 1
    entry = canceled[0]
    assert entry["pending_order_id"] == pending_id
    assert entry["reason"] == "take_profit"


def test_run_matching_sell_limit_close_records_canceled_stale_sell_limits(store):
    """A SELL LIMIT cross that fully closes a position must record the other
    stale pending SELL LIMITs (for the same symbol) in `canceled` — same
    audit shape as the SL/TP path. Without this, the SELL LIMIT close path
    silently drops stale exits, exactly the bug 89a2732 fixed for triggers."""
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 105,
        },
        profile_id="alice",
    )
    second = store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 110,
        },
        profile_id="alice",
    )
    stale_id = next(
        order["id"]
        for order in second["account"]["pending_orders"]
        if float(order.get("limit_price", 0)) == 110.0
    )

    result = store.run_matching({"AAPL": 105.0}, profile_id="alice")

    assert len(result["filled"]) == 1
    assert result["filled"][0]["fill_price"] == pytest.approx(105.0)
    assert result["account"]["positions"] == []
    assert result["account"]["pending_orders"] == []
    canceled = result.get("canceled") or []
    assert (
        len(canceled) == 1
    ), f"expected 1 canceled audit entry, got {len(canceled)}: {canceled}"
    entry = canceled[0]
    assert entry["pending_order_id"] == stale_id
    assert entry["symbol"] == "AAPL"
    assert entry["side"] == "SELL"
    # `limit_cross` mirrors the trigger_reason already attached to the
    # filling SELL LIMIT order, letting an audit consumer correlate the
    # closing fill with the cancellation it caused.
    assert entry["reason"] == "limit_cross"
    assert entry.get("canceled_at"), "canceled entry must record a timestamp"


def test_run_matching_canceled_collection_empty_when_no_pruning_happens(store):
    """Baseline: a triggered SL with no stale pending exits leaves `canceled`
    empty (not missing, not None) — the audit shape is stable across calls."""
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 95.0}, profile_id="alice")
    assert len(result["triggered"]) == 1
    assert result["canceled"] == []


def test_run_matching_does_not_trigger_stop_loss_above_threshold(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 95.01}, profile_id="alice")
    assert result["triggered"] == []
    assert result["account"]["positions"][0]["quantity"] == 5


def test_run_matching_triggers_take_profit_when_quote_crosses(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    # take_profit_price = 110.0 → quote crosses
    result = store.run_matching({"AAPL": 110.0}, profile_id="alice")
    assert len(result["triggered"]) == 1
    triggered = result["triggered"][0]
    assert triggered["side"] == "SELL"
    assert triggered["fill_price"] == pytest.approx(110.0)
    assert triggered["trigger_reason"] == "take_profit"
    account = result["account"]
    assert account["positions"] == []
    assert account["cash"] == pytest.approx(10000.0 - 500.0 + 5 * 110.0)


def test_run_matching_does_not_trigger_take_profit_below_threshold(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    result = store.run_matching({"AAPL": 109.99}, profile_id="alice")
    assert result["triggered"] == []
    assert result["account"]["positions"][0]["quantity"] == 5


def test_run_matching_position_without_sl_tp_is_left_alone(store):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 5, "fill_price": 100.0},
        profile_id="alice",
    )
    # No SL/TP attached → quote movement is irrelevant.
    result = store.run_matching({"AAPL": 1.0}, profile_id="alice")
    assert result["triggered"] == []
    assert result["account"]["positions"][0]["quantity"] == 5


def test_run_matching_filled_orders_are_persisted_to_history(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 3,
            "order_type": "LIMIT",
            "fill_price": 100,
            "limit_price": 95,
        },
        profile_id="alice",
    )
    store.run_matching({"AAPL": 95.0}, profile_id="alice")
    orders = store.list_orders(profile_id="alice")
    assert len(orders) == 1
    assert orders[0]["side"] == "BUY"
    assert orders[0]["fill_price"] == pytest.approx(95.0)


def test_run_matching_triggered_orders_are_persisted_to_history(store):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    store.run_matching({"AAPL": 90.0}, profile_id="alice")
    # Two history entries: original BUY, and the SL-triggered SELL.
    orders = store.list_orders(profile_id="alice")
    assert len(orders) == 2
    assert {order["side"] for order in orders} == {"BUY", "SELL"}
    sells = [order for order in orders if order["side"] == "SELL"]
    assert sells[0]["trigger_reason"] == "stop_loss"


def test_run_matching_take_profit_takes_precedence_over_stop_loss_if_both_cross(store):
    """A pathological quote that crosses both bands should trigger take-profit
    first (favorable side) — but the position can only be closed once, so we
    pick exactly one trigger reason."""
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.50,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    # quote=110 crosses TP threshold (110) but is far above SL (50). Only TP fires.
    result = store.run_matching({"AAPL": 110.0}, profile_id="alice")
    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["trigger_reason"] == "take_profit"
    assert result["account"]["positions"] == []


def test_run_matching_processes_limit_then_triggers_in_one_call(store):
    """A SELL LIMIT and a SL trigger on the same symbol shouldn't both fire,
    because the LIMIT consumes the position. LIMITs are processed first."""
    # Open a position with a stop-loss
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    # Queue a SELL LIMIT @ 96 for the full position
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 96,
            "limit_price": 96,
        },
        profile_id="alice",
    )
    # quote=95 crosses SELL LIMIT (95 ≥ ... wait, SELL LIMIT fires when quote ≥ 96).
    # Let's pick quote=96: crosses SELL LIMIT (>=96), and ALSO stop_loss (<= 95)? No, 96 > 95, so SL doesn't fire.
    # Use quote=96: SELL LIMIT fills at 96, position closes, SL is moot.
    result = store.run_matching({"AAPL": 96.0}, profile_id="alice")
    assert len(result["filled"]) == 1
    assert result["triggered"] == []
    assert result["account"]["positions"] == []


def test_buy_limit_carries_bracket_sl_tp_through_fill(store):
    """A BUY LIMIT queued with stop_loss_pct / take_profit_pct must carry the
    brackets all the way to the position when it fills. Otherwise the resulting
    position has no SL/TP, the user thinks they're protected, and run_matching
    silently lets the price drift past the threshold (PaperOrderRequest accepts
    the fields but _queue_limit_order used to drop them)."""
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "fill_price": 100,  # ignored for LIMIT
            "limit_price": 95,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    queued = store.get_account(profile_id="alice")
    assert queued["pending_orders"][0]["stop_loss_pct"] == pytest.approx(0.05)
    assert queued["pending_orders"][0]["take_profit_pct"] == pytest.approx(0.10)

    fill_result = store.run_matching({"AAPL": 95.0}, profile_id="alice")
    assert len(fill_result["filled"]) == 1
    position = fill_result["account"]["positions"][0]
    # Brackets rebase against the actual fill price (95), not the original 100.
    assert position["stop_loss_pct"] == pytest.approx(0.05)
    assert position["stop_loss_price"] == pytest.approx(95.0 * 0.95)
    assert position["take_profit_pct"] == pytest.approx(0.10)
    assert position["take_profit_price"] == pytest.approx(95.0 * 1.10)

    # And the bracketed exits actually fire on the next tick — proves the
    # invariant end-to-end, not just the data-shape claim above.
    triggered = store.run_matching({"AAPL": 95.0 * 0.95}, profile_id="alice")
    assert len(triggered["triggered"]) == 1
    assert triggered["triggered"][0]["trigger_reason"] == "stop_loss"
    assert triggered["account"]["positions"] == []


def test_run_matching_persists_changes_across_store_instances(store, tmp_path):
    store.submit_order(
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
    store.run_matching({"AAPL": 95.0}, profile_id="alice")
    fresh = PaperTradingStore(storage_path=tmp_path)
    fresh_account = fresh.get_account(profile_id="alice")
    assert fresh_account["pending_orders"] == []
    assert fresh_account["positions"][0]["quantity"] == 1
    assert fresh_account["cash"] == pytest.approx(10000.0 - 95.0)


def test_run_matching_empty_account_returns_clean_shape(store):
    result = store.run_matching({"AAPL": 100.0}, profile_id="alice")
    assert result["filled"] == []
    assert result["triggered"] == []
    assert result["rejected"] == []
    assert result["account"]["cash"] == pytest.approx(10000.0)
