"""Tests for industry runtime_helpers — pure data-transform helpers extracted from runtime.py."""

from types import SimpleNamespace

from backend.app.services.industry.runtime_helpers import (
    _build_parity_price_data,
    _coerce_trend_alignment_stock_rows,
    _count_quick_stock_detail_fields,
    _dedupe_leader_responses,
    _leader_detail_error_status,
)


def test_leader_detail_error_status_not_found_tokens():
    assert _leader_detail_error_status("Stock not found") == 404
    assert _leader_detail_error_status("data provider not set") == 404


def test_leader_detail_error_status_defaults_to_502():
    assert _leader_detail_error_status("") == 502
    assert _leader_detail_error_status("upstream gateway timeout") == 502


def test_build_parity_price_data_needs_two_points():
    assert _build_parity_price_data([]) == []
    assert _build_parity_price_data([1.0]) == []


def test_build_parity_price_data_shapes_points():
    result = _build_parity_price_data([1.0, 2.0, 3.0])
    assert len(result) >= 2
    for point in result:
        assert set(point) == {"date", "close", "volume"}


def test_count_quick_stock_detail_fields_returns_bounded_int():
    result = _count_quick_stock_detail_fields({"symbol": "000001", "name": "Foo"})
    assert isinstance(result, int)
    assert 0 <= result <= 4


def test_coerce_trend_alignment_stock_rows():
    rows = _coerce_trend_alignment_stock_rows([{"symbol": "000001", "name": "Foo"}])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "000001"
    assert rows[0]["code"] == "000001"
    assert rows[0]["name"] == "Foo"
    assert _coerce_trend_alignment_stock_rows([]) == []


def test_dedupe_leader_responses_keeps_higher_score():
    low = SimpleNamespace(symbol="000001", total_score=10, market_cap=100)
    high = SimpleNamespace(symbol="000001", total_score=20, market_cap=50)
    deduped = _dedupe_leader_responses([low, high])
    assert len(deduped) == 1
    assert deduped[0].total_score == 20
    assert deduped[0].global_rank == 1


def test_dedupe_leader_responses_drops_non_six_digit_symbols():
    valid = SimpleNamespace(symbol="000001", total_score=5, market_cap=10)
    invalid = SimpleNamespace(symbol="SPY", total_score=99, market_cap=10)
    deduped = _dedupe_leader_responses([valid, invalid])
    assert [leader.symbol for leader in deduped] == ["000001"]
