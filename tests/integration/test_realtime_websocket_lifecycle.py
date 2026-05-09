"""Realtime websocket lifecycle integration tests.

Covers the end-to-end flow that previous tests only exercised in pieces:
connect → subscribe → realtime broadcast → unsubscribe → disconnect, including
two concurrent clients sharing a single underlying realtime_manager subscription.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.websocket.connection_manager import manager
from backend.main import app
from src.data.realtime_manager import RealTimeQuote, realtime_manager
from src.utils.cache import cache_manager


FAKE_INITIAL_QUOTE = {
    "symbol": "AAPL",
    "price": 200.0,
    "change": 2.0,
    "change_percent": 1.0,
    "volume": 100_000,
    "timestamp": datetime(2026, 5, 9, 15, 0, 0).isoformat(),
    "source": "lifecycle-test-initial",
    "previous_close": 198.0,
    "high": 201.0,
    "low": 199.0,
    "open": 199.5,
    "bid": 199.95,
    "ask": 200.05,
}


@pytest.fixture(autouse=True)
def reset_realtime_state():
    def _wipe():
        manager.active_connections.clear()
        manager.subscriptions.clear()
        manager._send_queues.clear()
        manager._send_tasks.clear()
        manager.loop = None
        realtime_manager.subscribed_symbols.clear()
        realtime_manager.subscribers.clear()
        realtime_manager.quote_history.clear()
        realtime_manager._quotes_bundle_cache.clear()
        cache_manager.clear()

    _wipe()
    yield
    _wipe()


@pytest.fixture
def client():
    return TestClient(app)


def _make_realtime_quote(symbol: str = "AAPL", price: float = 205.5) -> RealTimeQuote:
    return RealTimeQuote(
        symbol=symbol,
        price=price,
        change=1.25,
        change_percent=0.61,
        volume=234_567,
        timestamp=datetime(2026, 5, 9, 15, 30, 45),
        high=price + 0.5,
        low=price - 1.0,
        open=price - 0.5,
        previous_close=price - 1.25,
        bid=price - 0.05,
        ask=price + 0.05,
        source="lifecycle-broadcast",
    )


def _drain_subscription_handshake(websocket, expected_symbols):
    ack = websocket.receive_json()
    snapshot = websocket.receive_json()
    assert ack["type"] == "subscription"
    assert ack["action"] == "subscribed"
    assert ack["symbols"] == expected_symbols
    assert snapshot["type"] == "snapshot"
    assert snapshot["symbols"] == expected_symbols
    return ack, snapshot


def test_realtime_websocket_full_lifecycle_single_client(client):
    """connect → subscribe → broadcast → unsubscribe → disconnect on one socket."""
    with patch.object(realtime_manager, "get_quotes_dict", return_value={"AAPL": FAKE_INITIAL_QUOTE}):
        with client.websocket_connect("/ws/quotes") as websocket:
            websocket.send_json({"action": "subscribe", "symbol": "AAPL"})
            _drain_subscription_handshake(websocket, ["AAPL"])

            # Subscribe propagated all the way down to realtime_manager and the
            # WebSocket connection manager registered exactly one bridge callback.
            assert "AAPL" in manager.active_connections
            assert "AAPL" in realtime_manager.subscribers
            callbacks = realtime_manager.subscribers["AAPL"]
            assert manager._handle_realtime_update in callbacks
            assert len(callbacks) == 1

            # Drive a deterministic realtime update through the registered bridge,
            # exactly as RealTimeDataManager._update_quotes would have.
            manager._handle_realtime_update(_make_realtime_quote(symbol="AAPL", price=205.5))

            received = websocket.receive_json()
            assert received["type"] == "quote"
            assert received["symbol"] == "AAPL"
            assert received["data"]["symbol"] == "AAPL"
            assert received["data"]["price"] == 205.5
            assert received["data"]["source"] == "lifecycle-broadcast"
            datetime.fromisoformat(received["timestamp"])

            websocket.send_json({"action": "unsubscribe", "symbol": "AAPL"})
            unsub_ack = websocket.receive_json()
            assert unsub_ack["type"] == "subscription"
            assert unsub_ack["action"] == "unsubscribed"
            assert unsub_ack["symbols"] == ["AAPL"]
            assert unsub_ack["noop"] is False

            # Single subscriber gone — symbol fully released from both managers,
            # but the websocket itself is still tracked until disconnect.
            assert "AAPL" not in manager.active_connections
            assert "AAPL" not in realtime_manager.subscribers
            assert "AAPL" not in realtime_manager.subscribed_symbols

    # After context exit, the websocket route's finally-block ran disconnect cleanup.
    assert manager.subscriptions == {}
    assert manager.active_connections == {}
    assert manager._send_queues == {}
    assert manager._send_tasks == {}


def test_realtime_websocket_concurrent_clients_share_broadcast(client):
    """Two concurrent clients on the same symbol both receive the broadcast,
    realtime_manager only sees one underlying subscription, and the symbol is
    released when the LAST client disconnects."""
    with patch.object(realtime_manager, "get_quotes_dict", return_value={"AAPL": FAKE_INITIAL_QUOTE}):
        with client.websocket_connect("/ws/quotes") as ws_first:
            ws_first.send_json({"action": "subscribe", "symbol": "AAPL"})
            _drain_subscription_handshake(ws_first, ["AAPL"])

            with client.websocket_connect("/ws/quotes") as ws_second:
                ws_second.send_json({"action": "subscribe", "symbol": "AAPL"})
                _drain_subscription_handshake(ws_second, ["AAPL"])

                # Both client websockets are tracked, but realtime_manager only
                # registered ONE callback (fan-out happens in connection_manager).
                assert len(manager.active_connections["AAPL"]) == 2
                assert len(realtime_manager.subscribers["AAPL"]) == 1

                # A single deterministic update fans out to both clients.
                manager._handle_realtime_update(_make_realtime_quote(symbol="AAPL", price=210.75))

                msg_first = ws_first.receive_json()
                msg_second = ws_second.receive_json()
                for received in (msg_first, msg_second):
                    assert received["type"] == "quote"
                    assert received["symbol"] == "AAPL"
                    assert received["data"]["price"] == 210.75
                    assert received["data"]["source"] == "lifecycle-broadcast"

            # ws_second context exited → route handler's finally ran disconnect.
            # ws_first remains, so realtime_manager keeps the underlying subscription.
            assert "AAPL" in manager.active_connections
            assert len(manager.active_connections["AAPL"]) == 1
            assert "AAPL" in realtime_manager.subscribers
            assert "AAPL" in realtime_manager.subscribed_symbols

        # ws_first exited → last subscriber gone; realtime_manager releases the symbol.
        assert manager.active_connections == {}
        assert "AAPL" not in realtime_manager.subscribers
        assert "AAPL" not in realtime_manager.subscribed_symbols
