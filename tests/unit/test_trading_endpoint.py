import asyncio

from backend.app.api.v1.endpoints import trading


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
