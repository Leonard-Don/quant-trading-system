"""Track what the user actually executed vs. what the strategy suggested.

The rotation system is manual-only by design — the user reviews each plan
and decides whether to follow, modify, or skip. Over time this generates
a stream of "strategy said X, I did Y" pairs that are independently more
valuable than the strategy's own IC: they answer **"is my discretionary
override making money or losing it?"**

This module is the data layer for that question. It records executions
to a JSON-Lines file (mirroring ``audit.jsonl`` conventions) and exposes
analytics that compare the strategy-target portfolio vs. the
user-actual portfolio, both using forward returns from the audit log's
``prices_at_decision`` field.

Design choices
--------------
* **Pure functions + simple I/O.** Storage is JSON-Lines, no DB. The
  tracker reads/writes via :func:`append_execution` and
  :func:`read_executions`. Audit rows are read through
  :func:`read_audit_entries`. Tests use ``tmp_path``.
* **Optional fields.** ``actual_fill_price`` is None until the user
  reports it; that's fine — analytics still works on shares + plan price.
* **Audit-log keyed.** Each execution carries the ``plan_run_at`` it
  responded to, so analytics can join on the audit log to find the
  strategy's target weight at that exact moment.
* **No side effects on the strategy.** Recording an execution does
  nothing to the live signal — it's purely observability.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


EXECUTIONS_PATH_ENV = "ETF_EXECUTIONS_PATH"
DEFAULT_EXECUTIONS_PATH = Path.home() / ".config" / "etf-rotation" / "executions.jsonl"
AUDIT_LOG_PATH_ENV = "ETF_AUDIT_LOG_PATH"
DEFAULT_AUDIT_LOG_PATH = Path.home() / ".config" / "etf-rotation" / "audit.jsonl"
VALID_DECISIONS = frozenset({"executed", "modified", "skipped"})
VALID_ACTIONS = frozenset({"buy", "sell", "hold"})
ACTION_DIRECTIONS = {"buy": +1.0, "sell": -1.0, "hold": 0.0}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionRecord:
    """One user-reported response to a strategy suggestion.

    ``decision`` captures the user's intent:
    * ``"executed"``: followed the suggestion (action + shares as suggested)
    * ``"modified"``: did something different (e.g. bought half the suggested size)
    * ``"skipped"``: explicitly chose not to act on the suggestion
    """

    code: str
    decision: str  # "executed" | "modified" | "skipped"
    action: str    # the user's actual action — "buy" / "sell" / "hold"
    shares: int    # what the user actually traded (0 for skipped/hold)
    plan_run_at: Optional[str]      # ISO timestamp of the plan this responded to
    recorded_at: str                # when this execution was recorded
    suggested_action: Optional[str] = None
    suggested_shares: Optional[int] = None
    actual_fill_price: Optional[float] = None
    note: Optional[str] = None
    user_id: Optional[str] = None  # multi-user setups; default None = single user

    def __post_init__(self) -> None:
        _validate_choice("decision", self.decision, VALID_DECISIONS)
        _validate_choice("action", self.action, VALID_ACTIONS)
        if self.suggested_action is not None:
            _validate_choice("suggested_action", self.suggested_action, VALID_ACTIONS)
        _coerce_int(self.shares, "shares")
        _coerce_optional_int(self.suggested_shares, "suggested_shares")
        _coerce_optional_float(self.actual_fill_price, "actual_fill_price")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "code": self.code,
            "decision": self.decision,
            "action": self.action,
            "shares": int(self.shares),
            "plan_run_at": self.plan_run_at,
            "recorded_at": self.recorded_at,
            "suggested_action": self.suggested_action,
            "suggested_shares": (
                int(self.suggested_shares)
                if self.suggested_shares is not None
                else None
            ),
            "actual_fill_price": (
                float(self.actual_fill_price)
                if self.actual_fill_price is not None
                else None
            ),
            "note": self.note,
            "user_id": self.user_id,
        }
        return out

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionRecord":
        return cls(
            code=str(raw["code"]),
            decision=str(raw.get("decision", "executed")),
            action=str(raw.get("action", "hold")),
            shares=_coerce_int(raw.get("shares", 0), "shares"),
            plan_run_at=raw.get("plan_run_at"),
            recorded_at=str(raw.get("recorded_at") or datetime.now(timezone.utc).isoformat()),
            suggested_action=raw.get("suggested_action"),
            suggested_shares=_coerce_optional_int(
                raw.get("suggested_shares"),
                "suggested_shares",
            ),
            actual_fill_price=_coerce_optional_float(
                raw.get("actual_fill_price"),
                "actual_fill_price",
            ),
            note=raw.get("note"),
            user_id=raw.get("user_id"),
        )


# ---------------------------------------------------------------------------
# Path resolution + I/O
# ---------------------------------------------------------------------------


def _resolve_executions_path(explicit: Optional[Path] = None) -> Optional[Path]:
    """Same resolution semantics as the audit log path."""

    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(EXECUTIONS_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    if DEFAULT_EXECUTIONS_PATH.parent.is_dir():
        return DEFAULT_EXECUTIONS_PATH
    return None


def _resolve_audit_log_path(explicit: Optional[Path] = None) -> Optional[Path]:
    """Return the ETF audit path, or None when default auditing is disabled."""

    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(AUDIT_LOG_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    if DEFAULT_AUDIT_LOG_PATH.parent.is_dir():
        return DEFAULT_AUDIT_LOG_PATH
    return None


def _validate_choice(field_name: str, value: Any, valid_values: frozenset[str]) -> None:
    if value not in valid_values:
        raise ValueError(
            f"{field_name} must be one of {sorted(valid_values)} (got {value!r})"
        )


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _coerce_optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    return _coerce_int(value, field_name)


def _coerce_optional_float(value: Any, field_name: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _coerce_positive_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result <= 0:
        return None
    return result


def append_execution(
    record: ExecutionRecord, *, path: Optional[Path] = None,
) -> Optional[Path]:
    """Append one execution row. Returns the path written, or None if disabled.

    Failures are logged and swallowed — recording must never abort a user
    action. The parent directory is created on demand so first use just
    works.
    """

    target = _resolve_executions_path(path)
    if target is None:
        logger.warning(
            "Execution tracker disabled: no path set and "
            "%s does not exist", DEFAULT_EXECUTIONS_PATH.parent,
        )
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to append execution to %s: %s", target, exc)
        return None
    return target


def read_executions(path: Optional[Path] = None) -> List[ExecutionRecord]:
    """Return executions in chronological order. Empty when file missing.

    Malformed lines are logged and skipped, never raised — we treat the
    executions log as best-effort observability data, same as the audit log.
    """

    target = path or _resolve_executions_path()
    if target is None or not Path(target).is_file():
        return []
    out: List[ExecutionRecord] = []
    text = Path(target).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed execution line %d in %s: %s", line_no, target, exc)
            continue
        try:
            out.append(ExecutionRecord.from_dict(raw))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping invalid execution row %d in %s: %s", line_no, target, exc)
    return out


def read_audit_entries(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return validated ETF audit rows from JSONL, empty when missing.

    Bad JSON lines, non-object rows, rows without ``run_at``, and rows
    without mapping ``prices_at_decision`` are logged and skipped. The audit
    log is observability data, so reader failures must not block the manual
    strategy or downstream reconciliation helpers.
    """

    target = path or _resolve_audit_log_path()
    if target is None or not Path(target).is_file():
        return []

    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(
        Path(target).read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed audit line %d in %s: %s", line_no, target, exc)
            continue
        if not isinstance(raw, Mapping):
            logger.warning(
                "Skipping invalid audit row %d in %s: expected object",
                line_no,
                target,
            )
            continue
        if not raw.get("run_at"):
            logger.warning(
                "Skipping invalid audit row %d in %s: missing run_at",
                line_no,
                target,
            )
            continue
        prices = raw.get("prices_at_decision")
        if not isinstance(prices, Mapping):
            logger.warning(
                "Skipping invalid audit row %d in %s: prices_at_decision must be an object",
                line_no,
                target,
            )
            continue
        entries.append(dict(raw))
    return entries


# ---------------------------------------------------------------------------
# Analytics — compare strategy suggestions vs user executions
# ---------------------------------------------------------------------------


def compute_decision_breakdown(executions: Sequence[ExecutionRecord]) -> Dict[str, Any]:
    """Tally executions by decision and by code.

    Returns counts of executed / modified / skipped — at a glance you can
    see whether the user mostly follows the strategy or mostly overrides
    it, and which ETFs see the most discretionary divergence.
    """

    by_decision: Dict[str, int] = {"executed": 0, "modified": 0, "skipped": 0}
    by_code: Dict[str, Dict[str, int]] = {}
    for record in executions:
        decision = record.decision
        by_decision[decision] = by_decision.get(decision, 0) + 1
        bucket = by_code.setdefault(record.code, {"executed": 0, "modified": 0, "skipped": 0})
        bucket[decision] = bucket.get(decision, 0) + 1
    total = sum(by_decision.values())
    return {
        "total": total,
        "by_decision": by_decision,
        "by_code": by_code,
        "follow_rate": (
            by_decision["executed"] / total if total else None
        ),
        "override_rate": (
            (by_decision["modified"] + by_decision["skipped"]) / total
            if total else None
        ),
    }


def compare_execution_to_suggestion(
    executions: Sequence[ExecutionRecord],
    audit_entries: Sequence[Mapping[str, Any]],
    *,
    horizon_minutes: float = 1440.0,
) -> Dict[str, Any]:
    """Score each execution against the strategy's suggestion at the same plan.

    For every execution we look up the audit entry it responded to (by
    ``plan_run_at``) and find the **next audit entry at least
    ``horizon_minutes`` later** to source the forward price. Then:

    * ``strategy_pnl``   — return of acting on the suggested action
    * ``user_pnl``       — return of the user's actual action
    * ``alpha``          — user_pnl - strategy_pnl (positive ⇒ user added value)

    The aggregate report summarises per-code and overall.
    """

    if not executions or not audit_entries:
        return _empty_compare_report(horizon_minutes)

    # Index audit entries by parsed run_at so equivalent ISO strings such as
    # ``Z`` and ``+00:00`` join to the same plan.
    by_run_at: Dict[datetime, Mapping[str, Any]] = {}
    sorted_entries: List[tuple[datetime, Mapping[str, Any]]] = []
    for entry in audit_entries:
        run_dt = _parse_iso(entry.get("run_at"))
        if run_dt is None:
            continue
        by_run_at[run_dt] = entry
        sorted_entries.append((run_dt, entry))
    sorted_entries.sort(key=lambda item: item[0])

    pairs: List[Dict[str, Any]] = []
    per_code: Dict[str, List[float]] = {}
    for record in executions:
        if not record.plan_run_at:
            continue
        anchor_dt = _parse_iso(record.plan_run_at)
        if anchor_dt is None:
            continue
        anchor = by_run_at.get(anchor_dt)
        if anchor is None:
            continue
        anchor_prices = anchor.get("prices_at_decision") or {}
        if not isinstance(anchor_prices, Mapping):
            continue
        decision_price = anchor_prices.get(record.code)
        decision_price_f = _coerce_positive_float(decision_price)
        if decision_price_f is None:
            continue
        # Find the forward audit entry past the horizon.
        forward_price = None
        for e_dt, entry in sorted_entries:
            if e_dt is None or e_dt <= anchor_dt:
                continue
            if (e_dt - anchor_dt).total_seconds() < horizon_minutes * 60:
                continue
            entry_prices = entry.get("prices_at_decision") or {}
            if not isinstance(entry_prices, Mapping):
                continue
            candidate = entry_prices.get(record.code)
            candidate_f = _coerce_positive_float(candidate)
            if candidate_f is not None:
                forward_price = candidate_f
                break
        if forward_price is None:
            continue

        # Compute strategy and user P&L from a normalised signed exposure.
        # The audit log does not know the user's whole portfolio size, but
        # execution rows do carry shares. We therefore scale actual exposure
        # by suggested_shares when available: buying half the suggested size
        # earns half the per-decision return instead of looking identical to
        # fully following the strategy.
        forward_return = forward_price / decision_price_f - 1.0

        baseline_shares = _normalisation_shares(record)
        strategy_exposure = _normalised_exposure(
            record.suggested_action or "hold",
            record.suggested_shares,
            baseline_shares,
        )
        user_exposure = _normalised_exposure(
            record.action,
            record.shares,
            baseline_shares,
        )
        # If the user "skipped", their effective direction is whatever
        # the existing position was — we can't tell from the execution
        # alone. Best-effort: treat skip-of-sell as "hold long" → +1,
        # skip-of-buy as "remained flat" → 0. The audit log's current
        # weights would disambiguate but we keep this simple.
        if record.decision == "skipped":
            if record.suggested_action == "sell":
                user_exposure = +1.0   # skipped a sell → stayed long
            elif record.suggested_action == "buy":
                user_exposure = 0.0    # skipped a buy → stayed flat
            else:
                user_exposure = 0.0

        strategy_pnl = strategy_exposure * forward_return
        user_pnl = user_exposure * forward_return
        alpha = user_pnl - strategy_pnl

        pairs.append({
            "code": record.code,
            "plan_run_at": record.plan_run_at,
            "forward_price": forward_price,
            "decision_price": decision_price_f,
            "forward_return": forward_return,
            "suggested_action": record.suggested_action,
            "user_action": record.action,
            "decision": record.decision,
            "suggested_shares": record.suggested_shares,
            "user_shares": record.shares,
            "strategy_exposure": strategy_exposure,
            "user_exposure": user_exposure,
            "strategy_pnl": strategy_pnl,
            "user_pnl": user_pnl,
            "alpha": alpha,
        })
        per_code.setdefault(record.code, []).append(alpha)

    if not pairs:
        return _empty_compare_report(horizon_minutes)

    alphas = [p["alpha"] for p in pairs]
    user_pnls = [p["user_pnl"] for p in pairs]
    strategy_pnls = [p["strategy_pnl"] for p in pairs]
    return {
        "n_pairs": len(pairs),
        "user_alpha_mean": sum(alphas) / len(alphas),
        "user_alpha_count_positive": sum(1 for a in alphas if a > 0),
        "user_alpha_count_negative": sum(1 for a in alphas if a < 0),
        "user_pnl_mean": sum(user_pnls) / len(user_pnls),
        "strategy_pnl_mean": sum(strategy_pnls) / len(strategy_pnls),
        "per_code": {
            code: {
                "n": len(arr),
                "alpha_mean": sum(arr) / len(arr) if arr else None,
                "positive_alpha_rate": (
                    sum(1 for a in arr if a > 0) / len(arr) if arr else None
                ),
            }
            for code, arr in per_code.items()
        },
        "horizon_minutes": horizon_minutes,
        # Most-recent N pairs for the dashboard timeline
        "recent_pairs": pairs[-20:],
    }


def compare_recorded_executions_to_audit(
    *,
    executions_path: Optional[Path] = None,
    audit_path: Optional[Path] = None,
    horizon_minutes: float = 1440.0,
) -> Dict[str, Any]:
    """Load recorded executions plus audit rows and return the comparison report."""

    return compare_execution_to_suggestion(
        read_executions(executions_path),
        read_audit_entries(audit_path),
        horizon_minutes=horizon_minutes,
    )


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalisation_shares(record: ExecutionRecord) -> float:
    for value in (record.suggested_shares, record.shares):
        if value is not None and value > 0:
            return float(value)
    return 1.0


def _normalised_exposure(action: str, shares: Optional[int], baseline_shares: float) -> float:
    direction = ACTION_DIRECTIONS[action]
    if direction == 0:
        return 0.0
    if shares is None:
        return direction
    if shares <= 0:
        return 0.0
    return direction * (float(shares) / baseline_shares)


def _empty_compare_report(horizon_minutes: float) -> Dict[str, Any]:
    return {
        "n_pairs": 0,
        "user_alpha_mean": None,
        "user_alpha_count_positive": 0,
        "user_alpha_count_negative": 0,
        "user_pnl_mean": None,
        "strategy_pnl_mean": None,
        "per_code": {},
        "horizon_minutes": horizon_minutes,
        "recent_pairs": [],
    }


__all__ = [
    "AUDIT_LOG_PATH_ENV",
    "DEFAULT_AUDIT_LOG_PATH",
    "DEFAULT_EXECUTIONS_PATH",
    "EXECUTIONS_PATH_ENV",
    "ExecutionRecord",
    "append_execution",
    "compare_recorded_executions_to_audit",
    "compute_decision_breakdown",
    "compare_execution_to_suggestion",
    "read_audit_entries",
    "read_executions",
]
