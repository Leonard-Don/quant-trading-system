import logging
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
        "price": 253.91,
        "change": 1.12,
        "change_percent": 0.44,
        "volume": 28000000,
        "high": 255.0,
        "low": 252.0,
        "open": 253.0,
        "previous_close": 252.8,
        "bid": None,
        "ask": None,
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
        "bid": None,
        "ask": None,
        "timestamp": quotes["^GSPC"]["timestamp"],
        "source": "yahoo",
    }
    assert isinstance(quotes["^GSPC"]["timestamp"], datetime)


def test_get_latest_quote_prefers_fast_info_before_info():
    provider = YahooFinanceProvider()
    slow_info_accessed = {"value": False}

    class FakeTicker:
        fast_info = {
            "lastPrice": 188.2,
            "regularMarketChange": 1.1,
            "regularMarketChangePercent": 0.59,
            "lastVolume": 123456,
            "dayHigh": 189.0,
            "dayLow": 186.8,
            "open": 187.2,
            "previousClose": 187.1,
        }

        @property
        def info(self):
            slow_info_accessed["value"] = True
            return {"regularMarketPrice": 188.5}

    with patch.object(provider, "_get_ticker", return_value=FakeTicker()):
        quote = provider.get_latest_quote("AAPL")

    assert quote["price"] == 188.2
    assert quote["previous_close"] == 187.1
    assert slow_info_accessed["value"] is False


def test_get_latest_quote_skips_info_fallback_for_crypto_symbols():
    provider = YahooFinanceProvider()
    slow_info_accessed = {"value": False}

    class FakeTicker:
        fast_info = {
            "regularMarketChange": 12.5,
            "regularMarketChangePercent": 1.8,
        }

        @property
        def info(self):
            slow_info_accessed["value"] = True
            raise AssertionError("crypto quote path should not touch ticker.info")

    with patch.object(provider, "_get_ticker", return_value=FakeTicker()):
        quote = provider.get_latest_quote("BNB-USD")

    assert quote == {
        "symbol": "BNB-USD",
        "error": "Yahoo crypto fast quote unavailable",
        "source": "yahoo",
    }
    assert slow_info_accessed["value"] is False


def test_expected_crypto_yfinance_gap_logs_are_suppressed(caplog):
    provider = YahooFinanceProvider()
    yfinance_logger = logging.getLogger("yfinance.scrapers.history")

    with caplog.at_level(logging.ERROR):
        with provider._suppress_expected_yfinance_noise(["BNB-USD"]):
            yfinance_logger.error("$BNB-USD: possibly delisted; no price data found")
            yfinance_logger.error("$AAPL: possibly delisted; no price data found")

    messages = [record.getMessage() for record in caplog.records]
    assert "$BNB-USD: possibly delisted; no price data found" not in messages
    assert "$AAPL: possibly delisted; no price data found" in messages
