from datetime import datetime

from src.data.realtime_manager import RealTimeDataManager


def test_build_quote_preserves_missing_numeric_fields():
    manager = RealTimeDataManager()
    try:
        quote = manager._build_quote(
            "TEST",
            {
                "symbol": "TEST",
                "price": None,
                "change": None,
                "change_percent": None,
                "volume": None,
                "timestamp": datetime.now().isoformat(),
            },
            default_source="test",
        )
    finally:
        manager.cleanup()

    assert quote is not None
    assert quote.price is None
    assert quote.change is None
    assert quote.change_percent is None
    assert quote.volume is None
    assert quote.source == "test"


def test_build_quote_derives_previous_close_and_percent_when_possible():
    manager = RealTimeDataManager()
    try:
        quote = manager._build_quote(
            "TEST",
            {
                "symbol": "TEST",
                "price": 105.0,
                "change": 5.0,
                "timestamp": datetime.now().isoformat(),
            },
            default_source="test",
        )
    finally:
        manager.cleanup()

    assert quote is not None
    assert quote.previous_close == 100.0
    assert round(quote.change_percent, 2) == 5.0
