"""Tests for ``src.research.policy_factor_attribution``.

Strategy: build small synthetic audit logs + price matrices and assert the
attribution math sums the way the dataclass docstrings claim it should.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import pytest

from src.research.policy_factor_attribution import (
    AttributionReport,
    compute_attribution,
    render_markdown,
)

# ---------------------------------------------------------------------------
# Synthetic-data helpers
# ---------------------------------------------------------------------------


def _write_audit(path: Path, entries: list[dict[str, Any]]) -> Path:
    """Write a list of audit dicts as JSON-Lines."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    return path


def _entry(
    run_at: str,
    *,
    enabled: bool,
    adjusted_weights: Optional[dict[str, float]] = None,
    policy_adjustments: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build an audit row with the canonical shape.

    ``policy_adjustments`` maps code → dict that fills the per-ETF
    ``policy_adjustment`` block under ``score_breakdown[code]``.
    """

    weights = adjusted_weights or {}
    score_breakdown: dict[str, dict[str, Any]] = {}
    if policy_adjustments:
        for code, meta in policy_adjustments.items():
            score_breakdown[code] = {"policy_adjustment": dict(meta)}
    return {
        "run_at": run_at,
        "adjusted_weights": dict(weights),
        "target_weights": dict(weights),
        "score_breakdown": score_breakdown,
        "policy_signal_factor": {"enabled": enabled, "applied_count": len(policy_adjustments or {})},
    }


def _flat_prices(
    codes: list[str],
    start: str,
    end: str,
    *,
    daily_returns: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Build a price matrix where each ETF compounds daily by a fixed return."""

    daily_returns = daily_returns or {}
    idx = pd.date_range(start=start, end=end, freq="D")
    frames: dict[str, list[float]] = {}
    for code in codes:
        r = daily_returns.get(code, 0.0)
        frames[code] = [100.0 * ((1.0 + r) ** i) for i in range(len(idx))]
    return pd.DataFrame(frames, index=idx)


def _compounded_contribution_pct(report: AttributionReport) -> float:
    on_growth = 1.0
    off_growth = 1.0
    for row in report.per_rebalance_attribution:
        on_growth *= 1.0 + row.factor_on_return_pct / 100.0
        off_growth *= 1.0 + row.factor_off_return_pct / 100.0
    return (on_growth - off_growth) * 100.0


# ---------------------------------------------------------------------------
# Empty / disabled / missing data paths
# ---------------------------------------------------------------------------


def test_empty_audit_log_returns_zero_contribution(tmp_path: Path) -> None:
    """Missing file produces an empty AttributionReport, no exception."""

    nav = _flat_prices(["512400"], "2026-04-15", "2026-05-15")
    report = compute_attribution(tmp_path / "missing.jsonl", nav, period_days=30)
    assert isinstance(report, AttributionReport)
    assert report.n_rebalances == 0
    assert report.n_factor_on_rebalances == 0
    assert report.factor_contribution_pct == 0.0
    assert any("empty" in note.lower() for note in report.notes)


def test_audit_with_factor_off_only_returns_zero_contribution(tmp_path: Path) -> None:
    """Entries where ``enabled=False`` must produce zero contribution."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-15T02:00:00+00:00", enabled=False,
               adjusted_weights={"512400": 0.20, "515030": 0.20}),
    ])
    nav = _flat_prices(["512400", "515030"], "2026-04-15", "2026-05-20")
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.n_rebalances == 1
    assert report.n_factor_on_rebalances == 0
    assert report.factor_contribution_pct == 0.0


def test_audit_reader_skips_malformed_and_non_object_rows(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed and scalar/array JSONL rows should not poison attribution."""
    valid_row = _entry(
        "2026-05-10T02:00:00+00:00",
        enabled=True,
        adjusted_weights={"512400": 0.22},
        policy_adjustments={
            "512400": {
                "industry": "metals",
                "signal": "bullish",
                "multiplier": 1.10,
                "weight_before": 0.20,
                "weight_after": 0.22,
                "delta_weight": 0.02,
                "applied": True,
            },
        },
    )
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        "\n".join([
            "{malformed-json",
            json.dumps([]),
            json.dumps(42),
            json.dumps("x"),
            json.dumps(valid_row, ensure_ascii=False, sort_keys=True),
        ]) + "\n",
        encoding="utf-8",
    )
    nav = _flat_prices(["512400"], "2026-05-10", "2026-05-16",
                        daily_returns={"512400": 0.01})

    with caplog.at_level(logging.WARNING, logger="src.research.policy_factor_attribution"):
        report = compute_attribution(
            audit_path, nav, period_days=30,
            now=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )

    assert report.n_rebalances == 1
    assert report.n_factor_on_rebalances == 1
    assert report.per_rebalance_attribution[0].applied_codes == ["512400"]
    warning_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Skipping malformed audit line" in warning_text
    assert "Skipping non-object audit line" in warning_text


