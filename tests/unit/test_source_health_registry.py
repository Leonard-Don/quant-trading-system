"""Tests for the cross-domain source health registry utility.

The registry normalizes per-source health/freshness metadata into a single
shape so dashboards (ETF rotation, policy radar, market data) can render them
uniformly without each domain re-inventing the field names.

Tests cover:
* Pure helpers (``freshness_label``)
* Builder ordering (required → ok → display name)
* Default-required inference
* As-of parsing (string / datetime / unparseable / missing)
* JSON-safe ``to_dict`` projection
* ETF rotation wiring (the first consumer in this PR)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.source_health import (
    DEFAULT_FRESHNESS,
    FreshnessThresholds,
    build_source_registry,
    freshness_label,
)

# ---------------------------------------------------------------------------
# freshness_label
# ---------------------------------------------------------------------------


def test_freshness_label_returns_missing_when_age_unknown() -> None:
    assert freshness_label(None) == "missing"


def test_freshness_label_default_thresholds_are_daily_cadence() -> None:
    assert DEFAULT_FRESHNESS.fresh_max_seconds == 60 * 60
    assert DEFAULT_FRESHNESS.recent_max_seconds == 24 * 60 * 60
    assert DEFAULT_FRESHNESS.stale_max_seconds == 7 * 24 * 60 * 60


def test_freshness_label_fresh_window_is_one_hour() -> None:
    assert freshness_label(0.0) == "fresh"
    assert freshness_label(59 * 60) == "fresh"


def test_freshness_label_recent_window_extends_to_one_day() -> None:
    assert freshness_label(60 * 60 + 1) == "recent"
    assert freshness_label(23 * 60 * 60) == "recent"


def test_freshness_label_stale_window_extends_to_one_week() -> None:
    assert freshness_label(25 * 60 * 60) == "stale"
    assert freshness_label(6 * 24 * 60 * 60) == "stale"


def test_freshness_label_expired_after_one_week() -> None:
    assert freshness_label(8 * 24 * 60 * 60) == "expired"


def test_freshness_label_treats_negative_age_as_fresh() -> None:
    # `as_of` slightly in the future (clock skew) is not "missing".
    assert freshness_label(-30.0) == "fresh"


def test_freshness_label_respects_custom_thresholds() -> None:
    thresholds = FreshnessThresholds(
        fresh_max_seconds=5.0,
        recent_max_seconds=10.0,
        stale_max_seconds=20.0,
    )
    assert freshness_label(4.0, thresholds=thresholds) == "fresh"
    assert freshness_label(7.0, thresholds=thresholds) == "recent"
    assert freshness_label(15.0, thresholds=thresholds) == "stale"
    assert freshness_label(25.0, thresholds=thresholds) == "expired"


# ---------------------------------------------------------------------------
# build_source_registry — basic normalization
# ---------------------------------------------------------------------------


def test_registry_normalizes_minimal_spec() -> None:
    entries = build_source_registry([{"source_id": "yahoo"}])
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source_id == "yahoo"
    assert entry.display_name == "yahoo"
    assert entry.status == "unknown"
    assert entry.ok is False
    assert entry.required is False
    assert entry.fallback is False
    assert entry.freshness == "missing"
    assert entry.age_seconds is None
    assert entry.as_of is None
    assert entry.reason is None
    assert entry.capabilities == ()


def test_registry_ignores_specs_without_source_id() -> None:
    entries = build_source_registry(
        [
            {"display_name": "no-id"},
            {"source_id": "", "ok": True},
            {"source_id": "  ", "ok": True},
            {"source_id": "yahoo", "ok": True},
        ]
    )
    assert [e.source_id for e in entries] == ["yahoo"]


def test_registry_marks_default_required_source() -> None:
    entries = build_source_registry(
        [
            {"source_id": "yahoo", "ok": True, "status": "ready"},
            {"source_id": "akshare", "ok": True, "status": "ready"},
        ],
        default_required="yahoo",
    )
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["yahoo"].required is True
    assert by_id["akshare"].required is False


def test_registry_explicit_required_overrides_default() -> None:
    entries = build_source_registry(
        [
            {"source_id": "yahoo", "ok": True, "required": False},
            {"source_id": "akshare", "ok": True, "required": True},
        ],
        default_required="yahoo",
    )
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["yahoo"].required is False
    assert by_id["akshare"].required is True


def test_registry_falls_back_flag_inferred_when_unset() -> None:
    entries = build_source_registry(
        [
            {"source_id": "yahoo", "ok": True},
            {"source_id": "akshare", "ok": False, "status": "skipped"},
        ]
    )
    by_id = {entry.source_id: entry for entry in entries}
    # ok=True implies not currently in fallback role
    assert by_id["yahoo"].fallback is False
    # Failing sources are eligible fallbacks
    assert by_id["akshare"].fallback is True


def test_registry_respects_explicit_fallback_flag() -> None:
    entries = build_source_registry(
        [
            {"source_id": "yahoo", "ok": True, "fallback": True},
            {"source_id": "akshare", "ok": False, "fallback": False},
        ]
    )
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["yahoo"].fallback is True
    assert by_id["akshare"].fallback is False


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_registry_orders_required_before_optional() -> None:
    entries = build_source_registry(
        [
            {"source_id": "b", "ok": True},
            {"source_id": "a", "ok": True, "required": True},
        ]
    )
    assert [entry.source_id for entry in entries] == ["a", "b"]


def test_registry_orders_ok_before_failed_within_same_required_tier() -> None:
    entries = build_source_registry(
        [
            {"source_id": "z_failing", "ok": False},
            {"source_id": "a_ready", "ok": True},
        ]
    )
    assert [entry.source_id for entry in entries] == ["a_ready", "z_failing"]


def test_registry_orders_alphabetically_within_same_tier() -> None:
    entries = build_source_registry(
        [
            {"source_id": "yahoo", "display_name": "Yahoo", "ok": True},
            {"source_id": "akshare", "display_name": "AKShare", "ok": True},
        ]
    )
    assert [entry.source_id for entry in entries] == ["akshare", "yahoo"]


def test_registry_required_failed_source_still_comes_before_optional_ok() -> None:
    entries = build_source_registry(
        [
            {"source_id": "optional_ok", "ok": True},
            {"source_id": "required_failed", "ok": False, "required": True},
        ]
    )
    assert [entry.source_id for entry in entries] == [
        "required_failed",
        "optional_ok",
    ]


# ---------------------------------------------------------------------------
# Freshness / as_of parsing
# ---------------------------------------------------------------------------


def test_registry_computes_freshness_from_iso_asof() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": True,
                "as_of": (now - timedelta(minutes=10)).isoformat(),
            },
            {
                "source_id": "akshare",
                "ok": True,
                "as_of": (now - timedelta(hours=12)).isoformat(),
            },
            {
                "source_id": "tushare",
                "ok": True,
                "as_of": (now - timedelta(days=10)).isoformat(),
            },
        ],
        now=now,
    )
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["yahoo"].freshness == "fresh"
    assert by_id["akshare"].freshness == "recent"
    assert by_id["tushare"].freshness == "expired"


def test_registry_accepts_datetime_asof() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": True,
                "as_of": now - timedelta(minutes=5),
            }
        ],
        now=now,
    )
    assert entries[0].freshness == "fresh"
    assert entries[0].age_seconds == pytest.approx(300.0, abs=1.0)


def test_registry_accepts_z_suffix_asof() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    iso_z = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    entries = build_source_registry(
        [{"source_id": "yahoo", "ok": True, "as_of": iso_z}],
        now=now,
    )
    assert entries[0].freshness == "fresh"


def test_registry_ignores_unparseable_asof_strings() -> None:
    entries = build_source_registry(
        [{"source_id": "yahoo", "ok": True, "as_of": "not-a-timestamp"}]
    )
    assert entries[0].freshness == "missing"
    assert entries[0].as_of is None
    assert entries[0].age_seconds is None


def test_registry_marks_missing_when_asof_absent() -> None:
    entries = build_source_registry([{"source_id": "yahoo", "ok": True}])
    assert entries[0].freshness == "missing"
    assert entries[0].age_seconds is None


def test_registry_respects_per_call_freshness_thresholds() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    thresholds = FreshnessThresholds(
        fresh_max_seconds=5.0,
        recent_max_seconds=10.0,
        stale_max_seconds=20.0,
    )
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": True,
                "as_of": (now - timedelta(seconds=15)).isoformat(),
            }
        ],
        now=now,
        thresholds=thresholds,
    )
    assert entries[0].freshness == "stale"


# ---------------------------------------------------------------------------
# Capabilities + reason + projection
# ---------------------------------------------------------------------------


def test_registry_preserves_capabilities_and_reason() -> None:
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": False,
                "status": "error",
                "reason": "HTTPError 500",
                "capabilities": ["historical_data", "latest_quote"],
            }
        ]
    )
    assert entries[0].reason == "HTTPError 500"
    assert entries[0].capabilities == ("historical_data", "latest_quote")


def test_registry_capabilities_accepts_tuple_and_set_inputs() -> None:
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": True,
                "capabilities": ("a", "b"),
            },
            {
                "source_id": "akshare",
                "ok": True,
                "capabilities": {"c", "d"},
            },
        ]
    )
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["yahoo"].capabilities == ("a", "b")
    # Sets are unordered upstream; sort to stabilize for assertion.
    assert sorted(by_id["akshare"].capabilities) == ["c", "d"]


def test_registry_to_dict_returns_json_safe_payload() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "display_name": "Yahoo Finance",
                "ok": True,
                "status": "ready",
                "as_of": (now - timedelta(minutes=10)).isoformat(),
                "capabilities": ["historical_data"],
            }
        ],
        now=now,
        default_required="yahoo",
    )
    payload = entries[0].to_dict()
    assert payload["source_id"] == "yahoo"
    assert payload["display_name"] == "Yahoo Finance"
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["required"] is True
    assert payload["fallback"] is False
    assert payload["freshness"] == "fresh"
    assert payload["capabilities"] == ["historical_data"]
    assert isinstance(payload["age_seconds"], float)
    # asof normalized to ISO Z form for stability across consumers
    assert payload["as_of"].endswith("Z") or "+" in payload["as_of"]


# ---------------------------------------------------------------------------
# ETF rotation wiring (first consumer)
# ---------------------------------------------------------------------------


def test_generate_plan_includes_synthetic_source_health_by_default() -> None:
    from scripts.daily_etf_signal import generate_plan

    plan = generate_plan()
    assert "source_health" in plan
    sources = plan["source_health"]
    assert isinstance(sources, list)
    ids = [entry["source_id"] for entry in sources]
    assert "etf_holdings" in ids
    assert "etf_quotes" in ids
    assert "price_matrix" in ids

    by_id = {entry["source_id"]: entry for entry in sources}
    # Required source is etf_holdings — without it there is no plan.
    assert by_id["etf_holdings"]["required"] is True
    # Defaults are synthetic — status and reason should say so.
    assert by_id["etf_holdings"]["status"] == "synthetic"
    assert by_id["etf_holdings"]["reason"] == "screenshot_seed"
    assert by_id["etf_holdings"]["ok"] is True
    # Synthetic data must not claim a sample timestamp (plan-build time
    # is not the same as data sample time).
    assert by_id["etf_holdings"]["as_of"] is None
    assert by_id["etf_holdings"]["freshness"] == "missing"


def test_generate_plan_marks_supplied_holdings_as_ready_with_asof() -> None:
    from scripts.daily_etf_signal import generate_plan, load_default_holdings

    holdings = load_default_holdings()
    sample = datetime(2026, 5, 14, 11, 55, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    plan = generate_plan(holdings=holdings, holdings_as_of=sample, now=now)
    by_id = {entry["source_id"]: entry for entry in plan["source_health"]}
    assert by_id["etf_holdings"]["status"] == "ready"
    assert by_id["etf_holdings"]["ok"] is True
    # Supplied sample timestamp survives the round trip.
    assert by_id["etf_holdings"]["as_of"] == "2026-05-14T11:55:00Z"
    assert by_id["etf_holdings"]["freshness"] == "fresh"
    # Reason is empty when there is nothing to disclose.
    assert by_id["etf_holdings"]["reason"] is None


def test_generate_plan_supplied_without_asof_does_not_overclaim_freshness() -> None:
    """Supplied data without a sample timestamp must not be stamped 'fresh'.

    Prior to the fix, ``_build_source_health_payload`` stamped ``as_of=now`` for
    any supplied data, which collapsed plan-build time and data-sample time
    into one value — overclaiming freshness for stale snapshots.
    """
    from scripts.daily_etf_signal import generate_plan, load_default_holdings

    holdings = load_default_holdings()
    plan = generate_plan(holdings=holdings)
    by_id = {entry["source_id"]: entry for entry in plan["source_health"]}
    assert by_id["etf_holdings"]["status"] == "ready"
    assert by_id["etf_holdings"]["ok"] is True
    # No supplied sample timestamp → don't claim freshness.
    assert by_id["etf_holdings"]["as_of"] is None
    assert by_id["etf_holdings"]["freshness"] == "missing"
    # The reason should make it discoverable why freshness is missing.
    reason = (by_id["etf_holdings"]["reason"] or "").lower()
    assert "sample_timestamp" in reason


def test_generate_plan_synthetic_quotes_marked_as_fallback() -> None:
    """Synthetic quotes must be distinguishable from real ones via fallback."""
    from scripts.daily_etf_signal import generate_plan

    plan = generate_plan()  # all synthetic
    by_id = {entry["source_id"]: entry for entry in plan["source_health"]}
    assert by_id["etf_quotes"]["status"] == "synthetic"
    assert by_id["etf_quotes"]["ok"] is True
    assert by_id["etf_quotes"]["fallback"] is True
    assert by_id["etf_quotes"]["as_of"] is None
    assert by_id["etf_quotes"]["reason"] == "derived_from_holdings"


def test_generate_plan_synthetic_price_matrix_marked_as_fallback() -> None:
    """Synthetic price history must be distinguishable from real history."""
    from scripts.daily_etf_signal import generate_plan

    plan = generate_plan()  # all synthetic
    by_id = {entry["source_id"]: entry for entry in plan["source_health"]}
    assert by_id["price_matrix"]["status"] == "synthetic"
    assert by_id["price_matrix"]["ok"] is True
    assert by_id["price_matrix"]["fallback"] is True
    assert by_id["price_matrix"]["as_of"] is None
    assert by_id["price_matrix"]["reason"] == "deterministic_random_walk"


def test_generate_plan_records_observed_at_for_every_source() -> None:
    """Every source entry should carry an observed_at (registry build time).

    ``observed_at`` is distinct from ``as_of``: it is the moment the registry
    snapshot was assembled, not the moment the underlying data was sampled.
    Consumers use it to compute "how long ago was this plan built".
    """
    from scripts.daily_etf_signal import generate_plan

    plan = generate_plan()
    for entry in plan["source_health"]:
        assert "observed_at" in entry
        observed = entry["observed_at"]
        assert isinstance(observed, str) and observed.endswith("Z")


def test_generate_plan_source_health_orders_required_first() -> None:
    from scripts.daily_etf_signal import generate_plan

    plan = generate_plan()
    ids = [entry["source_id"] for entry in plan["source_health"]]
    # etf_holdings is required → must come first.
    assert ids[0] == "etf_holdings"


def test_to_dict_as_of_uses_strict_z_suffix() -> None:
    """to_dict() must always render as_of with a ``Z`` UTC suffix (no ``+00:00``)."""
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    entries = build_source_registry(
        [
            {
                "source_id": "yahoo",
                "ok": True,
                "as_of": (now - timedelta(minutes=5)).isoformat(),
            }
        ],
        now=now,
    )
    payload = entries[0].to_dict()
    assert payload["as_of"] == "2026-05-14T11:55:00Z"
    assert "+00:00" not in payload["as_of"]


def test_to_dict_observed_at_uses_strict_z_suffix() -> None:
    """to_dict() must also render observed_at with a ``Z`` UTC suffix."""
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    entries = build_source_registry(
        [{"source_id": "yahoo", "ok": True}],
        now=now,
    )
    payload = entries[0].to_dict()
    assert payload["observed_at"] == "2026-05-14T12:00:00Z"
