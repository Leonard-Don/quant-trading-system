"""
实时行情 REST / WS 契约测试
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.websocket.connection_manager import manager
from backend.app.services.realtime_journal import realtime_journal_store
from backend.main import app
from src.data.realtime_manager import realtime_manager
from src.utils.cache import cache_manager


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
    manager._send_queues.clear()
    manager._send_tasks.clear()
    manager.loop = None
    realtime_manager.quote_history.clear()
    realtime_manager._quotes_bundle_cache.clear()
    cache_manager.clear()
    yield
    manager.active_connections.clear()
    manager.subscriptions.clear()
    manager._send_queues.clear()
    manager._send_tasks.clear()
    manager.loop = None
    realtime_manager.quote_history.clear()
    realtime_manager._quotes_bundle_cache.clear()
    cache_manager.clear()


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


def test_realtime_metadata_endpoint_returns_dynamic_symbol_payload(client):
    with patch.object(realtime_manager, "get_quote_dict", return_value={"symbol": "AAPL", "source": "test"}), \
         patch.object(realtime_manager.provider_factory, "get_fundamental_data", return_value={
             "company_name": "Apple Inc.",
             "source": "fundamental",
         }):
        response = client.get("/realtime/metadata?symbols=AAPL,BTC-USD")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["AAPL"]["en"] == "Apple Inc."
    assert payload["data"]["AAPL"]["type"] == "us"
    assert payload["data"]["BTC-USD"]["type"] == "crypto"


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


def test_realtime_journal_endpoint_accepts_profile_id_query_param(client):
    with patch.object(
        realtime_journal_store,
        "get_journal",
        return_value={"review_snapshots": [], "timeline_events": []},
    ) as get_journal:
        response = client.get("/realtime/journal?profile_id=query-profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    get_journal.assert_called_once_with(profile_id="query-profile")


def test_realtime_journal_endpoint_prefers_profile_header_over_query_param(client):
    with patch.object(
        realtime_journal_store,
        "get_journal",
        return_value={"review_snapshots": [], "timeline_events": []},
    ) as get_journal:
        response = client.get(
            "/realtime/journal?profile_id=query-profile",
            headers={"X-Realtime-Profile": "header-profile"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    get_journal.assert_called_once_with(profile_id="header-profile")


def test_realtime_alert_hit_endpoint_keeps_local_contract_without_quant_bus(client):
    with patch(
        "backend.app.api.v1.endpoints.realtime.realtime_alerts_store.record_alert_hit",
        return_value={
            "entry": {"id": "hit-1", "symbol": "AAPL", "message": "AAPL alert"},
            "alert_hit_history": [{"id": "hit-1", "symbol": "AAPL"}],
        },
    ) as record_alert_hit:
        response = client.post(
            "/realtime/alerts/hits?profile_id=realtime-profile",
            json={
                "entry": {"id": "hit-1", "symbol": "AAPL", "message": "AAPL alert"},
                "notify_channels": ["desktop"],
                "create_workbench_task": True,
                "persist_event_record": True,
                "severity": "warning",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["entry"]["symbol"] == "AAPL"
    assert payload["data"]["bus_event"] is None
    assert payload["data"]["cascade_results"] == []
    assert payload["data"]["orchestration_summary"] == {}
    record_alert_hit.assert_called_once_with(
        {"id": "hit-1", "symbol": "AAPL", "message": "AAPL alert"},
        profile_id="realtime-profile",
    )


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


def test_websocket_batch_subscription_ack_returns_symbols_and_results(client):
    quotes = {
        "AAPL": FAKE_QUOTE,
        "MSFT": {**FAKE_QUOTE, "symbol": "MSFT"},
    }

    with patch.object(realtime_manager, "get_quotes_dict", return_value=quotes), \
         patch.object(realtime_manager, "subscribe_symbol", return_value=True), \
         patch.object(realtime_manager, "unsubscribe_symbol", return_value=True):
        with client.websocket_connect("/ws/quotes") as websocket:
            websocket.send_json({"action": "subscribe", "symbols": ["AAPL", "MSFT"]})
            ack = websocket.receive_json()
            snapshot = websocket.receive_json()

            assert ack["type"] == "subscription"
            assert ack["action"] == "subscribed"
            assert ack["symbols"] == ["AAPL", "MSFT"]
            assert [item["symbol"] for item in ack["results"]] == ["AAPL", "MSFT"]
            assert all(item["added"] is True for item in ack["results"])
            datetime.fromisoformat(ack["timestamp"])

            assert snapshot["type"] == "snapshot"
            assert snapshot["symbols"] == ["AAPL", "MSFT"]


def test_websocket_ping_returns_iso_timestamp(client):
    with client.websocket_connect("/ws/quotes") as websocket:
        websocket.send_json({"action": "ping"})
        pong = websocket.receive_json()

        assert pong["type"] == "pong"
        datetime.fromisoformat(pong["timestamp"])
