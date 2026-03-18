from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from src.data.providers.yahoo_provider import YahooFinanceProvider


def test_get_multiple_quotes_includes_extended_intraday_fields():
    provider = YahooFinanceProvider()

    fake_aapl = SimpleNamespace(
        info={
            "regularMarketPrice": 253.94,
            "regularMarketChange": 1.12,
            "regularMarketChangePercent": 0.44,
            "regularMarketVolume": 28765432,
            "dayHigh": 255.13,
            "dayLow": 252.18,
            "regularMarketOpen": 253.08,
            "previousClose": 252.82,
            "bid": 253.86,
            "ask": 265.62,
        },
        fast_info={
            "lastPrice": 253.91,
            "lastVolume": 28000000,
            "dayHigh": 255.0,
            "dayLow": 252.0,
            "open": 253.0,
            "previousClose": 252.8,
        },
    )
    fake_spx = SimpleNamespace(
        info={
            "regularMarketPrice": None,
            "regularMarketChange": None,
            "regularMarketChangePercent": None,
            "regularMarketVolume": None,
            "dayHigh": None,
            "dayLow": None,
            "regularMarketOpen": None,
            "previousClose": None,
            "bid": 6683.37,
            "ask": 6757.55,
        },
        fast_info={
            "lastPrice": 6716.09,
            "regularMarketChange": 16.71,
            "regularMarketChangePercent": 0.25,
            "lastVolume": 2901000000,
            "dayHigh": 6754.30,
            "dayLow": 6710.80,
            "open": 6722.35,
            "previousClose": 6699.38,
        },
    )

    with patch(
        "src.data.providers.yahoo_provider.yf.Tickers",
        return_value=SimpleNamespace(tickers={"AAPL": fake_aapl, "^GSPC": fake_spx}),
    ):
        quotes = provider.get_multiple_quotes(["AAPL", "^GSPC"])

    assert quotes["AAPL"] == {
        "symbol": "AAPL",
        "price": 253.94,
        "change": 1.12,
        "change_percent": 0.44,
        "volume": 28765432,
        "high": 255.13,
        "low": 252.18,
        "open": 253.08,
        "previous_close": 252.82,
        "bid": 253.86,
        "ask": 265.62,
        "timestamp": quotes["AAPL"]["timestamp"],
        "source": "yahoo",
    }
    assert isinstance(quotes["AAPL"]["timestamp"], datetime)

    assert quotes["^GSPC"] == {
        "symbol": "^GSPC",
        "price": 6716.09,
        "change": 16.71,
        "change_percent": 0.25,
        "volume": 2901000000,
        "high": 6754.30,
        "low": 6710.80,
        "open": 6722.35,
        "previous_close": 6699.38,
        "bid": 6683.37,
        "ask": 6757.55,
        "timestamp": quotes["^GSPC"]["timestamp"],
        "source": "yahoo",
    }
    assert isinstance(quotes["^GSPC"]["timestamp"], datetime)
