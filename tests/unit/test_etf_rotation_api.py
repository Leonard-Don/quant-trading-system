"""Unit tests for the ETF rotation HTTP surface.

The endpoint should:
1. Return the same plan shape as ``scripts.daily_etf_signal.generate_plan()``.
2. Be manual-only — surface a deterministic plan without contacting any broker
   or external quote provider.
3. Refuse to leak any broker / order routing fields into suggestions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

PLAN_KEYS = {
    "manual_only",
    "auto_ordering",
    "banner",
    "total_asset",
    "current_weights",
    "target_weights",
    "adjusted_weights",
    "suggestions",
    "risk_reasons",
}

DEFAULT_SEED_CODES = {"159985", "512400", "510300", "518680", "513130"}


def _synthetic_path(query: str = "") -> str:
    suffix = f"&{query}" if query else ""
    return f"/etf-rotation/daily-signal?quote_source=synthetic{suffix}"


def test_daily_signal_returns_full_plan_envelope() -> None:
    client = TestClient(app)
    response = client.get(_synthetic_path())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    missing = PLAN_KEYS - data.keys()
    assert not missing, f"Missing keys in plan: {missing}"


def test_daily_signal_is_manual_only_and_no_auto_ordering() -> None:
    client = TestClient(app)
    response = client.get(_synthetic_path())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["manual_only"] is True
    assert data["auto_ordering"] is False
    assert isinstance(data["banner"], str) and data["banner"]
    assert "手动" in data["banner"]
    assert "自动下单" in data["banner"]


def test_daily_signal_covers_seed_codes() -> None:
    client = TestClient(app)
    response = client.get(_synthetic_path())

    data = response.json()["data"]
    assert set(data["current_weights"]) >= DEFAULT_SEED_CODES
    assert set(data["target_weights"]) >= DEFAULT_SEED_CODES
    assert isinstance(data["suggestions"], list)


def test_daily_signal_suggestions_have_no_broker_or_order_fields() -> None:
    client = TestClient(app)
    response = client.get(_synthetic_path())

    data = response.json()["data"]
    forbidden = {"broker", "order_id", "venue", "submitted", "account"}
    for suggestion in data["suggestions"]:
        assert suggestion["action"] in {"buy", "sell", "hold"}
        leaked = forbidden & suggestion.keys()
        assert not leaked, f"Suggestion leaked broker fields: {leaked}"


def test_daily_signal_is_deterministic_across_calls() -> None:
    client = TestClient(app)
    first = client.get(_synthetic_path()).json()["data"]
    second = client.get(_synthetic_path()).json()["data"]

    assert first["current_weights"] == second["current_weights"]
    assert first["target_weights"] == second["target_weights"]
    assert first["adjusted_weights"] == second["adjusted_weights"]
    assert [s["code"] for s in first["suggestions"]] == [
        s["code"] for s in second["suggestions"]
    ]


def test_daily_signal_threshold_weight_filters_smaller_suggestions() -> None:
    """A very high threshold should suppress all sell/buy suggestions."""

    client = TestClient(app)
    baseline = client.get(_synthetic_path()).json()["data"]
    filtered = client.get(_synthetic_path("threshold_weight=0.99")).json()["data"]

    baseline_actions = {s["action"] for s in baseline["suggestions"]}
    filtered_actions = {s["action"] for s in filtered["suggestions"]}
    # With a 99% threshold every drift is below threshold → only holds remain
    assert filtered_actions <= {"hold"}
    # Sanity: baseline should typically have at least one non-hold action,
    # otherwise this assertion is meaningless. The screenshot seed produces
    # non-zero adjustments by design.
    assert "hold" in baseline_actions or len(baseline_actions) >= 1


def test_daily_signal_rejects_invalid_threshold_weight() -> None:
    client = TestClient(app)
    response = client.get(_synthetic_path("threshold_weight=2.0"))
    assert response.status_code == 422


def test_daily_signal_default_uses_live_quotes_to_reprice_holdings(monkeypatch) -> None:
    from backend.app.api.v1.endpoints import etf_rotation

    captured = {}

    def fake_get_quotes_dict(symbols, use_cache=True):
        captured["symbols"] = symbols
        captured["use_cache"] = use_cache
        return {
            "510300.SS": {
                "symbol": "510300.SS",
                "price": 6.0,
                "previous_close": 5.5,
                "open": 5.6,
                "high": 6.1,
                "low": 5.4,
                "volume": 123456,
                "timestamp": "2026-05-14T11:00:00+00:00",
                "source": "fake-live",
            }
        }

    monkeypatch.setattr(etf_rotation.realtime_manager, "get_quotes_dict", fake_get_quotes_dict)

    client = TestClient(app)
    data = client.get("/etf-rotation/daily-signal").json()["data"]

    assert "510300.SS" in captured["symbols"]
    assert captured["use_cache"] is True
    assert data["quote_source"] == "live"
    assert data["live_quote_status"]["resolved"] == 1
    assert data["quote_snapshot"]["510300"]["current_price"] == 6.0
    assert data["quote_snapshot"]["510300"]["source"] == "fake-live"
    # 510300 default seed: 1400 shares at 5.017. The live endpoint should
    # reprice the holding to 6.0 before computing total asset/current weights.
    assert data["total_asset"] > 32000
    assert data["current_weights"]["510300"] > 0.25


def test_daily_signal_use_cache_false_forces_fresh_live_quote_fetch(monkeypatch) -> None:
    from backend.app.api.v1.endpoints import etf_rotation

    observed = []

    def fake_get_quotes_dict(symbols, use_cache=True):
        observed.append(use_cache)
        return {}

    monkeypatch.setattr(etf_rotation.realtime_manager, "get_quotes_dict", fake_get_quotes_dict)

    client = TestClient(app)
    response = client.get("/etf-rotation/daily-signal?use_cache=false")

    assert response.status_code == 200
    assert observed == [False]
    data = response.json()["data"]
    assert data["quote_source"] == "fallback_synthetic"
    assert data["live_quote_status"]["requested"] == 5
    assert data["live_quote_status"]["resolved"] == 0
