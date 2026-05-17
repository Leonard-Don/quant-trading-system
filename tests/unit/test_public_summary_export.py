"""Tests for ``scripts/export_public_summary.py`` (Phase F1).

The exporter distills runtime caches into a small, committable JSON that
sibling project ``cn-altdata-brief`` consumes. These tests verify:

- The full schema shape (every required top-level key present)
- Provider absence is graceful (no synthetic data is invented)
- The atomic-write path doesn't leave a partial file on disk
- Sensitive runtime data (file paths, cash, holdings, RSS bodies) never
  appears in the output
- The output stays well under the 50 KB budget
- The schema version is stable (regressions force an intentional bump)
- The exporter is deterministic given identical input
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts import export_public_summary

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_providers_dir(tmp_path: Path) -> Path:
    """A minimal policy_radar snapshot covering three industries."""
    providers_dir = tmp_path / "providers"
    providers_dir.mkdir()
    policy_radar = {
        "provider": "policy_radar",
        "signal": {
            "timestamp": "2026-05-17T10:29:47.063347",
            "record_count": 10,
            "policy_count": 10,
            "industry_signals": {
                "新能源汽车": {
                    "avg_impact": -0.32,
                    "mentions": 119,
                    "signal": "bearish",
                },
                "电网": {"avg_impact": 0.0, "mentions": 6, "signal": "neutral"},
                "风电": {"avg_impact": 0.05, "mentions": 3, "signal": "bullish"},
            },
            "source_health": {"fed": {"record_count": 5}},
        },
        "records": [
            # Sensitive details — should NEVER leak into the public summary.
            {
                "raw_value": {
                    "title": "private policy text",
                    "excerpt": "internal RSS body that must not leak",
                },
                "metadata": {
                    "link": "https://internal.example.com/secret",
                    "detail_url": "/Users/leonardodon/secret/path.html",
                },
            }
        ],
    }
    (providers_dir / "policy_radar.json").write_text(
        json.dumps(policy_radar, ensure_ascii=False), encoding="utf-8"
    )
    return providers_dir


@pytest.fixture()
def sample_heatmap_history(tmp_path: Path) -> Path:
    """An industry heatmap history file with two snapshots."""
    history = [
        {
            "snapshot_id": "5:2026-04-20",
            "days": 5,
            "captured_at": "2026-05-15T09:22:57",
            "industries": [
                {"name": "old_industry", "value": 1.0, "total_score": 50.0, "stockCount": 5},
            ],
        },
        {
            "snapshot_id": "5:2026-05-17",
            "days": 5,
            "captured_at": "2026-05-17T09:22:57",
            "industries": [
                {
                    "name": "新能源汽车",
                    "value": 2.5,
                    "total_score": 88.0,
                    "stockCount": 42,
                },
                {
                    "name": "白酒",
                    "value": 1.67,
                    "total_score": 92.5,
                    "stockCount": 18,
                },
                {
                    "name": "电网",
                    "value": -0.5,
                    "total_score": 60.1,
                    "stockCount": 12,
                },
            ],
        },
    ]
    path = tmp_path / "heatmap_history.json"
    path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def sample_paper_trading_dir(tmp_path: Path) -> Path:
    """A paper trading profile directory with two profile files. The cash
    / positions inside the file should NEVER be exposed by the exporter."""
    profiles_dir = tmp_path / "paper_trading"
    profiles_dir.mkdir()
    (profiles_dir / "default.json").write_text(
        json.dumps(
            {
                "initial_capital": 1_000_000.0,
                "cash": 999_888.50,
                "positions": {"600519": {"qty": 50, "cost": 1800.0}},
                "orders": [],
            }
        ),
        encoding="utf-8",
    )
    (profiles_dir / "growth.json").write_text(json.dumps({"cash": 50_000.0}), encoding="utf-8")
    return profiles_dir


@pytest.fixture()
def sample_audit_log(tmp_path: Path) -> Path:
    """A minimal audit log file with three lines, last one carrying timestamps."""
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps({"run_at": "2026-05-15T10:00:00+00:00", "weights": {"x": 1}}),
                json.dumps({"run_at": "2026-05-16T10:00:00+00:00", "weights": {"x": 1}}),
                json.dumps(
                    {
                        "run_at": "2026-05-17T10:00:00+00:00",
                        "recorded_at": "2026-05-17T10:00:05+00:00",
                        # Sensitive payload that must NOT appear in the summary.
                        "adjusted_weights": {"159985": 0.5, "510300": 0.5},
                        "prices_at_decision": {"159985": 2.0, "510300": 4.9},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return audit_path


@pytest.fixture()
def sample_backtest_price_csv(tmp_path: Path) -> Path:
    """A small deterministic price matrix for regime recommendation export."""
    path = tmp_path / "etf_prices.csv"
    start = date(2026, 1, 2)
    rows = ["date,510300,512400,159915"]
    for idx in range(120):
        current = start + timedelta(days=idx)
        rows.append(
            ",".join(
                [
                    current.isoformat(),
                    f"{10.0 * (1.0015 ** idx):.6f}",
                    f"{5.0 * (1.0010 ** idx):.6f}",
                    f"{3.0 * (1.0008 ** idx):.6f}",
                ]
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def empty_audit_log(tmp_path: Path) -> Path:
    """A path that doesn't exist — the audit-log absent branch."""
    return tmp_path / "no-audit.jsonl"