def test_non_finite_audit_numbers_do_not_poison_report(tmp_path: Path) -> None:
    """NaN/Infinity audit weights are ignored instead of bubbling into totals."""
    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry(
            "2026-05-10T02:00:00+00:00",
            enabled=True,
            adjusted_weights={"512400": float("nan"), "515030": 0.18},
            policy_adjustments={
                "512400": {
                    "industry": "metals",
                    "signal": "bullish",
                    "multiplier": 1.10,
                    "weight_before": 0.20,
                    "weight_after": 0.22,
                    "delta_weight": 0.02,
                    "applied": True,
                },
                "515030": {
                    "industry": "新能源汽车",
                    "signal": "bearish",
                    "multiplier": 0.90,
                    "weight_before": 0.20,
                    "weight_after": 0.18,
                    "delta_weight": -0.02,
                    "applied": True,
                },
            },
        ),
    ])
    nav = _flat_prices(
        ["512400", "515030"],
        "2026-05-10",
        "2026-05-16",
        daily_returns={"512400": 0.01, "515030": -0.01},
    )

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )

    assert report.n_factor_on_rebalances == 1
    assert report.per_rebalance_attribution[0].applied_codes == ["515030"]
    assert report.per_rebalance_attribution[0].per_code_contribution_pct.keys() == {"515030"}
    for value in (
        report.factor_on_return_pct,
        report.factor_off_return_pct,
        report.factor_contribution_pct,
        report.per_rebalance_attribution[0].factor_on_return_pct,
        report.per_rebalance_attribution[0].factor_off_return_pct,
        report.per_rebalance_attribution[0].factor_contribution_pct,
    ):
        assert math.isfinite(value)


def test_integer_price_matrix_keeps_valid_attribution(tmp_path: Path) -> None:
    """Valid pandas/numpy numeric scalars from integer price matrices must work."""
    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry(
            "2026-05-10T02:00:00+00:00",
            enabled=True,
            adjusted_weights={"512400": 0.22},
            policy_adjustments={
                "512400": {
                    "industry": "metals",
                    "signal": "bullish",
                    "multiplier": 1.10,
                    "weight_before": 0.20,
                    "weight_after": 0.22,
                    "delta_weight": 0.02,
                    "applied": True,
                },
            },
        ),
    ])
    nav = pd.DataFrame(
        {"512400": [100, 110]},
        index=pd.to_datetime(["2026-05-10", "2026-05-16"]),
    )

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )

    assert report.factor_on_return_pct == pytest.approx(2.2)
    assert report.factor_off_return_pct == pytest.approx(2.0)
    assert report.factor_contribution_pct == pytest.approx(0.2)


def test_non_finite_price_endpoints_do_not_poison_per_code_rows(tmp_path: Path) -> None:
    """NaN/Infinity prices should not leak into per-code attribution values."""
    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry(
            "2026-05-10T02:00:00+00:00",
            enabled=True,
            adjusted_weights={"512400": 0.22},
            policy_adjustments={
                "512400": {
                    "industry": "metals",
                    "signal": "bullish",
                    "multiplier": 1.10,
                    "weight_before": 0.20,
                    "weight_after": 0.22,
                    "delta_weight": 0.02,
                    "applied": True,
                },
            },
        ),
    ])
    nav = pd.DataFrame(
        {"512400": [100.0, float("inf")]},
        index=pd.to_datetime(["2026-05-10", "2026-05-16"]),
    )

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )

    row = report.per_rebalance_attribution[0]
    assert row.factor_on_return_pct == 0.0
    assert row.factor_off_return_pct == 0.0
    assert row.factor_contribution_pct == 0.0
    assert row.per_code_contribution_pct["512400"] == 0.0


