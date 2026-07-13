"""ModelRun: a frozen, JSON-serializable record of a single model training/evaluation.

A ``ModelRun`` is *not* a trained model. It is the **record** of one — the
identifier, the hyperparameters, the metrics that came out, the paths to any
artifacts. The research pipeline produces ``ModelRun`` objects and hands them to the
:mod:`experiment_registry` for tracking; the actual estimator lives wherever the
caller decided (in-memory, joblib pickle, MLflow, etc.) and is referenced through
``artifacts``.

This module deliberately does *not* train ML models — that is the caller's job.
The dataclass is a contract for "I ran something and here's the receipt." Pretending
to train when we don't have a real training loop would just produce misleading
metrics, so the contract is the metrics + provenance and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-:/]{0,127}$")


class ModelRunValidationError(ValueError):
    """Raised when ``ModelRun`` construction inputs are malformed."""


def validate_run_id(run_id: Any) -> str:
    """Return the canonical run id, or raise ``ModelRunValidationError``.

    Rules:

    * Must be a non-empty string.
    * Trimmed length 1..128.
    * Allowed characters: ``A-Z a-z 0-9 . _ - : /`` with a leading alnum.

    The character set is deliberately tight — run ids end up in filesystem paths,
    URLs, and JSON keys, so we reject anything that would force later escaping.
    """
    if not isinstance(run_id, str):
        raise ModelRunValidationError(f"run_id must be a string, got {type(run_id).__name__}")
    trimmed = run_id.strip()
    if not trimmed:
        raise ModelRunValidationError("run_id must not be empty / whitespace-only")
    if not _RUN_ID_PATTERN.match(trimmed):
        raise ModelRunValidationError(
            f"run_id {trimmed!r} contains disallowed characters or is too long"
        )
    return trimmed


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _isoformat(dt: datetime) -> str:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ModelRun:
    """A record of a single model training/evaluation.

    Fields
    ------
    run_id:
        Caller-chosen identifier. Validated via :func:`validate_run_id`.
    model_name:
        Human label for the estimator family (e.g. ``"linear_regression"``).
    params:
        Hyperparameters. Must be a mapping with JSON-coercible values.
    metrics:
        Numeric evaluation metrics. Mapping of string → float / int. Non-numeric
        values raise at construction so registries can't accidentally hold
        unsummable mixed metrics.
    artifacts:
        Optional mapping ``artifact_name -> path/uri``. Strings only; the registry
        does not open the files itself.
    created_at:
        UTC timestamp. Defaults to ``datetime.now(timezone.utc)``.
    notes:
        Optional free-text annotation (e.g. the feature set name or git SHA).
    """

    run_id: str
    model_name: str
    params: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, float] = field(default_factory=dict)
    artifacts: Mapping[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", validate_run_id(self.run_id))
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ModelRunValidationError("model_name must be a non-empty string")
        object.__setattr__(self, "model_name", self.model_name.strip())
        if not isinstance(self.params, Mapping):
            raise ModelRunValidationError("params must be a mapping")
        if not isinstance(self.metrics, Mapping):
            raise ModelRunValidationError("metrics must be a mapping")
        for key, value in self.metrics.items():
            if not isinstance(key, str):
                raise ModelRunValidationError(f"metric keys must be strings, got {key!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ModelRunValidationError(
                    f"metric {key!r} must be numeric, got {type(value).__name__}"
                )
        if not isinstance(self.artifacts, Mapping):
            raise ModelRunValidationError("artifacts must be a mapping")
        for key, value in self.artifacts.items():
            if not isinstance(key, str) or not key.strip():
                raise ModelRunValidationError("artifact names must be non-empty strings")
            if not isinstance(value, str) or not value.strip():
                raise ModelRunValidationError(f"artifact {key!r} path must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ModelRunValidationError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            object.__setattr__(self, "created_at", self.created_at.replace(tzinfo=UTC))
        if self.notes is not None and not isinstance(self.notes, str):
            raise ModelRunValidationError("notes must be a string or None")
        # Freeze maps to dict copies so external mutation can't bleed into the run.
        object.__setattr__(self, "params", dict(self.params))
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "artifacts", dict(self.artifacts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "artifacts": dict(self.artifacts),
            "created_at": _isoformat(self.created_at),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelRun:
        created_raw = data.get("created_at")
        if isinstance(created_raw, str):
            text = created_raw.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                created_at = datetime.fromisoformat(text)
            except ValueError as exc:
                raise ModelRunValidationError(
                    f"created_at could not be parsed: {created_raw!r}"
                ) from exc
        elif isinstance(created_raw, datetime):
            created_at = created_raw
        elif created_raw is None:
            created_at = _utcnow()
        else:
            raise ModelRunValidationError(
                f"created_at must be str/datetime/None, got {type(created_raw).__name__}"
            )
        return cls(
            run_id=data["run_id"],
            model_name=data["model_name"],
            params=data.get("params", {}) or {},
            metrics=data.get("metrics", {}) or {},
            artifacts=data.get("artifacts", {}) or {},
            created_at=created_at,
            notes=data.get("notes"),
        )


__all__: Sequence[str] = (
    "ModelRun",
    "ModelRunValidationError",
    "validate_run_id",
)
