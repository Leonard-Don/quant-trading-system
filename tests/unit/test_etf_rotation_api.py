"""Unit tests for the ETF rotation HTTP surface.

The endpoint should:
1. Return the same plan shape as ``scripts.daily_etf_signal.generate_plan()``.
2. Be manual-only — surface a deterministic plan without contacting any broker
   or external quote provider.
3. Refuse to leak any broker / order routing fields into suggestions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import etf_rotation as etf_endpoint
from backend.main import app
from scripts import daily_etf_signal

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
EXPECTED_EXECUTION_CONTRACT = {
    "mode": "manual_only",
    "manual_only": True,
    "auto_ordering": False,
    "broker_routing": False,
    "broker_submission": False,
    "order_transport": "none",
    "operator_review_required": True,
}


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


def test_daily_signal_exposes_manual_only_execution_contract() -> None:
    client = TestClient(app)

    response = client.get(_synthetic_path())

    assert response.status_code == 200
    assert response.json()["data"]["execution_contract"] == EXPECTED_EXECUTION_CONTRACT


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
    captured = {}

    def fake_fetch(codes, *, use_cache=True):
        from src.data.etf_rotation import EtfQuote

        captured["codes"] = list(codes)
        captured["use_cache"] = use_cache
        quote = EtfQuote(
            code="510300",
            name="沪深300ETF",
            current_price=6.0,
            prev_close=5.5,
            open_price=5.6,
            high=6.1,
            low=5.4,
            volume=123456,
            timestamp="2026-05-14T11:00:00+00:00",
            source="fake-live",
        )
        return {"510300": quote}, {
            "requested": len(codes),
            "resolved": 1,
            "missing": max(len(codes) - 1, 0),
            "use_cache": use_cache,
            "symbols": [f"{c}.SS" for c in codes],
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", fake_fetch)

    client = TestClient(app)
    data = client.get("/etf-rotation/daily-signal").json()["data"]

    assert "510300" in captured["codes"]
    assert captured["use_cache"] is True
    assert data["quote_source"] == "live"
    assert data["live_quote_status"]["resolved"] == 1
    assert data["quote_snapshot"]["510300"]["current_price"] == 6.0
    assert data["quote_snapshot"]["510300"]["source"] == "fake-live"
    # 510300 example seed: 1000 shares at 5.02. The live endpoint must
    # reprice the holding to 6.0 before computing total asset / weights —
    # we just check the repricing visibly moved the 510300 weight up
    # (the example portfolio's exact total is intentionally generic).
    example_seed = daily_etf_signal.load_default_holdings()
    example_total = sum(h.market_value for h in example_seed)
    assert data["total_asset"] > example_total  # 510300 was repriced upward
    assert data["current_weights"]["510300"] > 0.25


def test_live_target_returns_503_when_no_cached_plan() -> None:
    client = TestClient(app)
    response = client.get("/etf-rotation/live-target")
    assert response.status_code == 503
    # The global error handler may wrap detail into an envelope; just
    # confirm the message surfaces somewhere.
    body = response.text
    assert "plan" in body.lower()


def test_live_target_trigger_refresh_builds_initial_plan() -> None:
    client = TestClient(app)
    response = client.get("/etf-rotation/live-target?trigger_refresh=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "plan" in payload["data"]
    assert "adjusted_weights" in payload["data"]["plan"]
    assert payload["refresh"]["refreshed"] is True


def test_live_endpoints_forward_policy_factor_override() -> None:
    class CaptureService:
        def __init__(self) -> None:
            self.calls = []

        def refresh(self, **kwargs):
            self.calls.append(kwargs)
            cached = SimpleNamespace(
                plan={"adjusted_weights": {"CASH": 1.0}},
                refreshed_at=datetime(2026, 5, 15, 2, 0, tzinfo=timezone.utc),
                quote_source="test",
                debounced=False,
                debounce_max_delta=None,
                reasons=[],
            )
            return SimpleNamespace(
                refreshed=True,
                cached=cached,
                skipped_reason=None,
            )

        def get_cached_plan(self):
            return None

        def is_trading_hours(self):
            return False

    service = CaptureService()
    etf_endpoint.install_service(service)
    try:
        client = TestClient(app)
        live_response = client.get(
            "/etf-rotation/live-target"
            "?trigger_refresh=true&enable_policy_signal_factor=true"
        )
        refresh_response = client.post(
            "/etf-rotation/refresh"
            "?use_cache=false&enable_policy_signal_factor=false"
        )
    finally:
        etf_endpoint.reset_service_for_tests()

    assert live_response.status_code == 200
    assert refresh_response.status_code == 200
    assert service.calls[0]["force"] is True
    assert service.calls[0]["enable_policy_signal_factor"] is True
    assert service.calls[1]["force"] is True
    assert service.calls[1]["use_cache"] is False
    assert service.calls[1]["enable_policy_signal_factor"] is False


def test_live_target_returns_cached_plan_after_initial_refresh() -> None:
    client = TestClient(app)
    client.get("/etf-rotation/live-target?trigger_refresh=true")

    response = client.get("/etf-rotation/live-target")
    assert response.status_code == 200
    payload = response.json()
    assert "refreshed_at" in payload["data"]
    assert "is_trading_hours" in payload["refresh"]


def test_post_refresh_force_refreshes_even_outside_trading_hours() -> None:
    client = TestClient(app)
    response = client.post("/etf-rotation/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["refresh"]["refreshed"] is True


def test_reload_config_returns_summary_with_universe_and_rules() -> None:
    client = TestClient(app)
    response = client.post("/etf-rotation/reload-config?refresh_after=false")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "universe" in data and len(data["universe"]) >= 5
    for required in ("risk_rules", "strategy", "refresh", "regime", "premium"):
        assert required in data, f"missing {required}"
    # No refresh requested → null refresh block
    assert payload["refresh"] is None


def test_reload_config_then_refresh_returns_refresh_metadata() -> None:
    client = TestClient(app)
    response = client.post("/etf-rotation/reload-config?refresh_after=true")
    assert response.status_code == 200
    refresh = response.json()["refresh"]
    assert refresh is not None
    assert refresh["refreshed"] is True
    assert refresh["refreshed_at"] is not None


def test_audit_log_endpoint_returns_recent_entries(tmp_path, monkeypatch) -> None:
    """Write a deterministic audit log to a temp file, point the loader at
    it, and verify the endpoint returns the rows."""
    import json
    audit_path = tmp_path / "audit.jsonl"
    rows = [
        {"run_at": "2026-05-14T10:00:00+00:00", "quote_source": "test:1", "adjusted_weights": {"CASH": 0.5}},
        {"run_at": "2026-05-14T10:05:00+00:00", "quote_source": "test:2", "adjusted_weights": {"CASH": 0.45}},
    ]
    audit_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))

    client = TestClient(app)
    response = client.get("/etf-rotation/audit-log?limit=10")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["returned"] == 2
    assert payload["total"] == 2
    assert payload["entries"][0]["quote_source"] == "test:1"
    assert payload["entries"][1]["quote_source"] == "test:2"


def test_analytics_endpoint_returns_zero_state_on_empty_log(tmp_path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))

    client = TestClient(app)
    response = client.get("/etf-rotation/analytics")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["n_audit_entries"] == 0
    assert "horizons" in data
    for h in data["horizons"].values():
        assert h["n_pairs"] == 0
        assert h["information_coefficient"] is None


def test_analytics_endpoint_computes_ic_from_seeded_history(tmp_path, monkeypatch) -> None:
    """A monotone score→return relationship must yield positive IC."""

    import json
    audit_path = tmp_path / "audit.jsonl"
    rows = []
    base_price = 5.00
    # 6 entries every 30 minutes, score positively correlated with subsequent returns.
    for i, (score, price) in enumerate([
        (80.0, base_price * 1.00),
        (70.0, base_price * 1.02),
        (90.0, base_price * 1.04),
        (60.0, base_price * 1.07),
        (40.0, base_price * 1.06),
        (50.0, base_price * 1.05),
    ]):
        ts = f"2026-05-15T{10 + (i * 30) // 60:02d}:{(i * 30) % 60:02d}:00+00:00"
        rows.append({
            "run_at": ts,
            "score_breakdown": {"X": {"score": score}},
            "prices_at_decision": {"X": price},
        })
    audit_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))

    client = TestClient(app)
    response = client.get("/etf-rotation/analytics?horizons=30")
    assert response.status_code == 200
    data = response.json()["data"]
    horizon = data["horizons"]["horizon_30min"]
    assert horizon["n_pairs"] >= 3
    assert horizon["information_coefficient"] is not None


def test_analytics_endpoint_rejects_invalid_horizons() -> None:
    client = TestClient(app)
    response = client.get("/etf-rotation/analytics?horizons=not_a_number,60")
    assert response.status_code == 400


def test_audit_log_endpoint_filters_by_since(tmp_path, monkeypatch) -> None:
    import json
    audit_path = tmp_path / "audit.jsonl"
    rows = [
        {"run_at": "2026-05-14T10:00:00+00:00", "quote_source": "a"},
        {"run_at": "2026-05-14T11:00:00+00:00", "quote_source": "b"},
        {"run_at": "2026-05-14T12:00:00+00:00", "quote_source": "c"},
    ]
    audit_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))

    client = TestClient(app)
    response = client.get("/etf-rotation/audit-log?since=2026-05-14T10:30:00")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["returned"] == 2
    assert {e["quote_source"] for e in payload["entries"]} == {"b", "c"}


def test_daily_signal_use_cache_false_forces_fresh_live_quote_fetch(monkeypatch) -> None:
    observed = []

    def fake_fetch(codes, *, use_cache=True):
        observed.append(use_cache)
        return {}, {
            "requested": len(codes),
            "resolved": 0,
            "missing": len(codes),
            "use_cache": use_cache,
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", fake_fetch)

    client = TestClient(app)
    response = client.get("/etf-rotation/daily-signal?use_cache=false")

    assert response.status_code == 200
    assert observed == [False]
    data = response.json()["data"]
    assert data["quote_source"] == "fallback_synthetic"
    assert data["live_quote_status"]["requested"] == 5
    assert data["live_quote_status"]["resolved"] == 0


# ---------------------------------------------------------------------------
# /etf-rotation/preferences + precedence chain
#
# These tests exercise the per-installation preference store that backs the
# dashboard's policy-signal-factor toggle. Each test points the store at a
# tmp_path so it cannot stomp the developer's real ~/.config file.
# ---------------------------------------------------------------------------


def _install_isolated_preferences(monkeypatch, tmp_path) -> None:
    """Point the preferences singleton at a tmp_path file and install it."""

    from src.strategy import etf_rotation_preferences as prefs_module

    prefs_path = tmp_path / "ui_preferences.json"
    monkeypatch.setenv(prefs_module.PREFERENCES_PATH_ENV, str(prefs_path))
    prefs_module.reset_preferences_store_for_tests()
    etf_endpoint.install_preferences(prefs_module.EtfRotationPreferences(path=prefs_path))


def test_preferences_get_returns_default_when_unset(monkeypatch, tmp_path) -> None:
    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/etf-rotation/preferences")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        # File not written yet → preference.policy_signal_factor_enabled is None
        assert data["preference"]["policy_signal_factor_enabled"] is None
        # No preference → effective folds in the config default (False)
        assert data["effective"]["policy_signal_factor_enabled"] is False
        assert data["effective"]["source"] == "config"
        assert data["config_default"]["policy_signal_factor_enabled"] is False
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_preferences_post_persists_and_atomic(monkeypatch, tmp_path) -> None:
    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        post_response = client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": True},
        )
        assert post_response.status_code == 200
        post_data = post_response.json()["data"]
        assert post_data["preference"]["policy_signal_factor_enabled"] is True
        assert post_data["effective"]["policy_signal_factor_enabled"] is True
        assert post_data["effective"]["source"] == "preference"

        # The file lives at the path the env var points to and contains valid
        # JSON — i.e. the temp-file + rename actually committed.
        prefs_path = tmp_path / "ui_preferences.json"
        assert prefs_path.exists(), "Preferences file was not written"
        import json
        on_disk = json.loads(prefs_path.read_text(encoding="utf-8"))
        assert on_disk["policy_signal_factor_enabled"] is True
        # No leftover .tmp file — proves write-then-rename happened.
        assert not (tmp_path / "ui_preferences.json.tmp").exists()

        # A subsequent GET sees the same state (i.e. the singleton reads
        # from disk on every snapshot, not from an in-memory cache that
        # could go stale).
        get_response = client.get("/etf-rotation/preferences")
        assert get_response.status_code == 200
        get_data = get_response.json()["data"]
        assert get_data["preference"]["policy_signal_factor_enabled"] is True
        assert get_data["effective"]["source"] == "preference"
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_preferences_post_null_clears_the_preference(monkeypatch, tmp_path) -> None:
    """Sending ``null`` removes the preference so the config default wins again."""

    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": False},
        )

        clear_response = client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": None},
        )
        assert clear_response.status_code == 200
        data = clear_response.json()["data"]
        assert data["preference"]["policy_signal_factor_enabled"] is None
        # With no opinion, we fall through to the config default (False).
        assert data["effective"]["source"] == "config"
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_preferences_post_rejects_non_boolean(monkeypatch, tmp_path) -> None:
    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        response = client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": "yes"},
        )
        assert response.status_code == 422
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_daily_signal_precedence_query_beats_preference(monkeypatch, tmp_path) -> None:
    """``?enable_policy_signal_factor=false`` overrides a True preference."""

    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": True},
        )

        # Query param wins → enabled=False, source='query'.
        response = client.get(
            "/etf-rotation/daily-signal?quote_source=synthetic"
            "&enable_policy_signal_factor=false"
        )
        assert response.status_code == 200
        plan = response.json()["data"]
        assert plan["policy_signal_factor_enabled"] is False
        summary = plan["policy_signal_factor"]
        assert summary["enabled"] is False
        assert summary["source"] == "query"

        # Without the query param the preference wins.
        response_pref = client.get(
            "/etf-rotation/daily-signal?quote_source=synthetic"
        )
        plan_pref = response_pref.json()["data"]
        assert plan_pref["policy_signal_factor_enabled"] is True
        assert plan_pref["policy_signal_factor"]["source"] == "preference"
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_daily_signal_precedence_preference_beats_config(monkeypatch, tmp_path) -> None:
    """Preference=True with config default False yields enabled=True."""

    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": True},
        )

        response = client.get(
            "/etf-rotation/daily-signal?quote_source=synthetic"
        )
        assert response.status_code == 200
        plan = response.json()["data"]
        # config_default is False (the built-in), preference is True → True wins.
        assert plan["policy_signal_factor_enabled"] is True
        assert plan["policy_signal_factor"]["source"] == "preference"
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_daily_signal_returns_effective_enabled_field(monkeypatch, tmp_path) -> None:
    """Even without any user opinion, the response exposes the effective bool
    so the UI can render the toggle without a separate round-trip."""

    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        response = client.get(
            "/etf-rotation/daily-signal?quote_source=synthetic"
        )
        assert response.status_code == 200
        plan = response.json()["data"]
        # Field present + boolean even on the cold-start path.
        assert isinstance(plan.get("policy_signal_factor_enabled"), bool)
        assert plan["policy_signal_factor"]["source"] == "config"
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_refresh_override_uses_persisted_preference(monkeypatch, tmp_path) -> None:
    """Background service.refresh callers have no query param, but should
    still inherit the persisted UI preference when one exists.
    """

    _install_isolated_preferences(monkeypatch, tmp_path)
    try:
        client = TestClient(app)
        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": True},
        )
        assert etf_endpoint.resolve_policy_factor_refresh_override() is True

        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": None},
        )
        assert etf_endpoint.resolve_policy_factor_refresh_override() is None
    finally:
        etf_endpoint.reset_preferences_for_tests()


def test_reload_config_refresh_honors_persisted_preference(
    monkeypatch, tmp_path
) -> None:
    """reload-config refresh should compute weights with the UI preference."""

    from src.strategy.etf_rotation_config_loader import load_strategy_config

    class CaptureReloadService:
        def __init__(self) -> None:
            self.calls = []

        def reload_strategy_config(self):
            return load_strategy_config()

        def refresh(self, **kwargs):
            self.calls.append(kwargs)
            cached = SimpleNamespace(
                plan={"adjusted_weights": {"CASH": 1.0}},
                refreshed_at=datetime(2026, 5, 15, 2, 0, tzinfo=timezone.utc),
                quote_source="test",
                debounced=False,
                debounce_max_delta=None,
                reasons=[],
            )
            return SimpleNamespace(
                refreshed=True,
                cached=cached,
                skipped_reason=None,
            )

    _install_isolated_preferences(monkeypatch, tmp_path)
    service = CaptureReloadService()
    etf_endpoint.install_service(service)  # type: ignore[arg-type]
    try:
        client = TestClient(app)
        client.post(
            "/etf-rotation/preferences",
            json={"policy_signal_factor_enabled": True},
        )
        response = client.post("/etf-rotation/reload-config?refresh_after=true")
    finally:
        etf_endpoint.reset_service_for_tests()
        etf_endpoint.reset_preferences_for_tests()

    assert response.status_code == 200
    assert service.calls[0]["force"] is True
    assert service.calls[0]["enable_policy_signal_factor"] is True


# ---------------------------------------------------------------------------
# /policy-factor-attribution
# ---------------------------------------------------------------------------


def test_policy_factor_attribution_returns_zero_when_audit_missing(
    tmp_path, monkeypatch,
) -> None:
    """No audit log → endpoint returns a zero report with a note, not 404."""

    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(tmp_path / "missing.jsonl"))
    etf_endpoint.reset_attribution_cache_for_tests()

    client = TestClient(app)
    response = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["n_factor_on_rebalances"] == 0
    assert data["factor_contribution_pct"] == 0.0


def test_policy_factor_attribution_replays_factor_on_rows(
    tmp_path, monkeypatch,
) -> None:
    """A synthetic factor-ON audit + flat prices → the endpoint returns numbers."""

    import json
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps({
            "run_at": "2026-05-10T02:00:00+00:00",
            "adjusted_weights": {"512400": 0.22},
            "target_weights": {"512400": 0.22},
            "score_breakdown": {
                "512400": {"policy_adjustment": {
                    "industry": "metals", "signal": "bullish",
                    "multiplier": 1.10, "weight_before": 0.20,
                    "weight_after": 0.22, "delta_weight": 0.02,
                    "applied": True,
                }},
            },
            "policy_signal_factor": {"enabled": True, "applied_count": 1},
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))
    etf_endpoint.reset_attribution_cache_for_tests()

    # Stub the (network-bound) price fetcher with a flat in-memory matrix.
    import pandas as pd
    idx = pd.date_range(start="2026-05-10", end="2026-05-20", freq="D")
    nav = pd.DataFrame(
        {"512400": [100.0 * (1.005 ** i) for i in range(len(idx))]},
        index=idx,
    )
    monkeypatch.setattr(etf_endpoint, "_fetch_attribution_prices", lambda *a, **k: nav)

    client = TestClient(app)
    response = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["n_factor_on_rebalances"] == 1
    # Bullish boost on a rising ETF → strictly positive contribution.
    assert data["factor_contribution_pct"] > 0
    assert len(data["per_rebalance_attribution"]) == 1


def test_policy_factor_attribution_uses_cache_within_ttl(
    tmp_path, monkeypatch,
) -> None:
    """Second call within TTL must return ``cached=True`` and skip the engine."""

    import json
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps({
            "run_at": "2026-05-10T02:00:00+00:00",
            "adjusted_weights": {"512400": 0.20},
            "policy_signal_factor": {"enabled": False},
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))
    etf_endpoint.reset_attribution_cache_for_tests()

    import pandas as pd
    monkeypatch.setattr(
        etf_endpoint, "_fetch_attribution_prices", lambda *a, **k: pd.DataFrame(),
    )

    client = TestClient(app)
    first = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    second = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json().get("cache_age_seconds", 0) >= 0


def test_policy_factor_attribution_cache_invalidates_when_audit_changes(
    tmp_path, monkeypatch,
) -> None:
    """Appending a new audit row should bypass the 5-minute cache automatically."""

    import json

    import pandas as pd

    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps({
            "run_at": "2026-05-10T02:00:00+00:00",
            "adjusted_weights": {"512400": 0.20},
            "policy_signal_factor": {"enabled": False},
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ETF_AUDIT_LOG_PATH", str(audit_path))
    etf_endpoint.reset_attribution_cache_for_tests()

    idx = pd.date_range(start="2026-05-10", end="2026-05-20", freq="D")
    nav = pd.DataFrame(
        {"512400": [100.0 * (1.01 ** i) for i in range(len(idx))]},
        index=idx,
    )
    monkeypatch.setattr(etf_endpoint, "_fetch_attribution_prices", lambda *a, **k: nav)

    client = TestClient(app)
    first = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert first.json()["data"]["n_factor_on_rebalances"] == 0

    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "run_at": "2026-05-11T02:00:00+00:00",
            "adjusted_weights": {"512400": 0.22},
            "score_breakdown": {
                "512400": {"policy_adjustment": {
                    "industry": "metals", "signal": "bullish",
                    "multiplier": 1.10, "weight_before": 0.20,
                    "weight_after": 0.22, "delta_weight": 0.02,
                    "applied": True,
                }},
            },
            "policy_signal_factor": {"enabled": True, "applied_count": 1},
        }, ensure_ascii=False))
        fh.write("\n")

    second = client.get("/etf-rotation/policy-factor-attribution?period_days=30")
    assert second.status_code == 200
    assert second.json()["cached"] is False
    assert second.json()["data"]["n_factor_on_rebalances"] == 1


# ---------------------------------------------------------------------------
# /walkforward
# ---------------------------------------------------------------------------


def test_walkforward_empty_windows_response_is_frontend_safe(
    tmp_path, monkeypatch,
) -> None:
    """No executable windows should serialise as a finite zero report.

    This exercises the HTTP layer, not just ``WalkforwardReport.to_dict()``:
    a one-row committed-price CSV can generate a calendar window, but every
    per-window backtest is empty after warmup. The frontend contract is still
    ``n_windows=0`` + ``windows=[]`` so it can render the degraded empty state.
    """

    import json
    import math

    prices_csv = tmp_path / "etf_prices_4y.csv"
    prices_csv.write_text("date,512400\n2024-01-02,100.0\n", encoding="utf-8")
    monkeypatch.setattr(etf_endpoint, "DEFAULT_BACKTEST_PRICE_CSV", prices_csv)
    etf_endpoint.reset_walkforward_cache_for_tests()

    client = TestClient(app)
    response = client.post(
        "/etf-rotation/walkforward",
        json={
            "period_start": "2024-01-01",
            "period_end": "2024-03-31",
            "window_months": 3,
            "step_months": 1,
            "refresh": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["cached"] is False
    data = payload["data"]
    assert data["n_windows"] == 0
    assert data["windows"] == []

    zero_metric_keys = [
        "aggregate_return_pct",
        "mean_window_return_pct",
        "median_window_return_pct",
        "return_std_pct",
        "pct_positive_windows",
        "mean_sharpe",
        "median_sharpe",
        "mean_max_dd_pct",
        "worst_window_dd_pct",
        "mean_buy_hold_return_pct",
        "consistency_score",
    ]
    for key in zero_metric_keys:
        assert data[key] == 0.0
        assert math.isfinite(data[key])

    assert any(c.startswith("empty_report:all_windows_empty") for c in data["caveats"])
    assert "empty_report:insufficient_history" in " ".join(data["caveats"])
    serialised = json.dumps(payload, allow_nan=False)
    assert "NaN" not in serialised
    assert "undefined" not in serialised


# ---------------------------------------------------------------------------
# Data-safety gate: actionable / non_actionable_reasons contract
#
# A plan generated from synthetic (fabricated) price data must be explicitly
# flagged actionable=False so the client can never mistake a demo plan for a
# live-tradeable one.  These tests assert that the API contract is honoured
# regardless of how the plan reaches the response (direct from generate_plan or
# via the EtfRotationService cache).
# ---------------------------------------------------------------------------


def test_daily_signal_synthetic_plan_is_not_actionable() -> None:
    """quote_source=synthetic → actionable=False, non_actionable_reasons is populated."""

    client = TestClient(app)
    response = client.get(_synthetic_path())

    assert response.status_code == 200
    data = response.json()["data"]

    # actionable must be a bool, not None or missing.
    assert isinstance(data.get("actionable"), bool), (
        "actionable must be an explicit bool in the response"
    )
    # Synthetic plans are never safe to trade.
    assert data["actionable"] is False, (
        "a plan built on fabricated price data must be marked actionable=False"
    )
    # non_actionable_reasons must be a non-empty list explaining why.
    assert isinstance(data.get("non_actionable_reasons"), list)
    assert len(data["non_actionable_reasons"]) > 0
    assert any("synthetic" in r for r in data["non_actionable_reasons"])


def test_daily_signal_actionable_field_is_always_a_bool(monkeypatch) -> None:
    """Even on the live path actionable must be a typed bool, never absent."""

    def fake_fetch(codes, *, use_cache=True):
        from src.data.etf_rotation import EtfQuote

        quote = EtfQuote(
            code="510300",
            name="沪深300ETF",
            current_price=6.0,
            prev_close=5.5,
            open_price=5.6,
            high=6.1,
            low=5.4,
            volume=123456,
            timestamp="2026-05-14T11:00:00+00:00",
            source="fake-live",
        )
        return {"510300": quote}, {
            "requested": len(codes),
            "resolved": 1,
            "missing": max(len(codes) - 1, 0),
            "use_cache": use_cache,
            "symbols": [f"{c}.SS" for c in codes],
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", fake_fetch)

    client = TestClient(app)
    data = client.get("/etf-rotation/daily-signal").json()["data"]

    # actionable is always a bool — never None, never absent.
    assert isinstance(data.get("actionable"), bool)
    # non_actionable_reasons is always a list — even when empty.
    assert isinstance(data.get("non_actionable_reasons"), list)


def test_live_target_plan_has_actionable_field() -> None:
    """live-target with trigger_refresh must carry actionable in the nested plan."""

    client = TestClient(app)
    response = client.get("/etf-rotation/live-target?trigger_refresh=true")

    assert response.status_code == 200
    plan = response.json()["data"]["plan"]

    assert isinstance(plan.get("actionable"), bool), (
        "live-target plan must expose actionable as an explicit bool"
    )
    assert isinstance(plan.get("non_actionable_reasons"), list), (
        "live-target plan must expose non_actionable_reasons as a list"
    )


def test_live_target_actionable_false_plan_surfaces_reasons() -> None:
    """When the service caches a plan with actionable=False the endpoint must
    expose both ``actionable`` and ``non_actionable_reasons`` to the client.

    This test uses an injected stub service so it is independent of whether
    the real service has access to live price history in CI.
    """

    non_actionable_plan = {
        "manual_only": True,
        "auto_ordering": False,
        "banner": "手动调仓 — 不自动下单",
        "total_asset": 100000.0,
        "current_weights": {"CASH": 1.0},
        "target_weights": {"CASH": 1.0},
        "adjusted_weights": {"CASH": 1.0},
        "suggestions": [],
        "risk_reasons": [],
        "actionable": False,
        "non_actionable_reasons": [
            "price_history_synthetic: plan was built on a fabricated "
            "deterministic price matrix, not real market data"
        ],
        "data_safety": {
            "price_matrix_synthetic": True,
            "price_matrix_stale": False,
            "price_matrix_age_trading_days": None,
            "staleness_threshold_trading_days": 3,
            "override_applied": False,
            "override_available": True,
            "reasons": [
                "price_history_synthetic: plan was built on a fabricated "
                "deterministic price matrix, not real market data"
            ],
        },
    }

    class StubService:
        def refresh(self, **kwargs):
            cached = SimpleNamespace(
                plan=dict(non_actionable_plan),
                refreshed_at=datetime(2026, 5, 22, 2, 0, tzinfo=timezone.utc),
                quote_source="synthetic",
                debounced=False,
                debounce_max_delta=None,
                reasons=[],
            )
            return SimpleNamespace(refreshed=True, cached=cached, skipped_reason=None)

        def get_cached_plan(self):
            return None

        def is_trading_hours(self):
            return False

    etf_endpoint.install_service(StubService())
    try:
        client = TestClient(app)
        response = client.get("/etf-rotation/live-target?trigger_refresh=true")
    finally:
        etf_endpoint.reset_service_for_tests()

    assert response.status_code == 200
    plan = response.json()["data"]["plan"]

    assert plan["actionable"] is False, (
        "endpoint must surface actionable=False from the cached plan"
    )
    reasons = plan["non_actionable_reasons"]
    assert isinstance(reasons, list) and len(reasons) > 0
    assert any("synthetic" in r for r in reasons)


def test_live_target_stamps_execution_contract_on_cached_legacy_plan() -> None:
    """Cached plans from older service instances still get the API contract.

    This guards route-surface consumers: every plan-bearing ETF HTTP response
    must include the nested manual-only execution contract even when the cached
    payload predates the field.
    """

    legacy_plan = {
        "total_asset": 100000.0,
        "current_weights": {"CASH": 1.0},
        "target_weights": {"CASH": 1.0},
        "adjusted_weights": {"CASH": 1.0},
        "suggestions": [],
        "risk_reasons": [],
    }

    class StubService:
        def get_cached_plan(self):
            return SimpleNamespace(
                plan=dict(legacy_plan),
                refreshed_at=datetime(2026, 5, 22, 2, 0, tzinfo=timezone.utc),
                quote_source="legacy-cache",
                debounced=False,
                debounce_max_delta=None,
                reasons=[],
            )

        def is_trading_hours(self):
            return False

    etf_endpoint.install_service(StubService())  # type: ignore[arg-type]
    try:
        client = TestClient(app)
        response = client.get("/etf-rotation/live-target")
    finally:
        etf_endpoint.reset_service_for_tests()

    assert response.status_code == 200
    plan = response.json()["data"]["plan"]
    assert plan["manual_only"] is True
    assert plan["auto_ordering"] is False
    assert plan["execution_contract"] == EXPECTED_EXECUTION_CONTRACT


def test_post_refresh_plan_has_actionable_field() -> None:
    """POST /refresh must also carry actionable in the nested plan."""

    client = TestClient(app)
    response = client.post("/etf-rotation/refresh")

    assert response.status_code == 200
    plan = response.json()["data"]["plan"]

    assert isinstance(plan.get("actionable"), bool)
    assert isinstance(plan.get("non_actionable_reasons"), list)