@pytest.fixture()
def full_payload(
    sample_providers_dir: Path,
    sample_heatmap_history: Path,
    sample_paper_trading_dir: Path,
    sample_audit_log: Path,
    sample_backtest_price_csv: Path,
    tmp_path: Path,
) -> dict[str, Any]:
    """The full payload built against the rich-input fixture set."""
    version_path = tmp_path / "VERSION"
    version_path.write_text("9.9.9", encoding="utf-8")
    return export_public_summary.build_public_summary(
        sample_providers_dir,
        version_path=version_path,
        heatmap_history_path=sample_heatmap_history,
        paper_trading_dir=sample_paper_trading_dir,
        audit_log_path=sample_audit_log,
        backtest_price_csv_path=sample_backtest_price_csv,
        generated_at="2026-05-17T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_schema_required_keys_present(full_payload: dict[str, Any]) -> None:
    """Every top-level section the consumer relies on must be present."""
    required = {
        "schema_version",
        "generated_at",
        "source_codebase_version",
        "policy_radar",
        "industry_heat",
        "etf_rotation",
        "paper_trading",
    }
    assert required.issubset(full_payload.keys()), (
        f"missing keys: {required - full_payload.keys()}"
    )
    assert full_payload["schema_version"] == export_public_summary.SCHEMA_VERSION
    assert full_payload["source_codebase_version"] == "9.9.9"


def test_policy_radar_top_industries_sorted_and_capped(
    full_payload: dict[str, Any],
) -> None:
    """top_industries: sorted by |avg_impact| desc, capped at MAX_POLICY_INDUSTRIES."""
    rows = full_payload["policy_radar"]["top_industries"]
    assert len(rows) <= export_public_summary.MAX_POLICY_INDUSTRIES
    impacts = [abs(r["avg_impact"]) for r in rows]
    assert impacts == sorted(impacts, reverse=True), "not sorted by |avg_impact|"
    # Each row has only the safe fields — no excerpt / link / RSS body.
    for row in rows:
        assert set(row.keys()) == {"avg_impact", "industry", "mentions", "signal"}
    assert full_payload["policy_radar"]["total_records"] == 10


def test_industry_heat_enriches_with_policy_signal(full_payload: dict[str, Any]) -> None:
    """Industries that overlap policy_radar.top_industries get policy_signal inlined."""
    heat = full_payload["industry_heat"]["top_industries_by_score"]
    by_name = {row["industry_name"]: row for row in heat}
    # 新能源汽车 is in both blocks → enriched.
    nev = by_name.get("新能源汽车")
    assert nev is not None
    assert "policy_signal" in nev
    assert nev["policy_signal"]["signal"] == "bearish"
    # 白酒 has no policy_radar coverage → no policy_signal key.
    baijiu = by_name.get("白酒")
    assert baijiu is not None
    assert "policy_signal" not in baijiu


def test_paper_trading_lists_profile_names_only(
    full_payload: dict[str, Any],
) -> None:
    """active_profiles: just names, no cash/positions leak."""
    pt = full_payload["paper_trading"]
    assert set(pt["active_profiles"]) == {"default", "growth"}
    assert pt["available"] is True
    assert pt["profile_count"] == 2
    # The serialized payload must NOT contain any of the sensitive numbers.
    serialized = json.dumps(full_payload, ensure_ascii=False)
    assert "999888.5" not in serialized
    assert "1000000.0" not in serialized
    assert "600519" not in serialized


def test_etf_rotation_audit_metadata_only_no_weights(
    full_payload: dict[str, Any],
) -> None:
    """latest_audit_at + count surface; weights / prices stay private."""
    etf = full_payload["etf_rotation"]
    assert etf["latest_audit_log_entry_count"] == 3
    assert etf["latest_audit_at"] == "2026-05-17T10:00:05+00:00"
    assert etf["latest_audit_run_at"] == "2026-05-17T10:00:00+00:00"
    assert etf["policy_signal_factor_enabled_default"] is False
    assert etf["config_default_universe_size"] >= 5
    assert etf["available_strategies_count"] > 0
    serialized = json.dumps(full_payload, ensure_ascii=False)
    # Sensitive audit body must not leak into the summary.
    assert "adjusted_weights" not in serialized
    assert "prices_at_decision" not in serialized


def test_etf_rotation_regime_recommendation_exported_without_raw_prices(
    full_payload: dict[str, Any],
) -> None:
    """Public summary includes the R1 regime recommendation, not raw price rows."""
    rec = full_payload["etf_rotation"]["regime_recommendation"]
    assert rec["available"] is True
    assert rec["lookback_days"] == 90
    assert rec["regime_name"] in {
        "trending_low_vol",
        "trending_high_vol",
        "choppy_low_vol",
        "choppy_high_vol",
        "bear_high_vol",
        "bear_low_vol",
        "unknown",
    }
    assert rec["recommended_strategy"] in {
        "rotation",
        "mean_reversion",
        "blend",
        "cash",
        "unchanged",
    }
    assert 0.0 <= rec["confidence"] <= 1.0
    assert rec["n_assets_used"] == 3
    assert set(rec["features"]) == {
        "trend_r2",
        "trend_slope",
        "realized_vol",
        "return_skew",
        "drawdown_ratio",
        "avg_pairwise_correlation",
    }
    serialized = json.dumps(rec, ensure_ascii=False)
    assert "510300" not in serialized
    assert "etf_prices" not in serialized


def test_missing_regime_price_matrix_reports_reason_without_path(
    full_payload: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Missing price CSV should degrade gracefully and avoid local path leakage."""
    rec = export_public_summary._build_regime_recommendation_section(
        tmp_path / "missing.csv"
    )
    assert rec == {
        "available": False,
        "lookback_days": 90,
        "unavailable_reason": "price_matrix_missing",
    }
    assert str(tmp_path) not in json.dumps(rec, ensure_ascii=False)


def test_missing_provider_key_absent_no_synthetic_data(
    tmp_path: Path,
    sample_heatmap_history: Path,
    sample_paper_trading_dir: Path,
    empty_audit_log: Path,
) -> None:
    """When policy_radar.json is missing the key is absent — no fake fallback."""
    empty_providers = tmp_path / "empty_providers"
    empty_providers.mkdir()
    payload = export_public_summary.build_public_summary(
        empty_providers,
        version_path=tmp_path / "no-version",
        heatmap_history_path=sample_heatmap_history,
        paper_trading_dir=sample_paper_trading_dir,
        audit_log_path=empty_audit_log,
        generated_at="2026-05-17T00:00:00+00:00",
    )
    assert "policy_radar" not in payload, "policy_radar must not be invented"
    # Industry heat survives because its source file exists.
    assert "industry_heat" in payload
    # But no industry should carry policy_signal — there's no policy_radar.
    for row in payload["industry_heat"]["top_industries_by_score"]:
        assert "policy_signal" not in row
    # ETF rotation block is always present; latest_audit_* are null when
    # the log is missing.
    assert payload["etf_rotation"]["latest_audit_log_entry_count"] == 0
    assert payload["etf_rotation"]["latest_audit_at"] is None
    assert payload["etf_rotation"]["latest_audit_run_at"] is None


def test_missing_industry_heatmap_history_drops_section(
    tmp_path: Path,
    sample_providers_dir: Path,
    sample_paper_trading_dir: Path,
    empty_audit_log: Path,
) -> None:
    """When heatmap_history.json is missing, industry_heat is omitted entirely."""
    payload = export_public_summary.build_public_summary(
        sample_providers_dir,
        version_path=tmp_path / "no-version",
        heatmap_history_path=tmp_path / "no-heatmap.json",
        paper_trading_dir=sample_paper_trading_dir,
        audit_log_path=empty_audit_log,
        generated_at="2026-05-17T00:00:00+00:00",
    )
    assert "industry_heat" not in payload
    # policy_radar still made it through.
    assert "policy_radar" in payload


def test_atomic_write_no_partial_file(
    tmp_path: Path,
    full_payload: dict[str, Any],
) -> None:
    """Atomic-write: temp file is removed on success; no stale .tmp."""
    output_path = tmp_path / "out" / "quant_summary.json"
    export_public_summary.write_public_summary_atomic(full_payload, output_path)
    assert output_path.exists()
    # No leftover temp files in the destination directory.
    leftover = list(output_path.parent.glob("*.tmp"))
    assert leftover == [], f"atomic write left tempfiles: {leftover}"
    # Round-trip OK.
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded == full_payload


def test_size_budget_under_50kb(full_payload: dict[str, Any]) -> None:
    """The serialized payload must stay well under 50 KB."""
    serialized = json.dumps(full_payload, ensure_ascii=False, indent=2, sort_keys=True)
    assert len(serialized.encode("utf-8")) < 50 * 1024, (
        f"payload too large: {len(serialized.encode('utf-8'))} bytes"
    )


def test_schema_version_locked_to_one() -> None:
    """A change to SCHEMA_VERSION is a breaking change — force conscious bump."""
    assert export_public_summary.SCHEMA_VERSION == 1


def test_export_is_deterministic_for_fixed_generated_at(
    sample_providers_dir: Path,
    sample_heatmap_history: Path,
    sample_paper_trading_dir: Path,
    sample_audit_log: Path,
    sample_backtest_price_csv: Path,
    tmp_path: Path,
) -> None:
    """Same input + same generated_at → byte-identical output."""
    version_path = tmp_path / "VERSION"
    version_path.write_text("5.0.0", encoding="utf-8")
    first = export_public_summary.build_public_summary(
        sample_providers_dir,
        version_path=version_path,
        heatmap_history_path=sample_heatmap_history,
        paper_trading_dir=sample_paper_trading_dir,
        audit_log_path=sample_audit_log,
        backtest_price_csv_path=sample_backtest_price_csv,
        generated_at="2026-05-17T00:00:00+00:00",
    )
    second = export_public_summary.build_public_summary(
        sample_providers_dir,
        version_path=version_path,
        heatmap_history_path=sample_heatmap_history,
        paper_trading_dir=sample_paper_trading_dir,
        audit_log_path=sample_audit_log,
        backtest_price_csv_path=sample_backtest_price_csv,
        generated_at="2026-05-17T00:00:00+00:00",
    )
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_sensitive_internal_fields_excluded(full_payload: dict[str, Any]) -> None:
    """Spot-check that internal cache strings never appear in the serialized output."""
    serialized = json.dumps(full_payload, ensure_ascii=False)
    forbidden = [
        "internal RSS body",
        "secret/path",
        "internal.example.com",
        "private policy text",
        "/Users/",  # No absolute filesystem paths.
        "source_health",  # Internal aggregation key — omitted.
    ]
    for needle in forbidden:
        assert needle not in serialized, f"sensitive token leaked: {needle!r}"