def test_applied_code_missing_from_price_matrix_is_zeroed(tmp_path: Path) -> None:
    """Missing price columns for applied codes should not crash attribution."""
    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry(
            "2026-05-10T02:00:00+00:00",
            enabled=True,
            adjusted_weights={"512400": 0.22},
            policy_adjustments={
                "512400": {
                    "industry": "metals",
                    "signal": "bullish",
                    "multiplier": 1.10,
                    "weight_before": 0.20,
                    "weight_after": 0.22,
                    "delta_weight": 0.02,
                    "applied": True,
                },
            },
        ),
    ])
    nav = pd.DataFrame(
        {"515030": [100.0, 101.0]},
        index=pd.to_datetime(["2026-05-10", "2026-05-16"]),
    )

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )

    row = report.per_rebalance_attribution[0]
    assert row.factor_on_return_pct == 0.0
    assert row.factor_off_return_pct == 0.0
    assert row.factor_contribution_pct == 0.0
    assert row.per_code_contribution_pct["512400"] == 0.0


# ---------------------------------------------------------------------------
# Single-rebalance attribution sign / magnitude
# ---------------------------------------------------------------------------


def test_bullish_boost_on_rising_etf_adds_contribution(tmp_path: Path) -> None:
    """A bullish boost on a rising ETF must produce a positive contribution.

    Universe: just ``512400`` boosted from 0.20 → 0.22 (+10%). Price rises
    1%/day for 5 days → on-leg gets 0.22 * 5%, off-leg 0.20 * 5%.
    Contribution ≈ 0.02 * (1.01**5 - 1) ≈ 0.10%.
    """

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "industry": "metals",
                       "signal": "bullish",
                       "multiplier": 1.10,
                       "weight_before": 0.20,
                       "weight_after": 0.22,
                       "delta_weight": 0.02,
                       "applied": True,
                   },
               }),
    ])
    nav = _flat_prices(["512400"], "2026-05-10", "2026-05-16",
                        daily_returns={"512400": 0.01})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.n_factor_on_rebalances == 1
    assert report.factor_contribution_pct > 0
    # Expected to a few decimal places: 0.02 * (1.01**6 - 1) ≈ 0.123% (6 bar = 6 entries between 5/10 and 5/16)
    # We assert a permissive band so the test stays robust to bar-count details.
    assert 0.05 < report.factor_contribution_pct < 0.25
    assert "512400" in report.per_rebalance_attribution[0].applied_codes


def test_bearish_penalty_on_falling_etf_adds_contribution(tmp_path: Path) -> None:
    """Penalising a *falling* ETF saves money → positive contribution."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"515030": 0.18},
               policy_adjustments={
                   "515030": {
                       "industry": "新能源汽车",
                       "signal": "bearish",
                       "multiplier": 0.90,
                       "weight_before": 0.20,
                       "weight_after": 0.18,
                       "delta_weight": -0.02,
                       "applied": True,
                   },
               }),
    ])
    nav = _flat_prices(["515030"], "2026-05-10", "2026-05-16",
                        daily_returns={"515030": -0.01})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.factor_contribution_pct > 0
    assert report.per_rebalance_attribution[0].applied_codes == ["515030"]


def test_bullish_boost_on_falling_etf_subtracts_contribution(tmp_path: Path) -> None:
    """Boosting a *falling* ETF loses money → negative contribution."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "industry": "metals",
                       "signal": "bullish",
                       "multiplier": 1.10,
                       "weight_before": 0.20,
                       "weight_after": 0.22,
                       "delta_weight": 0.02,
                       "applied": True,
                   },
               }),
    ])
    nav = _flat_prices(["512400"], "2026-05-10", "2026-05-16",
                        daily_returns={"512400": -0.01})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.factor_contribution_pct < 0


