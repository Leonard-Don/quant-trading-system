import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import trading
from backend.app.core.error_handler import register_exception_handlers


@pytest.fixture
def trading_client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(trading.router, prefix="/trade")
    return TestClient(app)


def test_execute_trade_prefers_realtime_quote_cache(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        trading.realtime_manager,
        "get_quote_dict",
        lambda symbol, use_cache=True: {"symbol": symbol, "price": 321.45},
    )
    monkeypatch.setattr(
        trading.data_manager,
        "get_latest_price",
        lambda symbol: {"price": 111.11},
    )

    def fake_execute_trade(symbol, action, quantity, price):
        captured["trade_call"] = {
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
        }
        return {"symbol": symbol, "action": action, "quantity": quantity, "price": price}

    async def fake_broadcast(payload):
        captured["broadcast_payload"] = payload

    monkeypatch.setattr(trading.trade_manager, "execute_trade", fake_execute_trade)
    monkeypatch.setattr(trading.trade_ws_manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(
        trading,
        "build_trade_stream_payload",
        lambda: {"portfolio": {"cash": 100000}, "history": []},
    )

    request = trading.TradeRequest(symbol="AAPL", action="BUY", quantity=10, price=None)
    result = asyncio.run(trading.execute_trade(request))

    assert captured["trade_call"]["price"] == 321.45
    assert result["success"] is True
    assert result["data"]["price"] == 321.45
    assert captured["broadcast_payload"]["type"] == "trade_executed"


def test_execute_trade_missing_price_keeps_400_response(monkeypatch, trading_client):
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


def test_trade_history_runtime_failure_uses_app_exception(monkeypatch, trading_client):
    def raise_runtime_error(limit):
        raise RuntimeError(f"history unavailable for limit={limit}")

    monkeypatch.setattr(trading.trade_manager, "get_history", raise_runtime_error)

    response = trading_client.get("/trade/history?limit=3")

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "TRADE_HISTORY_FAILED"
    assert payload["error"]["message"] == "history unavailable for limit=3"
