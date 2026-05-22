"""Tests for the strategy edge analytics (IC + hit rate from audit log)."""

from __future__ import annotations

from typing import Any

import pytest

from src.strategy.etf_rotation_analytics import (
    build_score_return_pairs,
    compute_hit_rate,
    compute_information_coefficient,
    compute_per_code_metrics,
    spearman_correlation,
    summarise_edge,
)


def _entry(
    run_at: str, *, scores: dict[str, float], prices: dict[str, float]
) -> dict[str, Any]:
    return {
        "run_at": run_at,
        "score_breakdown": {
            code: {"score": float(score)} for code, score in scores.items()
        },
        "prices_at_decision": {code: float(price) for code, price in prices.items()},
    }


# ---------------------------------------------------------------------------
# Spearman + IC math
# ---------------------------------------------------------------------------


def test_spearman_perfect_positive_correlation() -> None:
    xs = [1, 2, 3, 4, 5]
    ys = [10, 20, 30, 40, 50]
    assert spearman_correlation(xs, ys) == pytest.approx(1.0)


def test_spearman_perfect_negative_correlation() -> None:
    xs = [1, 2, 3, 4, 5]
    ys = [50, 40, 30, 20, 10]
    assert spearman_correlation(xs, ys) == pytest.approx(-1.0)


def test_spearman_handles_ties() -> None:
    xs = [1, 1, 2, 3]
    ys = [10, 10, 20, 30]
    assert spearman_correlation(xs, ys) == pytest.approx(1.0)


def test_spearman_returns_none_when_insufficient_points() -> None:
    assert spearman_correlation([1.0, 2.0], [3.0, 4.0]) is None
    assert spearman_correlation([], []) is None


# ---------------------------------------------------------------------------
# Forward-return joining
# ---------------------------------------------------------------------------


def test_build_score_return_pairs_joins_with_earliest_post_horizon_entry() -> None:
    entries: list[dict[str, Any]] = [
        _entry("2026-05-15T10:00:00+00:00",
               scores={"510300": 80.0, "159985": 30.0},
               prices={"510300": 5.00, "159985": 2.00}),
        _entry("2026-05-15T10:30:00+00:00",
               scores={"510300": 75.0, "159985": 32.0},
               prices={"510300": 5.05, "159985": 1.99}),
        _entry("2026-05-15T11:30:00+00:00",
               scores={"510300": 78.0, "159985": 28.0},
               prices={"510300": 5.10, "159985": 1.95}),
    ]
    # 60-minute horizon: T0 (10:00) → first match is 11:30 (>= 11:00)
    pairs = build_score_return_pairs(entries, horizon_minutes=60.0)
    by_code_t0 = [p for p in pairs if p["run_at"] == "2026-05-15T10:00:00+00:00"]
    assert {p["code"] for p in by_code_t0} == {"510300", "159985"}
    p_510300 = next(p for p in by_code_t0 if p["code"] == "510300")
    assert p_510300["forward_price"] == pytest.approx(5.10)
    assert p_510300["forward_return"] == pytest.approx(5.10 / 5.00 - 1.0)


def test_build_score_return_pairs_skips_codes_without_forward_price() -> None:
    entries = [
        _entry("2026-05-15T10:00:00+00:00",
               scores={"510300": 80.0, "159985": 30.0},
               prices={"510300": 5.00, "159985": 2.00}),
        # Later entry lacks 159985 price → 159985 pair is dropped, 510300 still paired
        _entry("2026-05-15T11:30:00+00:00",
               scores={"510300": 78.0},
               prices={"510300": 5.10}),
    ]
    pairs = build_score_return_pairs(entries, horizon_minutes=60.0)
    codes = {p["code"] for p in pairs}
    assert codes == {"510300"}


def test_build_score_return_pairs_drops_entries_before_horizon() -> None:
    entries = [
        _entry("2026-05-15T10:00:00+00:00", scores={"X": 50.0}, prices={"X": 5.0}),
        # Only 30 minutes later — under the 60-minute horizon → skipped
        _entry("2026-05-15T10:30:00+00:00", scores={"X": 55.0}, prices={"X": 5.10}),
    ]
    pairs = build_score_return_pairs(entries, horizon_minutes=60.0)
    assert pairs == []


