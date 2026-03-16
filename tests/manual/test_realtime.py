import os
import sys
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient


# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.main import app  # noqa: E402
from src.data.realtime_manager import realtime_manager  # noqa: E402


client = TestClient(app)

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


def test_get_quote_success():
    """Test getting unified quote data for a valid symbol."""
    with patch.object(realtime_manager, "get_quote_dict", return_value=FAKE_QUOTE):
        response = client.get("/realtime/quote/AAPL")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    quote = data["data"]
    assert quote["symbol"] == "AAPL"
    assert quote["price"] > 0
    assert quote["previous_close"] == FAKE_QUOTE["previous_close"]
    print(f"\n✅ Successfully fetched quote for AAPL: {quote['price']}")


def test_subscribe_success():
    """Test deprecated compatibility subscription endpoint."""
    response = client.post("/realtime/subscribe", json={"symbol": "AAPL"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deprecated"] is True
    assert payload["symbols"] == ["AAPL"]
    assert payload["websocket"] == "/ws/quotes"


if __name__ == "__main__":
    try:
        test_get_quote_success()
        test_subscribe_success()
        print("\n🎉 Realtime API tests passed!")
    except Exception as e:
        print(f"\n❌ API tests failed: {e}")
        raise
