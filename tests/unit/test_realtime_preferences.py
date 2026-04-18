from backend.app.services.realtime_preferences import RealtimePreferencesStore


def test_realtime_preferences_store_normalizes_symbols_and_active_tab(tmp_path):
    store = RealtimePreferencesStore(storage_path=tmp_path)

    updated = store.update_preferences({
        "symbols": ["aapl", " AAPL ", "msft", "", None],
        "active_tab": "us",
        "symbol_categories": {"aapl": "us", " msft ": "other", "bad": "invalid"},
    })

    assert updated == {
        "symbols": ["AAPL", "MSFT"],
        "active_tab": "us",
        "symbol_categories": {"AAPL": "us", "MSFT": "other"},
        "watch_groups": [],
        "_warnings": ["symbol_categories['BAD']: skipped (invalid category 'invalid')"],
    }


def test_realtime_preferences_store_falls_back_to_default_tab_for_invalid_values(tmp_path):
    store = RealtimePreferencesStore(storage_path=tmp_path)

    updated = store.update_preferences({
        "symbols": ["nflx"],
        "active_tab": "not-a-tab",
    })

    assert updated["symbols"] == ["NFLX"]
    assert updated["active_tab"] == "index"
    assert updated["symbol_categories"] == {}


def test_realtime_preferences_store_isolated_by_profile_id(tmp_path):
    store = RealtimePreferencesStore(storage_path=tmp_path)

    store.update_preferences({
        "symbols": ["aapl"],
        "active_tab": "us",
        "symbol_categories": {"AAPL": "us"},
    }, profile_id="browser-a")
    store.update_preferences({
        "symbols": ["btc-usd"],
        "active_tab": "crypto",
        "symbol_categories": {"BTC-USD": "crypto"},
    }, profile_id="browser-b")

    assert store.get_preferences(profile_id="browser-a") == {
        "symbols": ["AAPL"],
        "active_tab": "us",
        "symbol_categories": {"AAPL": "us"},
        "watch_groups": [],
    }
    assert store.get_preferences(profile_id="browser-b") == {
        "symbols": ["BTC-USD"],
        "active_tab": "crypto",
        "symbol_categories": {"BTC-USD": "crypto"},
        "watch_groups": [],
    }


def test_realtime_preferences_store_sanitizes_profile_id(tmp_path):
    store = RealtimePreferencesStore(storage_path=tmp_path)

    store.update_preferences({
        "symbols": ["msft"],
        "active_tab": "us",
        "symbol_categories": {"msft": "us"},
    }, profile_id="  Browser A / Test  ")

    assert store.get_preferences(profile_id="browser-a---test") == {
        "symbols": ["MSFT"],
        "active_tab": "us",
        "symbol_categories": {"MSFT": "us"},
        "watch_groups": [],
    }
