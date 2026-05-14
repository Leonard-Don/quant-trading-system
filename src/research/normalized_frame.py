"""NormalizedFrame: a typed, provenance-tracked wrapper around a pandas DataFrame.

The research pipeline takes raw provider payloads (akshare DataFrames, fixture JSON,
synthetic generators) and needs a consistent in-memory representation before features,
models, or backtests touch it. ``NormalizedFrame`` is that representation.

Three guarantees:

1. **Schema validation.** A ``FrameSchema`` declares the index name + dtype and the
   value columns + dtypes. Building a ``NormalizedFrame`` from raw data validates the
   shape — missing required columns and bad index types raise ``FrameValidationError``.

2. **Absent vs. null distinction.** Real-world feeds often *omit* a column entirely
   (e.g. an old API response lacks ``turnover``) — that is fundamentally different
   from a column being present but containing NaN for some rows. The ``field_status``
   map records ``"present"`` / ``"absent"`` / ``"has_nulls"`` per declared column so
   downstream code can decide whether to backfill, error, or label features as
   synthetic.

3. **Provenance.** A small ``FrameProvenance`` records the source id, sample time
   (``as_of``, never "now"), and a free-form reason for synthetic / fallback frames.
   This piggybacks on the existing ``src.data.source_health`` vocabulary so the same
   freshness labels can be applied.

The class is deliberately stdlib + pandas only — no SDK dependencies — so it can be
constructed from notebooks, scripts, or the FastAPI service layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

FIELD_STATUS_PRESENT = "present"
FIELD_STATUS_ABSENT = "absent"
FIELD_STATUS_HAS_NULLS = "has_nulls"


class FrameValidationError(ValueError):
    """Raised when raw data cannot be coerced into the declared ``FrameSchema``."""


@dataclass(frozen=True)
class FrameSchema:
    """Declarative schema for a ``NormalizedFrame``.

    ``index`` is a ``(name, dtype)`` pair — typical use ``("date", "datetime64[ns]")``.
    ``value_columns`` is an ordered mapping of column name → dtype string (anything
    ``pandas.Series.astype`` accepts). The order is preserved as the canonical column
    order of the resulting frame.

    ``required`` lists columns that must be present in the raw input; columns outside
    ``required`` may be absent and will be tracked as ``"absent"`` in field_status
    without raising.
    """

    index: tuple[str, str]
    value_columns: Mapping[str, str]
    required: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.index, tuple) or len(self.index) != 2:
            raise FrameValidationError("FrameSchema.index must be a (name, dtype) tuple")
        index_name, index_dtype = self.index
        if not isinstance(index_name, str) or not index_name.strip():
            raise FrameValidationError("FrameSchema.index name must be a non-empty string")
        if not isinstance(index_dtype, str) or not index_dtype.strip():
            raise FrameValidationError("FrameSchema.index dtype must be a non-empty string")
        if not isinstance(self.value_columns, Mapping) or not self.value_columns:
            raise FrameValidationError("FrameSchema.value_columns must be a non-empty mapping")
        # Tuple-ize required for deterministic iteration.
        object.__setattr__(self, "required", tuple(self.required))
        unknown_required = [c for c in self.required if c not in self.value_columns]
        if unknown_required:
            raise FrameValidationError(
                f"required columns not declared in value_columns: {unknown_required}"
            )

    @property
    def index_name(self) -> str:
        return self.index[0]

    @property
    def index_dtype(self) -> str:
        return self.index[1]

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(self.value_columns.keys())


@dataclass(frozen=True)
class FrameProvenance:
    """Where this frame came from and when its data was sampled.

    ``as_of`` should be the **sample time** of the underlying data, not the time the
    frame was constructed. Pass ``None`` if the upstream did not supply one — do not
    substitute ``datetime.now()``, that conflates sample freshness with build time.
    """

    source_id: str
    as_of: Optional[datetime] = None
    fallback: bool = False
    synthetic: bool = False
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise FrameValidationError("FrameProvenance.source_id must be a non-empty string")
        if self.as_of is not None and not isinstance(self.as_of, datetime):
            raise FrameValidationError("FrameProvenance.as_of must be a datetime or None")
        # Normalize naive datetimes to UTC for downstream serialization.
        if isinstance(self.as_of, datetime) and self.as_of.tzinfo is None:
            object.__setattr__(self, "as_of", self.as_of.replace(tzinfo=timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        as_of_iso: Optional[str]
        if self.as_of is None:
            as_of_iso = None
        else:
            as_of_iso = (
                self.as_of.astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        return {
            "source_id": self.source_id,
            "as_of": as_of_iso,
            "fallback": self.fallback,
            "synthetic": self.synthetic,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class NormalizedFrame:
    """A pandas DataFrame conforming to a declared schema, plus provenance.

    Build via :meth:`from_raw` — that is the validating constructor. Direct
    instantiation is allowed but assumes the caller has already validated the inputs.
    """

    data: pd.DataFrame
    schema: FrameSchema
    provenance: FrameProvenance
    field_status: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        raw: pd.DataFrame,
        schema: FrameSchema,
        provenance: FrameProvenance,
    ) -> NormalizedFrame:
        """Validate + coerce ``raw`` to ``schema``, returning a NormalizedFrame.

        Behavior:

        * The index is set from ``schema.index_name`` (column lifted into the index
          if present in ``raw``; otherwise the existing index is renamed/cast).
        * Index values are coerced to ``schema.index_dtype`` via ``astype``. Failures
          raise ``FrameValidationError``.
        * Required columns missing from ``raw`` raise ``FrameValidationError``.
        * Optional columns missing from ``raw`` are recorded as ``"absent"`` in
          ``field_status`` and filled with ``pd.NA``-coerced dtype defaults so the
          DataFrame shape is uniform.
        * Present columns with any null values get ``"has_nulls"``; otherwise
          ``"present"``.
        """
        if not isinstance(raw, pd.DataFrame):
            raise FrameValidationError("raw must be a pandas DataFrame")

        working = raw.copy()

        # Lift / rename / cast the index.
        idx_name = schema.index_name
        if idx_name in working.columns:
            working = working.set_index(idx_name)
        elif working.index.name != idx_name:
            raise FrameValidationError(
                f"index column '{idx_name}' missing from raw frame and existing index is unnamed/mismatched"
            )

        try:
            working.index = working.index.astype(schema.index_dtype)
        except (TypeError, ValueError) as exc:
            raise FrameValidationError(
                f"index could not be cast to {schema.index_dtype}: {exc}"
            ) from exc

        # Check required columns.
        missing_required = [c for c in schema.required if c not in working.columns]
        if missing_required:
            raise FrameValidationError(
                f"required columns missing from raw frame: {missing_required}"
            )

        # Build the canonical column projection in schema order.
        field_status: dict[str, str] = {}
        projected = pd.DataFrame(index=working.index)
        for col, dtype in schema.value_columns.items():
            if col not in working.columns:
                field_status[col] = FIELD_STATUS_ABSENT
                # Fill an empty column of the declared dtype so consumers can rely
                # on the schema's column set even for sparse upstream payloads.
                try:
                    projected[col] = pd.Series(
                        [pd.NA] * len(working.index), index=working.index, dtype=dtype
                    )
                except TypeError:
                    projected[col] = pd.Series(
                        [float("nan")] * len(working.index), index=working.index, dtype=dtype
                    )
                continue
            series = working[col]
            try:
                series = series.astype(dtype)
            except (TypeError, ValueError) as exc:
                raise FrameValidationError(
                    f"column '{col}' could not be cast to {dtype}: {exc}"
                ) from exc
            projected[col] = series
            field_status[col] = (
                FIELD_STATUS_HAS_NULLS if series.isna().any() else FIELD_STATUS_PRESENT
            )

        return cls(
            data=projected,
            schema=schema,
            provenance=provenance,
            field_status=dict(field_status),
        )

    @property
    def columns(self) -> tuple[str, ...]:
        return self.schema.columns

    @property
    def index_name(self) -> str:
        return self.schema.index_name

    def is_empty(self) -> bool:
        return self.data.empty

    def absent_columns(self) -> tuple[str, ...]:
        return tuple(c for c, s in self.field_status.items() if s == FIELD_STATUS_ABSENT)

    def columns_with_nulls(self) -> tuple[str, ...]:
        return tuple(c for c, s in self.field_status.items() if s == FIELD_STATUS_HAS_NULLS)

    def to_summary(self) -> dict[str, Any]:
        """JSON-safe summary — useful for logs / API responses."""
        return {
            "rows": len(self.data.index),
            "columns": list(self.columns),
            "field_status": dict(self.field_status),
            "provenance": self.provenance.to_dict(),
        }


__all__: Sequence[str] = (
    "FIELD_STATUS_ABSENT",
    "FIELD_STATUS_HAS_NULLS",
    "FIELD_STATUS_PRESENT",
    "FrameProvenance",
    "FrameSchema",
    "FrameValidationError",
    "NormalizedFrame",
)
