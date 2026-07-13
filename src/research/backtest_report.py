"""BacktestReport: a serializable summary of one backtest run.

Bound to the same provenance discipline as ``NormalizedFrame`` — the report carries
explicit period_start / period_end taken from the **data** (not "now") plus a list
of source-health entries describing where the input frames came from.

Returns are stored as an ordered sequence of ``(date_iso, value)`` pairs so the
report round-trips through JSON without pickling a pandas object. Metrics are a
JSON-safe dict. Both are immutable after construction.

The report intentionally does *not* compute Sharpe / max-drawdown / etc itself —
callers compute those with their preferred library and pass the resulting dict in.
Hard-coding metric formulas would duplicate logic that already lives in
:mod:`src.backtest.metrics` and create a second source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Optional, Union

import pandas as pd


class BacktestReportError(ValueError):
    """Raised when ``BacktestReport`` construction inputs are malformed."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _isoformat_datetime(dt: datetime) -> str:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise BacktestReportError("return date must not be empty")
        # Validate it parses, but keep the caller's preferred format.
        ts = pd.to_datetime(text, errors="coerce")
        if pd.isna(ts):
            raise BacktestReportError(f"return date {value!r} could not be parsed")
        return ts.date().isoformat()
    # pandas timestamps
    if hasattr(value, "to_pydatetime"):
        try:
            py = value.to_pydatetime()
        except Exception as exc:
            raise BacktestReportError(f"could not convert {value!r} to datetime: {exc}") from exc
        return _to_iso_date(py)
    raise BacktestReportError(f"unsupported return date type: {type(value).__name__}")


def _coerce_returns(
    raw: Union[pd.Series, Mapping[Any, Any], Iterable[tuple[Any, Any]]],
) -> tuple[tuple[str, float], ...]:
    pairs: list[tuple[str, float]] = []
    if isinstance(raw, pd.Series):
        iterator: Iterable[tuple[Any, Any]] = raw.items()
    elif isinstance(raw, Mapping):
        iterator = raw.items()
    elif isinstance(raw, Iterable):
        iterator = list(raw)  # type: ignore[arg-type]
    else:
        raise BacktestReportError(
            "returns must be a pandas Series, mapping, or iterable of (date, value) pairs"
        )
    for entry in iterator:
        try:
            d, v = entry
        except (TypeError, ValueError) as exc:
            raise BacktestReportError(
                f"return entry must be a (date, value) pair, got {entry!r}"
            ) from exc
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise BacktestReportError(
                f"return value must be numeric, got {type(v).__name__} for date {d!r}"
            )
        if pd.isna(v):
            raise BacktestReportError(f"return value is NaN for date {d!r}")
        pairs.append((_to_iso_date(d), float(v)))
    return tuple(pairs)


def _coerce_metrics(metrics: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(metrics, Mapping):
        raise BacktestReportError("metrics must be a mapping")
    out: dict[str, float] = {}
    for key, value in metrics.items():
        if not isinstance(key, str):
            raise BacktestReportError(f"metric keys must be strings, got {key!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BacktestReportError(f"metric {key!r} must be numeric, got {type(value).__name__}")
        if pd.isna(value):
            raise BacktestReportError(f"metric {key!r} is NaN")
        out[key] = float(value)
    return out


def _coerce_source_health(entries: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        if hasattr(entry, "to_dict"):
            out.append(dict(entry.to_dict()))
        elif isinstance(entry, Mapping):
            out.append(dict(entry))
        else:
            raise BacktestReportError(
                f"source_health entries must be mappings or have .to_dict(), got {type(entry).__name__}"
            )
    return tuple(out)


@dataclass(frozen=True)
class BacktestReport:
    """An immutable, JSON-serializable backtest summary.

    ``period_start`` / ``period_end`` are derived from the returns series when not
    explicitly supplied, never from ``datetime.now()``. ``generated_at`` *is* the
    build time — it's labelled clearly so consumers don't confuse it with data
    freshness.
    """

    report_id: str
    returns: tuple[tuple[str, float], ...]
    metrics: Mapping[str, float] = field(default_factory=dict)
    source_health: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    generated_at: datetime = field(default_factory=_utcnow)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise BacktestReportError("report_id must be a non-empty string")
        object.__setattr__(self, "report_id", self.report_id.strip())
        object.__setattr__(self, "returns", _coerce_returns(self.returns))
        object.__setattr__(self, "metrics", _coerce_metrics(self.metrics))
        object.__setattr__(self, "source_health", _coerce_source_health(self.source_health))
        if self.period_start is None and self.returns:
            object.__setattr__(self, "period_start", self.returns[0][0])
        if self.period_end is None and self.returns:
            object.__setattr__(self, "period_end", self.returns[-1][0])
        if not isinstance(self.generated_at, datetime):
            raise BacktestReportError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None:
            object.__setattr__(self, "generated_at", self.generated_at.replace(tzinfo=UTC))
        if self.notes is not None and not isinstance(self.notes, str):
            raise BacktestReportError("notes must be a string or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "generated_at": _isoformat_datetime(self.generated_at),
            "returns": [{"date": d, "value": v} for d, v in self.returns],
            "metrics": dict(self.metrics),
            "source_health": [dict(entry) for entry in self.source_health],
            "notes": self.notes,
        }

    def returns_series(self) -> pd.Series:
        """Reconstruct the returns as a date-indexed Series for downstream analytics."""
        if not self.returns:
            return pd.Series([], index=pd.DatetimeIndex([], name="date"), dtype="float64")
        dates = pd.to_datetime([d for d, _ in self.returns])
        values = [v for _, v in self.returns]
        return pd.Series(values, index=pd.DatetimeIndex(dates, name="date"), dtype="float64")


__all__: Sequence[str] = (
    "BacktestReport",
    "BacktestReportError",
)
