from backend.app.services.realtime_alerts import RealtimeAlertsStore


def test_realtime_alerts_store_normalizes_symbols_and_cooldown(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    updated = store.update_alerts({
        "alerts": [
            {
                "id": "alert-1",
                "symbol": " aapl ",
                "condition": "price_above",
                "threshold": "195.2",
                "cooldownMinutes": "20",
            },
            {
                "id": "alert-2",
                "symbol": "btc-usd",
                "condition": "relative_volume_above",
                "threshold": 2.5,
            },
        ],
        "alert_hit_history": [
            {"id": "hit-1", "symbol": "AAPL", "message": "AAPL 提醒已触发"},
        ],
    })

    assert updated["alerts"][0]["symbol"] == "AAPL"
    assert updated["alerts"][0]["threshold"] == 195.2
    assert updated["alerts"][0]["cooldownMinutes"] == 20
    assert updated["alerts"][1]["symbol"] == "BTC-USD"
    assert updated["alerts"][1]["cooldownMinutes"] == 15
    assert updated["alert_hit_history"] == [
        {"id": "hit-1", "symbol": "AAPL", "message": "AAPL 提醒已触发"},
    ]


def test_realtime_alerts_store_filters_invalid_items(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    updated = store.update_alerts({
        "alerts": [
            {"symbol": "", "condition": "price_above"},
            {"symbol": "AAPL", "condition": "not-supported"},
            {"symbol": "MSFT", "condition": "price_below", "threshold": 390},
        ]
    })

    assert updated == {
        "alerts": [
            {
                "symbol": "MSFT",
                "condition": "price_below",
                "threshold": 390.0,
                "tolerancePercent": 0.1,
                "cooldownMinutes": 15,
            }
        ],
        "alert_hit_history": [],
        "_warnings": [
            "alerts[0]: skipped (missing symbol)",
            "alerts[1]: skipped (invalid condition 'not-supported')",
        ],
    }


def test_realtime_alerts_store_isolated_by_profile_id(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    store.update_alerts({
        "alerts": [{"symbol": "AAPL", "condition": "price_above", "threshold": 200}],
        "alert_hit_history": [{"id": "hit-a", "symbol": "AAPL"}],
    }, profile_id="browser-a")
    store.update_alerts({
        "alerts": [{"symbol": "BTC-USD", "condition": "change_pct_above", "threshold": 5}],
        "alert_hit_history": [{"id": "hit-b", "symbol": "BTC-USD"}],
    }, profile_id="browser-b")

    assert store.get_alerts(profile_id="browser-a")["alerts"][0]["symbol"] == "AAPL"
    assert store.get_alerts(profile_id="browser-b")["alerts"][0]["symbol"] == "BTC-USD"
    assert store.get_alerts(profile_id="browser-a")["alert_hit_history"][0]["id"] == "hit-a"
    assert store.get_alerts(profile_id="browser-b")["alert_hit_history"][0]["id"] == "hit-b"


def test_realtime_alerts_store_limits_alert_hit_history(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    updated = store.update_alerts({
        "alerts": [],
        "alert_hit_history": [{"id": f"hit-{index}"} for index in range(120)],
    })

    assert len(updated["alert_hit_history"]) == 80
    assert updated["alert_hit_history"][0]["id"] == "hit-0"
