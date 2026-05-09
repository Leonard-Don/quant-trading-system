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


def test_realtime_alerts_store_coerces_invalid_numeric_fields_to_defaults(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    updated = store.update_alerts({
        "alerts": [
            {
                "symbol": "AAPL",
                "condition": "price_above",
                "threshold": "not-a-number",
                "tolerancePercent": "bad",
                "cooldownMinutes": "garbage",
            },
        ],
    })

    alert = updated["alerts"][0]
    assert alert["threshold"] is None
    assert alert["tolerancePercent"] == 0.1
    assert alert["cooldownMinutes"] == 15


def test_realtime_alerts_store_sanitizes_profile_id_path_traversal(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)
    dangerous_profile = "../../etc/passwd"

    store.update_alerts(
        {"alerts": [{"symbol": "AAPL", "condition": "price_above", "threshold": 1}]},
        profile_id=dangerous_profile,
    )

    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].parent == tmp_path
    assert "/" not in written[0].name and ".." not in written[0].name

    round_tripped = store.get_alerts(profile_id=dangerous_profile)["alerts"]
    assert round_tripped and round_tripped[0]["symbol"] == "AAPL"


def test_realtime_alerts_store_returns_empty_default_for_missing_or_corrupt_file(tmp_path):
    store = RealtimeAlertsStore(storage_path=tmp_path)

    missing = store.get_alerts(profile_id="never-saved")
    assert missing == {"alerts": [], "alert_hit_history": []}

    (tmp_path / "corrupt.json").write_text("{not valid json", encoding="utf-8")
    corrupt = store.get_alerts(profile_id="corrupt")
    assert corrupt == {"alerts": [], "alert_hit_history": []}
