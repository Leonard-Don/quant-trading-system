"""DataHandler: orchestrate ``NormalizedFrame`` + ``FeatureSet`` into a feature matrix.

The handler is intentionally small. It applies one of three null-handling policies
when assembling the feature matrix:

* ``drop`` (default) — drop rows where any feature is null. Use when downstream
  models can't tolerate NaNs (most sklearn estimators).
* ``keep`` — keep nulls in the output. Use when the model handles them (LightGBM,
  XGBoost ``missing`` arg).
* ``raise`` — raise ``FeatureMatrixError`` if any null appears post-compute. Use
  in strict research mode where you want to catch unexpected gaps loudly.

The handler also surfaces a ``prepare_with_report`` variant that returns the matrix
*plus* a small dict suitable for embedding in a ``BacktestReport`` — number of rows
in, rows out, dropped, plus the underlying frame's provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .feature_set import FeatureSet
from .normalized_frame import NormalizedFrame

VALID_NULL_POLICIES = ("drop", "keep", "raise")


class FeatureMatrixError(ValueError):
    """Raised when a feature matrix violates the configured null policy."""


@dataclass(frozen=True)
class FeatureMatrixReport:
    """Companion stats for a feature matrix — embeddable in a BacktestReport."""

    rows_in: int
    rows_out: int
    rows_dropped: int
    null_policy: str
    feature_names: Sequence[str]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_in": int(self.rows_in),
            "rows_out": int(self.rows_out),
            "rows_dropped": int(self.rows_dropped),
            "null_policy": self.null_policy,
            "feature_names": list(self.feature_names),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class DataHandler:
    """Configurable feature-matrix builder.

    Construct once per experiment, reuse across symbols. The handler holds no state
    between ``prepare`` calls — frames flow in, matrices flow out.
    """

    null_policy: str = "drop"

    def __post_init__(self) -> None:
        if self.null_policy not in VALID_NULL_POLICIES:
            raise ValueError(
                f"null_policy must be one of {VALID_NULL_POLICIES}, got {self.null_policy!r}"
            )

    def prepare(self, frame: NormalizedFrame, feature_set: FeatureSet) -> pd.DataFrame:
        matrix = feature_set.compute(frame)
        return self._apply_null_policy(matrix)

    def prepare_with_report(
        self, frame: NormalizedFrame, feature_set: FeatureSet
    ) -> tuple[pd.DataFrame, FeatureMatrixReport]:
        raw_matrix = feature_set.compute(frame)
        matrix = self._apply_null_policy(raw_matrix)
        report = FeatureMatrixReport(
            rows_in=len(raw_matrix.index),
            rows_out=len(matrix.index),
            rows_dropped=int(len(raw_matrix.index) - len(matrix.index)),
            null_policy=self.null_policy,
            feature_names=feature_set.names,
            provenance=frame.provenance.to_dict(),
        )
        return matrix, report

    def _apply_null_policy(self, matrix: pd.DataFrame) -> pd.DataFrame:
        if self.null_policy == "keep":
            return matrix
        if self.null_policy == "drop":
            return matrix.dropna()
        # raise
        if matrix.isna().any().any():
            offenders = [c for c in matrix.columns if matrix[c].isna().any()]
            raise FeatureMatrixError(f"null_policy='raise' but features contain nulls: {offenders}")
        return matrix


__all__: Sequence[str] = (
    "VALID_NULL_POLICIES",
    "DataHandler",
    "FeatureMatrixError",
    "FeatureMatrixReport",
)
