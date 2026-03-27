"""
实时行情 REST / WS 契约测试
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.websocket.connection_manager import manager
from backend.main import app
from src.data.realtime_manager import realtime_manager


FAKE_QUOTE = {
    "symbol": "AAPL",
    "price": 189.25,
    "change": 1.5,
    "change_percent": 0.8,
    "volume": 123456,
    "high": 190.1,
    "low": 187.9,
    "open": 188.0,
    "previous_close": 187.75,
    "bid": 189.2,
    "ask": 189.3,
    "timestamp": datetime.now().isoformat(),
    "source": "test",
}


@pytest.fixture(autouse=True)
def reset_ws_manager():
    manager.active_connections.clear()
    manager.subscriptions.clear()
    manager.loop = None
    yield
    manager.active_connections.clear()
    manager.subscriptions.clear()
    manager.loop = None


@pytest.fixture
def client():
    return TestClient(app)


def test_realtime_quote_endpoint_returns_unified_shape(client):
    with patch.object(realtime_manager, "get_quote_dict", return_value=FAKE_QUOTE) as get_quote_dict:
        response = client.get("/realtime/quote/AAPL")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["symbol"] == "AAPL"
    assert payload["data"]["previous_close"] == FAKE_QUOTE["previous_close"]
    assert payload["data"]["source"] == "test"
    get_quote_dict.assert_called_once_with("AAPL", use_cache=True)


def test_realtime_quotes_endpoint_returns_mapping(client):
    quotes = {"AAPL": FAKE_QUOTE, "MSFT": {**FAKE_QUOTE, "symbol": "MSFT"}}
    with patch.object(realtime_manager, "get_quotes_dict", return_value=quotes) as get_quotes_dict:
        response = client.get("/realtime/quotes?symbols=AAPL,MSFT")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert sorted(payload["data"].keys()) == ["AAPL", "MSFT"]
    get_quotes_dict.assert_called_once_with(["AAPL", "MSFT"], use_cache=True)


def test_realtime_summary_endpoint_returns_cache_and_websocket_stats(client):
    with patch.object(realtime_manager, "get_market_summary", return_value={
        "subscribed_symbols": 2,
        "cache": {
            "bundle_cache_hits": 5,
            "bundle_cache_writes": 2,
        },
        "quality": {
            "active_quote_count": 2,
            "field_coverage": [{"field": "price", "coverage_ratio": 1.0}],
            "most_incomplete_symbols": [{"symbol": "MSFT", "missing_count": 4}],
        },
    }) as get_market_summary:
        response = client.get("/realtime/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["subscribed_symbols"] == 2
    assert payload["data"]["cache"]["bundle_cache_hits"] == 5
    assert payload["data"]["quality"]["active_quote_count"] == 2
    assert "websocket" in payload["data"]
    assert "connections" in payload["data"]["websocket"]
    get_market_summary.assert_called_once_with()


def test_realtime_compat_subscription_endpoints(client):
    subscribe_response = client.post("/realtime/subscribe", json={"symbols": ["aapl", "msft"]})
    unsubscribe_response = client.post("/realtime/unsubscribe", json={"symbol": "aapl"})

    assert subscribe_response.status_code == 200
    assert unsubscribe_response.status_code == 200

    subscribe_payload = subscribe_response.json()
    unsubscribe_payload = unsubscribe_response.json()
    assert subscribe_payload["deprecated"] is True
    assert subscribe_payload["symbols"] == ["AAPL", "MSFT"]
    assert unsubscribe_payload["symbols"] == ["AAPL"]


def test_websocket_duplicate_subscribe_only_fetches_initial_snapshot_once(client):
    snapshot_calls = []

    def fake_get_quotes(symbols, use_cache=True):
        snapshot_calls.append((tuple(symbols), use_cache))
        return {"AAPL": FAKE_QUOTE}

    with patch.object(realtime_manager, "get_quotes_dict", side_effect=fake_get_quotes), \
         patch.object(realtime_manager, "subscribe_symbol", return_value=True), \
         patch.object(realtime_manager, "unsubscribe_symbol", return_value=True):
        with client.websocket_connect("/ws/quotes") as websocket:
            websocket.send_json({"action": "subscribe", "symbol": "AAPL"})
            ack = websocket.receive_json()
            snapshot = websocket.receive_json()

            websocket.send_json({"action": "subscribe", "symbol": "AAPL"})
            duplicate_ack = websocket.receive_json()

            assert ack["type"] == "subscription"
            assert ack["action"] == "subscribed"
            assert ack["duplicate"] is False

            assert snapshot["type"] == "snapshot"
            assert snapshot["origin"] == "subscribe"
            assert snapshot["symbols"] == ["AAPL"]
            assert snapshot["data"]["AAPL"]["previous_close"] == FAKE_QUOTE["previous_close"]

            assert duplicate_ack["type"] == "subscription"
            assert duplicate_ack["action"] == "subscribed"
            assert duplicate_ack["duplicate"] is True

    assert snapshot_calls == [(("AAPL",), True)]


def test_websocket_manual_snapshot_reuses_cached_quote_contract(client):
    snapshot_calls = []

    def fake_get_quotes(symbols, use_cache=True):
        snapshot_calls.append((tuple(symbols), use_cache))
        return {"AAPL": FAKE_QUOTE}

    with patch.object(realtime_manager, "get_quotes_dict", side_effect=fake_get_quotes), \
         patch.object(realtime_manager, "subscribe_symbol", return_value=True), \
         patch.object(realtime_manager, "unsubscribe_symbol", return_value=True):
        with client.websocket_connect("/ws/quotes") as websocket:
            websocket.send_json({"action": "subscribe", "symbol": "AAPL"})
            websocket.receive_json()  # subscription ack
            websocket.receive_json()  # initial snapshot

            websocket.send_json({"action": "snapshot", "symbol": "AAPL"})
            snapshot = websocket.receive_json()

            assert snapshot["type"] == "snapshot"
            assert snapshot["origin"] == "manual_refresh"
            assert snapshot["symbols"] == ["AAPL"]
            assert snapshot["data"]["AAPL"]["symbol"] == "AAPL"

    assert snapshot_calls == [(("AAPL",), True), (("AAPL",), True)]
