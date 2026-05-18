"""Tests for the manual ETF execution tracker data layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.strategy.etf_execution_tracker import (
    ExecutionRecord,
    append_execution,
    compare_execution_to_suggestion,
    compute_decision_breakdown,
    read_executions,
)


def _record(
    code: str = "510300",
    *,
    decision: str = "executed",
    action: str = "buy",
    shares: int = 100,
    plan_run_at: str = "2026-05-18T10:00:00+00:00",
    suggested_action: str = "buy",
    suggested_shares: int = 100,
) -> ExecutionRecord:
    return ExecutionRecord(
        code=code,
        decision=decision,
        action=action,
        shares=shares,
        plan_run_at=plan_run_at,
        recorded_at="2026-05-18T10:02:00+00:00",
        suggested_action=suggested_action,
        suggested_shares=suggested_shares,
        actual_fill_price=5.01,
        note="manual test fill",
    )


def _audit_entry(run_at: str, prices: dict[str, object]) -> dict[str, object]:
    return {"run_at": run_at, "prices_at_decision": prices}


def test_append_and_read_executions_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "executions.jsonl"
    record = _record()

    written = append_execution(record, path=path)
    loaded = read_executions(path)

    assert written == path
    assert len(loaded) == 1
    assert loaded[0] == record

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    assert json.loads(raw_lines[0])["code"] == "510300"


def test_read_executions_skips_malformed_and_invalid_rows(tmp_path: Path) -> None:
    path = tmp_path / "executions.jsonl"
    good = _record(code="159985").to_dict()
    missing_code = {**good}
    missing_code.pop("code")
    bad_shares = {**good, "code": "510300", "shares": "not-a-number"}
    bad_suggested_shares = {
        **good,
        "code": "512400",
        "suggested_shares": "not-a-number",
    }
    bad_fill_price = {
        **good,
        "code": "588000",
        "actual_fill_price": "not-a-price",
    }
    bad_decision = {**good, "code": "BAD_DECISION", "decision": "ignored"}
    bad_action = {**good, "code": "BAD_ACTION", "action": "rebalance"}
    bad_suggested_action = {
        **good,
        "code": "BAD_SUGGESTED_ACTION",
        "suggested_action": "rebalance",
    }
    path.write_text(
        "\n".join(
            [
                json.dumps(good),
                "not-json",
                json.dumps(missing_code),
                json.dumps(bad_shares),
                json.dumps(bad_suggested_shares),
                json.dumps(bad_fill_price),
                json.dumps(bad_decision),
                json.dumps(bad_action),
                json.dumps(bad_suggested_action),
            ]
        ),
        encoding="utf-8",
    )

    loaded = read_executions(path)

    assert [record.code for record in loaded] == ["159985"]


def test_append_execution_swallows_write_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> object:
        raise OSError("disk is read-only")

    monkeypatch.setattr(Path, "open", _raise_os_error)

    assert append_execution(_record(), path=Path("/tmp/executions.jsonl")) is None


def test_decision_breakdown_counts_decisions_and_codes() -> None:
    records = [
        _record(code="510300", decision="executed"),
        _record(code="510300", decision="modified"),
        _record(code="512400", decision="skipped", action="hold", shares=0),
        _record(code="512400", decision="skipped", action="hold", shares=0),
    ]

    breakdown = compute_decision_breakdown(records)

    assert breakdown["total"] == 4
    assert breakdown["by_decision"] == {"executed": 1, "modified": 1, "skipped": 2}
    assert breakdown["by_code"]["510300"] == {
        "executed": 1,
        "modified": 1,
        "skipped": 0,
    }
    assert breakdown["by_code"]["512400"] == {
        "executed": 0,
        "modified": 0,
        "skipped": 2,
    }
    assert breakdown["follow_rate"] == pytest.approx(0.25)
    assert breakdown["override_rate"] == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "ignored"),
        ("action", "rebalance"),
        ("suggested_action", "rebalance"),
    ],
)
def test_execution_record_rejects_unknown_decision_or_actions(
    field: str,
    value: str,
) -> None:
    kwargs = {field: value}

    with pytest.raises(ValueError, match=field):
        _record(**kwargs)


def test_empty_inputs_return_empty_reports() -> None:
    breakdown = compute_decision_breakdown([])
    assert breakdown == {
        "total": 0,
        "by_decision": {"executed": 0, "modified": 0, "skipped": 0},
        "by_code": {},
        "follow_rate": None,
        "override_rate": None,
    }

    report = compare_execution_to_suggestion([], [])
    assert report["n_pairs"] == 0
    assert report["user_alpha_mean"] is None
    assert report["per_code"] == {}


def test_compare_execution_to_suggestion_scores_executed_modified_and_skipped() -> None:
    executions = [
        _record(code="510300", decision="executed", action="buy", suggested_action="buy"),
        _record(code="159985", decision="modified", action="sell", suggested_action="buy"),
        _record(
            code="512400",
            decision="skipped",
            action="hold",
            shares=0,
            suggested_action="buy",
        ),
    ]
    audit_entries = [
        _audit_entry(
            "2026-05-18T10:00:00+00:00",
            {"510300": 5.0, "159985": 2.0, "512400": 1.0},
        ),
        _audit_entry(
            "2026-05-18T11:00:00+00:00",
            {"510300": 5.5, "159985": 1.8, "512400": 1.1},
        ),
    ]

    report = compare_execution_to_suggestion(
        executions,
        audit_entries,
        horizon_minutes=60.0,
    )

    assert report["n_pairs"] == 3
    assert report["user_alpha_mean"] == pytest.approx((0.0 + 0.2 - 0.1) / 3)
    assert report["user_alpha_count_positive"] == 1
    assert report["user_alpha_count_negative"] == 1
    assert report["per_code"]["510300"]["alpha_mean"] == pytest.approx(0.0)
    assert report["per_code"]["159985"]["alpha_mean"] == pytest.approx(0.2)
    assert report["per_code"]["512400"]["alpha_mean"] == pytest.approx(-0.1)

    by_code = {pair["code"]: pair for pair in report["recent_pairs"]}
    assert by_code["510300"]["decision"] == "executed"
    assert by_code["159985"]["decision"] == "modified"
    assert by_code["512400"]["decision"] == "skipped"


def test_compare_execution_to_suggestion_uses_share_ratio_and_iso_equivalence() -> None:
    execution = _record(
        code="510300",
        decision="modified",
        action="buy",
        shares=50,
        suggested_action="buy",
        suggested_shares=100,
        plan_run_at="2026-05-18T10:00:00Z",
    )
    audit_entries = [
        _audit_entry("2026-05-18T10:00:00+00:00", {"510300": 5.0}),
        _audit_entry("2026-05-18T11:00:00+00:00", {"510300": 5.5}),
    ]

    report = compare_execution_to_suggestion(
        [execution],
        audit_entries,
        horizon_minutes=60.0,
    )

    assert report["n_pairs"] == 1
    pair = report["recent_pairs"][0]
    assert pair["strategy_pnl"] == pytest.approx(0.10)
    assert pair["user_pnl"] == pytest.approx(0.05)
    assert pair["alpha"] == pytest.approx(-0.05)


def test_compare_execution_to_suggestion_skips_missing_and_non_numeric_prices() -> None:
    executions = [
        _record(code="BAD_ANCHOR"),
        _record(code="BAD_FORWARD"),
        _record(code="MISSING_FORWARD"),
    ]
    audit_entries = [
        _audit_entry(
            "2026-05-18T10:00:00+00:00",
            {"BAD_ANCHOR": "not-a-price", "BAD_FORWARD": 2.0, "MISSING_FORWARD": 3.0},
        ),
        _audit_entry(
            "2026-05-18T11:00:00+00:00",
            {"BAD_ANCHOR": 1.1, "BAD_FORWARD": "not-a-price"},
        ),
    ]

    report = compare_execution_to_suggestion(
        executions,
        audit_entries,
        horizon_minutes=60.0,
    )

    assert report["n_pairs"] == 0
    assert report["recent_pairs"] == []