def test_post_overlay_counterfactual_scales_final_weight_proportionally(
    tmp_path: Path,
) -> None:
    """If final overlays halve the on-weight, the off-leg should be halved too."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.11},
               policy_adjustments={
                   "512400": {
                       "industry": "metals",
                       "signal": "bullish",
                       "multiplier": 1.10,
                       "weight_before": 0.20,
                       "weight_after": 0.22,
                       "delta_weight": 0.02,
                       "applied": True,
                   },
               }),
    ])
    nav = _flat_prices(["512400"], "2026-05-10", "2026-05-11",
                        daily_returns={"512400": 0.10})

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert report.factor_contribution_pct == pytest.approx(0.1, abs=1e-4)
    assert report.per_rebalance_attribution[0].factor_on_return_pct == pytest.approx(1.1)
    assert report.per_rebalance_attribution[0].factor_off_return_pct == pytest.approx(1.0)


def test_daily_price_slice_includes_rebalance_date_close(tmp_path: Path) -> None:
    """A 02:00 audit timestamp should still include that calendar date's close."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "industry": "metals",
                       "signal": "bullish",
                       "multiplier": 1.10,
                       "weight_before": 0.20,
                       "weight_after": 0.22,
                       "delta_weight": 0.02,
                       "applied": True,
                   },
               }),
    ])
    nav = pd.DataFrame(
        {"512400": [100.0, 110.0]},
        index=pd.date_range(start="2026-05-10", periods=2, freq="D"),
    )

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert len(report.per_rebalance_attribution) == 1
    assert report.factor_contribution_pct == pytest.approx(0.2, abs=1e-4)


# ---------------------------------------------------------------------------
# Aggregation across multiple rebalances
# ---------------------------------------------------------------------------


def test_multiple_rebalances_aggregate_correctly(tmp_path: Path) -> None:
    """Three rebalances compound into the aggregate contribution."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-04-25T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "weight_before": 0.20, "weight_after": 0.22,
                       "multiplier": 1.10, "signal": "bullish",
                       "delta_weight": 0.02, "applied": True,
                       "industry": "metals",
                   },
               }),
        _entry("2026-05-05T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "weight_before": 0.20, "weight_after": 0.22,
                       "multiplier": 1.10, "signal": "bullish",
                       "delta_weight": 0.02, "applied": True,
                       "industry": "metals",
                   },
               }),
        _entry("2026-05-12T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {
                       "weight_before": 0.20, "weight_after": 0.22,
                       "multiplier": 1.10, "signal": "bullish",
                       "delta_weight": 0.02, "applied": True,
                       "industry": "metals",
                   },
               }),
    ])
    nav = _flat_prices(["512400"], "2026-04-20", "2026-05-16",
                        daily_returns={"512400": 0.01})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.n_factor_on_rebalances == 3
    assert len(report.per_rebalance_attribution) == 3
    expected = _compounded_contribution_pct(report)
    assert report.factor_contribution_pct == pytest.approx(expected, abs=1e-4)


def test_per_rebalance_breakdown_compounds_to_total(tmp_path: Path) -> None:
    """Invariant: aggregate contribution == compounded per-rebalance legs."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-01T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22, "515030": 0.18},
               policy_adjustments={
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
                   "515030": {"weight_before": 0.20, "weight_after": 0.18,
                              "multiplier": 0.90, "signal": "bearish",
                              "delta_weight": -0.02, "applied": True,
                              "industry": "新能源汽车"},
               }),
        _entry("2026-05-08T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22, "515030": 0.18},
               policy_adjustments={
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
                   "515030": {"weight_before": 0.20, "weight_after": 0.18,
                              "multiplier": 0.90, "signal": "bearish",
                              "delta_weight": -0.02, "applied": True,
                              "industry": "新能源汽车"},
               }),
    ])
    nav = _flat_prices(["512400", "515030"], "2026-04-20", "2026-05-16",
                        daily_returns={"512400": 0.005, "515030": -0.005})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    expected = _compounded_contribution_pct(report)
    assert report.factor_contribution_pct == pytest.approx(expected, abs=1e-4)


