from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import events
from backend.app.core.error_handler import register_exception_handlers


def build_events_client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(events.router, prefix="/events")
    return TestClient(app)


def test_events_summary_ticker_runtime_failure_uses_app_exception(monkeypatch):
    def raise_runtime_error(symbol):
        raise RuntimeError(f"ticker unavailable for {symbol}")

    monkeypatch.setattr(events.yf, "Ticker", raise_runtime_error)

    response = build_events_client().post("/events/summary", json={"symbol": "AAPL"})

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "EVENTS_SUMMARY_FAILED"
    assert payload["error"]["message"] == "ticker unavailable for AAPL"


def test_events_summary_keeps_partial_response_for_calendar_fetch_error(monkeypatch):
    class EmptyDividends:
        empty = True

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def calendar(self):
            raise OSError("calendar transport failed")

        @property
        def dividends(self):
            return EmptyDividends()

        @property
        def news(self):
            return [
                {
                    "title": "AAPL headline",
                    "publisher": "Example",
                    "link": "https://example.test/aapl",
                    "providerPublishTime": 1710000000,
                    "type": "STORY",
                }
            ]

    monkeypatch.setattr(events.yf, "Ticker", FakeTicker)

    response = build_events_client().post("/events/summary", json={"symbol": "AAPL"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["earnings"] == {}
    assert payload["dividends"] == {}
    assert payload["news"] == [
        {
            "title": "AAPL headline",
            "publisher": "Example",
            "link": "https://example.test/aapl",
            "providerPublishTime": 1710000000,
            "type": "STORY",
        }
    ]
