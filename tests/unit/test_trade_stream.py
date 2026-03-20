from backend.app.services import trade_stream


def test_resolve_trade_portfolio_prefers_realtime_quotes_and_falls_back(monkeypatch):
    monkeypatch.setattr(
        trade_stream.trade_manager,
        "positions",
        {"AAPL": object(), "MSFT": object()},
    )
    monkeypatch.setattr(
        trade_stream.realtime_manager,
        "get_quotes_dict",
        lambda symbols, use_cache=True: {
            "AAPL": {"price": 321.45},
            "MSFT": {"price": None},
        },
    )
    monkeypatch.setattr(
        trade_stream.data_manager,
        "get_latest_price",
        lambda symbol: {"price": 412.0} if symbol == "MSFT" else {"price": 111.0},
    )
    monkeypatch.setattr(
        trade_stream.trade_manager,
        "get_portfolio_status",
        lambda current_prices: {"current_prices": current_prices},
    )

    result = trade_stream.resolve_trade_portfolio()

    assert result["current_prices"] == {
        "AAPL": 321.45,
        "MSFT": 412.0,
    }