def test_build_score_return_pairs_handles_unordered_input() -> None:
    """Input order must not matter; sort happens internally."""

    entries = [
        _entry("2026-05-15T11:30:00+00:00", scores={"X": 78.0}, prices={"X": 5.10}),
        _entry("2026-05-15T10:00:00+00:00", scores={"X": 80.0}, prices={"X": 5.00}),
    ]
    pairs = build_score_return_pairs(entries, horizon_minutes=60.0)
    assert len(pairs) == 1
    assert pairs[0]["run_at"] == "2026-05-15T10:00:00+00:00"
    assert pairs[0]["forward_return"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# IC + hit rate aggregates
# ---------------------------------------------------------------------------


def test_compute_information_coefficient_aligned_with_returns() -> None:
    pairs = [
        {"code": "A", "score": 80.0, "forward_return": 0.05},
        {"code": "A", "score": 70.0, "forward_return": 0.03},
        {"code": "A", "score": 50.0, "forward_return": 0.01},
        {"code": "A", "score": 30.0, "forward_return": -0.02},
        {"code": "A", "score": 20.0, "forward_return": -0.04},
    ]
    ic = compute_information_coefficient(pairs)
    assert ic is not None
    assert ic > 0.9  # near-perfect monotone alignment


def test_compute_hit_rate_with_neutral_score_50() -> None:
    pairs = [
        {"code": "A", "score": 80.0, "forward_return": 0.05},  # hit (bullish + up)
        {"code": "A", "score": 30.0, "forward_return": -0.02},  # hit (bearish + down)
        {"code": "A", "score": 70.0, "forward_return": -0.01},  # miss
        {"code": "A", "score": 40.0, "forward_return": 0.02},   # miss
    ]
    hit = compute_hit_rate(pairs)
    assert hit == pytest.approx(0.5)


def test_compute_per_code_metrics_splits_by_code() -> None:
    pairs = [
        {"code": "A", "score": 80.0, "forward_return": 0.05},
        {"code": "A", "score": 30.0, "forward_return": -0.02},
        {"code": "A", "score": 50.0, "forward_return": 0.00},
        {"code": "A", "score": 60.0, "forward_return": 0.01},
        {"code": "B", "score": 70.0, "forward_return": -0.05},
        {"code": "B", "score": 40.0, "forward_return": 0.04},
        {"code": "B", "score": 55.0, "forward_return": -0.01},
    ]
    per_code = compute_per_code_metrics(pairs)
    assert set(per_code) == {"A", "B"}
    assert per_code["A"]["n_pairs"] == 4
    assert per_code["B"]["n_pairs"] == 3
    # A's signal is monotone-aligned with returns → positive IC
    assert per_code["A"]["ic"] > 0
    # B's signal is inverted vs returns → negative IC
    assert per_code["B"]["ic"] < 0


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------


def test_summarise_edge_handles_empty_log() -> None:
    report = summarise_edge([])
    assert report["n_audit_entries"] == 0
    for horizon in report["horizons"].values():
        assert horizon["n_pairs"] == 0
        assert horizon["information_coefficient"] is None
        assert horizon["hit_rate"] is None


def test_summarise_edge_computes_three_default_horizons() -> None:
    entries = [
        _entry("2026-05-15T10:00:00+00:00",
               scores={"A": 80.0}, prices={"A": 5.00}),
        _entry("2026-05-15T11:00:00+00:00",
               scores={"A": 75.0}, prices={"A": 5.10}),  # +1h, +2%
        _entry("2026-05-15T14:00:00+00:00",
               scores={"A": 78.0}, prices={"A": 5.20}),  # +4h, +4%
        _entry("2026-05-16T10:00:00+00:00",
               scores={"A": 60.0}, prices={"A": 5.30}),  # +24h, +6%
    ]
    report = summarise_edge(entries)
    horizons = report["horizons"]
    assert "horizon_60min" in horizons
    assert "horizon_240min" in horizons
    assert "horizon_1440min" in horizons
    # 60-minute horizon should have at least one pair (T0 -> T1)
    assert horizons["horizon_60min"]["n_pairs"] >= 1


def test_summarise_edge_respects_custom_horizons() -> None:
    entries = [
        _entry("2026-05-15T10:00:00+00:00",
               scores={"A": 80.0}, prices={"A": 5.00}),
        _entry("2026-05-15T10:15:00+00:00",
               scores={"A": 75.0}, prices={"A": 5.05}),
    ]
    report = summarise_edge(entries, horizons_minutes=[10.0])
    assert "horizon_10min" in report["horizons"]
    assert report["horizons"]["horizon_10min"]["n_pairs"] == 1