def test_hit_rate_computed_correctly(tmp_path: Path) -> None:
    """3 rebalances: 2 wins, 1 loss → hit rate = 66.67%."""

    audit_path = tmp_path / "audit.jsonl"

    def make_row(date: str, return_during_hold: float) -> dict[str, Any]:
        return _entry(date, enabled=True,
                      adjusted_weights={"512400": 0.22},
                      policy_adjustments={
                          "512400": {
                              "weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals",
                          },
                      })

    _write_audit(audit_path, [
        make_row("2026-04-23T02:00:00+00:00", +0.01),
        make_row("2026-04-30T02:00:00+00:00", +0.01),
        make_row("2026-05-07T02:00:00+00:00", -0.01),
    ])

    # Build a price series where the first two windows rise and the last falls.
    idx = pd.date_range(start="2026-04-20", end="2026-05-16", freq="D")
    prices: list[float] = []
    base = 100.0
    for d in idx:
        # Up before May 7, down after.
        if d < pd.Timestamp("2026-05-07"):
            base *= 1.005
        else:
            base *= 0.995
        prices.append(base)
    nav = pd.DataFrame({"512400": prices}, index=idx)

    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.n_factor_on_rebalances == 3
    # 2 of 3 rebalances should be positive contribution.
    positives = sum(
        1 for row in report.per_rebalance_attribution
        if row.factor_contribution_pct > 0
    )
    assert positives == 2
    assert report.hit_rate_pct == pytest.approx(2 / 3 * 100, abs=0.1)


def test_top_winner_and_loser_etfs_identified(tmp_path: Path) -> None:
    """Per-code aggregation surfaces the right winners and losers.

    Two rebalances:
      * 512400 boosted on a rising ETF → positive per-code contribution.
      * 515030 boosted on a falling ETF → negative per-code contribution.
    """

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-03T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   # Bullish boost on RISING 512400 → wins.
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
               }),
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"515030": 0.22},
               policy_adjustments={
                   # Bullish boost on FALLING 515030 → loses.
                   "515030": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "新能源汽车"},
               }),
    ])
    nav = _flat_prices(["512400", "515030"], "2026-05-01", "2026-05-16",
                        daily_returns={"512400": 0.01, "515030": -0.01})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    winner_codes = [winner["code"] for winner in report.top_winner_etfs]
    loser_codes = [loser["code"] for loser in report.top_loser_etfs]
    assert "512400" in winner_codes
    assert "515030" in loser_codes


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_factor_toggles_between_consecutive_rebalances(tmp_path: Path) -> None:
    """When some rows are factor-off they're skipped in the attribution loop."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-05T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
               }),
        _entry("2026-05-08T02:00:00+00:00", enabled=False,
               adjusted_weights={"512400": 0.20}),
        _entry("2026-05-12T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
               }),
    ])
    nav = _flat_prices(["512400"], "2026-04-20", "2026-05-20",
                        daily_returns={"512400": 0.005})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert report.n_rebalances == 3
    # Only the two enabled rows feed the math.
    assert report.n_factor_on_rebalances == 2
    assert len(report.per_rebalance_attribution) == 2
    assert report.per_rebalance_attribution[0].period_end.startswith("2026-05-08")


def test_render_markdown_includes_key_sections(tmp_path: Path) -> None:
    """Smoke-test the markdown renderer; no NaN tokens, expected headings."""

    audit_path = tmp_path / "audit.jsonl"
    _write_audit(audit_path, [
        _entry("2026-05-10T02:00:00+00:00", enabled=True,
               adjusted_weights={"512400": 0.22},
               policy_adjustments={
                   "512400": {"weight_before": 0.20, "weight_after": 0.22,
                              "multiplier": 1.10, "signal": "bullish",
                              "delta_weight": 0.02, "applied": True,
                              "industry": "metals"},
               }),
    ])
    nav = _flat_prices(["512400"], "2026-05-10", "2026-05-16",
                        daily_returns={"512400": 0.005})
    report = compute_attribution(
        audit_path, nav, period_days=30,
        now=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    md = render_markdown(report)
    assert "# Policy Signal Factor — Attribution Report" in md
    assert "Factor contribution" in md
    assert "Per-rebalance breakdown" in md
    assert "nan" not in md.lower()
