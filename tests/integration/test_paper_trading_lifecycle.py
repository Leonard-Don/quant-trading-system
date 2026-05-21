"""Integration-style coverage of the paper-trading order lifecycle.

The unit suite exercises each layer in isolation. This file walks the
lifecycle end-to-end across the FastAPI surface, the service-level
matching engine (which has no HTTP endpoint), and the on-disk JSON
ledger — verifying that the research-journal-compatible audit links
(``opening_order_id``, ``pending_order_id``, ``entry_order_id``,
``canceled_pending_order_ids``) survive the round trip and remain
reconstructable from persisted history alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.services.paper_trading import PaperTradingStore

PROFILE = "lifecycle-tester"
HEADERS = {"X-Research-Profile": PROFILE}


@pytest.fixture
def integration_setup(tmp_path: Path, monkeypatch):
    """Wire the FastAPI surface to a temp-disk store, and hand the same
    instance back so the test can also drive ``run_matching`` (the only
    public lifecycle hook with no HTTP endpoint)."""
    isolated_store = PaperTradingStore(storage_path=tmp_path)
    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.paper_trading.paper_trading_store",
        isolated_store,
    )
    from backend.main import app

    client = TestClient(app)
    return client, isolated_store, tmp_path


def _ok(response) -> Any:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True
    return body["data"]


def test_rejected_market_sell_without_position_has_no_lifecycle_side_effects(
    integration_setup,
):
    """A rejected close must stay purely rejected: no fill, position, pending
    mutation, or account file should appear from the failed order."""
    client, _store, storage_root = integration_setup
    profile_file = storage_root / f"{PROFILE}.json"
    assert not profile_file.exists()

    response = client.post(
        "/paper/orders",
        json={"symbol": "AAPL", "side": "SELL", "quantity": 1, "fill_price": 100.0},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "insufficient position" in response.text.lower()
    assert not profile_file.exists()

    account = _ok(client.get("/paper/account", headers=HEADERS))
    assert account["cash"] == 10000.0
    assert account["positions"] == []
    assert account["pending_orders"] == []
    assert account["orders_count"] == 0

    orders_payload = _ok(client.get("/paper/orders", headers=HEADERS))
    assert orders_payload["orders"] == []

    reload_store = PaperTradingStore(storage_path=storage_root)
    assert reload_store.list_orders(profile_id=PROFILE) == []
    reload_account = reload_store.get_account(profile_id=PROFILE)
    assert reload_account["cash"] == 10000.0
    assert reload_account["positions"] == []
    assert reload_account["pending_orders"] == []


def test_limit_buy_then_limit_sell_full_lifecycle_through_http_and_matching(
    integration_setup,
):
    """End-to-end: reset profile via POST → queue LIMIT BUY via POST → drive
    fill via service ``run_matching`` → queue LIMIT SELL via POST → drive
    fill → verify cash/position/orders through GET. Each transition must be
    observable through the HTTP API alone (no peeking at the store object)."""
    client, store, _storage = integration_setup

    reset = _ok(
        client.post(
            "/paper/reset", json={"initial_capital": 5000.0}, headers=HEADERS
        )
    )
    assert reset["cash"] == 5000.0
    assert reset["positions"] == []
    assert reset["pending_orders"] == []
    assert reset["profile_id"] == PROFILE

    submit_buy = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 5,
                "order_type": "LIMIT",
                "limit_price": 90.0,
                "fill_price": 100.0,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.10,
            },
            headers=HEADERS,
        )
    )
    buy_pending_id = submit_buy["order"]["id"]
    assert buy_pending_id.startswith("ord-pending-")
    assert submit_buy["order"]["order_type"] == "LIMIT"

    pre_fill = _ok(client.get("/paper/account", headers=HEADERS))
    assert pre_fill["cash"] == 5000.0
    assert pre_fill["positions"] == []
    assert len(pre_fill["pending_orders"]) == 1
    assert pre_fill["pending_orders"][0]["id"] == buy_pending_id

    fill_result = store.run_matching({"AAPL": 88.0}, profile_id=PROFILE)
    assert len(fill_result["filled"]) == 1
    buy_fill = fill_result["filled"][0]
    assert buy_fill["side"] == "BUY"
    assert buy_fill["pending_order_id"] == buy_pending_id
    assert buy_fill["trigger_reason"] == "limit_cross"
    assert buy_fill["fill_price"] == pytest.approx(90.0)
    buy_order_id = buy_fill["id"]
    assert buy_order_id.startswith("ord-")
    assert not buy_order_id.startswith("ord-pending-")

    post_fill = _ok(client.get("/paper/account", headers=HEADERS))
    assert post_fill["cash"] == pytest.approx(5000.0 - 5 * 90.0)
    assert post_fill["pending_orders"] == []
    assert len(post_fill["positions"]) == 1
    position = post_fill["positions"][0]
    assert position["symbol"] == "AAPL"
    assert position["quantity"] == 5
    assert position["avg_cost"] == pytest.approx(90.0)
    assert position["opening_order_id"] == buy_order_id
    assert position["stop_loss_price"] == pytest.approx(90.0 * 0.95)
    assert position["take_profit_price"] == pytest.approx(90.0 * 1.10)

    submit_sell = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "SELL",
                "quantity": 5,
                "order_type": "LIMIT",
                "limit_price": 110.0,
                "fill_price": 100.0,
            },
            headers=HEADERS,
        )
    )
    sell_pending_id = submit_sell["order"]["id"]

    # LIMIT exits are evaluated before SL/TP triggers; this quote also clears
    # the take-profit threshold, so the pending limit should own the close.
    sell_result = store.run_matching({"AAPL": 110.0}, profile_id=PROFILE)
    assert len(sell_result["filled"]) == 1
    sell_fill = sell_result["filled"][0]
    assert sell_fill["side"] == "SELL"
    assert sell_fill["pending_order_id"] == sell_pending_id
    assert sell_fill["fill_price"] == pytest.approx(110.0)
    assert sell_fill["entry_order_id"] == buy_order_id

    final_account = _ok(client.get("/paper/account", headers=HEADERS))
    assert final_account["positions"] == []
    assert final_account["pending_orders"] == []
    assert final_account["cash"] == pytest.approx(5000.0 - 5 * 90.0 + 5 * 110.0)
    # orders_count counts persisted fills. Pending LIMITs only live in
    # pending_orders until a fill produces a separate `ord-...` id; the
    # pending_order_id link on that fill is what ties the two together.
    assert final_account["orders_count"] == 2

    orders_payload = _ok(client.get("/paper/orders", headers=HEADERS))
    orders = orders_payload["orders"]
    by_id = {order["id"]: order for order in orders}
    assert {buy_order_id, sell_fill["id"]} <= set(by_id)
    assert by_id[buy_order_id]["pending_order_id"] == buy_pending_id
    assert by_id[sell_fill["id"]]["pending_order_id"] == sell_pending_id
    assert by_id[sell_fill["id"]]["entry_order_id"] == buy_order_id


def test_close_cancel_audit_chain_round_trips_through_persistence(
    integration_setup,
):
    """A LIMIT cross that closes a position must prune the un-crossed
    pending SELL exits. The cascade is the journal-friendly invariant:
    the closing fill records ``canceled_pending_order_ids`` and each
    canceled audit entry records ``closing_order_id`` — both directions
    must survive the JSON round trip and a fresh store reload.
    """
    client, store, storage_root = integration_setup

    _ok(
        client.post(
            "/paper/reset", json={"initial_capital": 5000.0}, headers=HEADERS
        )
    )
    buy = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 10,
                "fill_price": 100.0,
            },
            headers=HEADERS,
        )
    )
    buy_order_id = buy["order"]["id"]

    sell_low = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "SELL",
                "quantity": 10,
                "order_type": "LIMIT",
                "limit_price": 105.0,
                "fill_price": 100.0,
            },
            headers=HEADERS,
        )
    )
    sell_high = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "SELL",
                "quantity": 10,
                "order_type": "LIMIT",
                "limit_price": 115.0,
                "fill_price": 100.0,
            },
            headers=HEADERS,
        )
    )
    low_pending_id = sell_low["order"]["id"]
    high_pending_id = sell_high["order"]["id"]

    result = store.run_matching({"AAPL": 106.0}, profile_id=PROFILE)
    assert len(result["filled"]) == 1
    closing_fill = result["filled"][0]
    assert closing_fill["pending_order_id"] == low_pending_id
    assert closing_fill["entry_order_id"] == buy_order_id
    # Forward link: closing fill -> what it pruned (walkable from history alone).
    assert closing_fill["canceled_pending_order_ids"] == [high_pending_id]

    # Reverse link: each cancel entry points back at the closing fill.
    canceled = result["canceled"]
    assert len(canceled) == 1
    assert canceled[0]["pending_order_id"] == high_pending_id
    assert canceled[0]["reason"] == "limit_cross"
    assert canceled[0]["closing_order_id"] == closing_fill["id"]

    final_account = _ok(client.get("/paper/account", headers=HEADERS))
    assert final_account["positions"] == []
    assert final_account["pending_orders"] == []

    profile_file = storage_root / f"{PROFILE}.json"
    assert profile_file.exists()
    with open(profile_file, encoding="utf-8") as handle:
        persisted = json.load(handle)

    persisted_fills = [
        order for order in persisted["orders"] if order["id"] == closing_fill["id"]
    ]
    assert len(persisted_fills) == 1
    assert persisted_fills[0]["canceled_pending_order_ids"] == [high_pending_id]
    assert persisted_fills[0]["entry_order_id"] == buy_order_id

    reload_store = PaperTradingStore(storage_path=storage_root)
    reload_account = reload_store.get_account(profile_id=PROFILE)
    assert reload_account["cash"] == final_account["cash"]
    assert reload_account["positions"] == []
    assert reload_account["pending_orders"] == []

    reload_orders = reload_store.list_orders(profile_id=PROFILE)
    reload_by_id = {order["id"]: order for order in reload_orders}
    assert closing_fill["id"] in reload_by_id
    assert reload_by_id[closing_fill["id"]]["canceled_pending_order_ids"] == [
        high_pending_id
    ]
    assert reload_by_id[closing_fill["id"]]["entry_order_id"] == buy_order_id


def test_cancel_pending_via_http_clears_lifecycle_without_fills(
    integration_setup,
):
    """User-initiated cancel via DELETE removes the pending order before
    a quote ever crosses; the lifecycle ends with no fills and no
    leftover pending state, and the account file persists the empty
    pending_orders list cleanly across a reload."""
    client, store, storage_root = integration_setup

    _ok(
        client.post(
            "/paper/reset", json={"initial_capital": 5000.0}, headers=HEADERS
        )
    )
    submit = _ok(
        client.post(
            "/paper/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 3,
                "order_type": "LIMIT",
                "limit_price": 80.0,
                "fill_price": 100.0,
            },
            headers=HEADERS,
        )
    )
    pending_id = submit["order"]["id"]

    cancel_response = client.delete(f"/paper/orders/{pending_id}", headers=HEADERS)
    cancel_data = _ok(cancel_response)
    assert cancel_data["pending_orders"] == []
    assert cancel_data["cash"] == 5000.0

    # A subsequent matching call with a quote that *would* have crossed
    # the original limit price must produce nothing — the pending order
    # is gone and cash stays untouched.
    no_match = store.run_matching({"AAPL": 70.0}, profile_id=PROFILE)
    assert no_match["filled"] == []
    assert no_match["triggered"] == []

    after = _ok(client.get("/paper/account", headers=HEADERS))
    assert after["cash"] == 5000.0
    assert after["positions"] == []
    assert after["pending_orders"] == []

    reload_store = PaperTradingStore(storage_path=storage_root)
    reload_account = reload_store.get_account(profile_id=PROFILE)
    assert reload_account["pending_orders"] == []
    assert reload_account["cash"] == 5000.0
