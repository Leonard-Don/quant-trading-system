import asyncio

import pytest

from backend.app.websocket.connection_manager import ConnectionManager
from backend.app.websocket.trade_connection_manager import TradeConnectionManager


class DummyWebSocket:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    async def send_json(self, payload):
        if self.error is not None:
            raise self.error
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_connection_manager_send_personal_message_disconnects_failed_socket(monkeypatch):
    manager = ConnectionManager()
    websocket = DummyWebSocket(
        RuntimeError('WebSocket is not connected. Need to call "accept" first.')
    )
    manager.subscriptions[websocket] = {"AAPL"}
    manager.active_connections["AAPL"] = {websocket}
    unsubscribed_symbols = []

    monkeypatch.setattr(
        "backend.app.websocket.connection_manager.realtime_manager.unsubscribe_symbol",
        lambda symbol, callback: unsubscribed_symbols.append(symbol),
    )

    delivered = await manager.send_personal_message(websocket, {"type": "snapshot"})

    assert delivered is False
    assert websocket not in manager.subscriptions
    assert "AAPL" not in manager.active_connections
    assert unsubscribed_symbols == ["AAPL"]


@pytest.mark.asyncio
async def test_connection_manager_send_personal_message_returns_true_for_active_socket():
    manager = ConnectionManager()
    websocket = DummyWebSocket()
    manager.subscriptions[websocket] = set()

    delivered = await manager.send_personal_message(websocket, {"type": "pong"})

    assert delivered is True
    assert websocket.messages == [{"type": "pong"}]


@pytest.mark.asyncio
async def test_connection_manager_coalesces_pending_quotes_for_same_symbol():
    manager = ConnectionManager()
    websocket = DummyWebSocket()
    manager.subscriptions[websocket] = {"AAPL"}
    manager.active_connections["AAPL"] = {websocket}
    manager._send_queues[websocket] = asyncio.Queue(maxsize=1)

    await manager.broadcast_quote("AAPL", {"price": 101})
    await manager.broadcast_quote("AAPL", {"price": 102})

    queued_messages = list(manager._send_queues[websocket]._queue)
    assert len(queued_messages) == 1
    assert queued_messages[0][0]["type"] == "quote"
    assert queued_messages[0][0]["data"]["price"] == 102


@pytest.mark.asyncio
async def test_connection_manager_keeps_control_messages_ahead_of_coalesced_quotes():
    manager = ConnectionManager()
    websocket = DummyWebSocket()
    manager.subscriptions[websocket] = {"AAPL"}
    manager.active_connections["AAPL"] = {websocket}
    manager._send_queues[websocket] = asyncio.Queue(maxsize=4)

    assert manager._enqueue_message(websocket, {"type": "snapshot", "symbols": ["AAPL"]}) is True

    await manager.broadcast_quote("AAPL", {"price": 101})
    await manager.broadcast_quote("AAPL", {"price": 105})

    queued_messages = list(manager._send_queues[websocket]._queue)
    assert len(queued_messages) == 2
    assert queued_messages[0][0]["type"] == "snapshot"
    assert queued_messages[1][0]["type"] == "quote"
    assert queued_messages[1][0]["data"]["price"] == 105


@pytest.mark.asyncio
async def test_trade_connection_manager_send_personal_message_disconnects_failed_socket():
    manager = TradeConnectionManager()
    websocket = DummyWebSocket(
        RuntimeError('WebSocket is not connected. Need to call "accept" first.')
    )
    manager.active_connections.add(websocket)

    delivered = await manager.send_personal_message(websocket, {"type": "trade_snapshot"})

    assert delivered is False
    assert websocket not in manager.active_connections


@pytest.mark.asyncio
async def test_trade_connection_manager_send_personal_message_returns_true_for_active_socket():
    manager = TradeConnectionManager()
    websocket = DummyWebSocket()
    manager.active_connections.add(websocket)

    delivered = await manager.send_personal_message(websocket, {"type": "connected"})

    assert delivered is True
    assert websocket.messages == [{"type": "connected"}]
