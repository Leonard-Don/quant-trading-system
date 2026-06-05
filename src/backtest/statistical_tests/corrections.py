"""Multiple-testing corrections (Bonferroni and Holm-Bonferroni).

Extracted verbatim from ``strategy_statistical_tests`` and re-exported there
so the public import path is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from .results import MultipleTestingCorrection


def bonferroni_correct(
    p_values: Sequence[float],
    *,
    alpha: float = 0.05,
    labels: Optional[Sequence[str]] = None,
) -> MultipleTestingCorrection:
    """Bonferroni correction: each test uses α/k threshold.

    Conservative but simple. For a pairwise grid of 6 comparisons at
    α=0.05, every individual test now needs p < 0.0083 to reject.
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    raw = [float(p) for p in p_values]
    k = len(raw)
    if k == 0:
        return MultipleTestingCorrection(
            method="bonferroni",
            alpha=alpha,
            raw_p_values=[],
            adjusted_alpha=[],
            rejected=[],
            labels=list(labels) if labels else [],
        )
    threshold = alpha / k
    rejected = [p < threshold for p in raw]
    return MultipleTestingCorrection(
        method="bonferroni",
        alpha=alpha,
        raw_p_values=raw,
        adjusted_alpha=[threshold] * k,
        rejected=rejected,
        labels=list(labels) if labels else [],
    )


def holm_correct(
    p_values: Sequence[float],
    *,
    alpha: float = 0.05,
    labels: Optional[Sequence[str]] = None,
) -> MultipleTestingCorrection:
    """Holm-Bonferroni step-down correction.

    Less conservative than vanilla Bonferroni. Sort p-values ascending;
    the i-th (1-indexed) test compares to ``alpha / (k - i + 1)``. The
    first failure to reject cascades to all higher-ranked tests.
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    raw = [float(p) for p in p_values]
    k = len(raw)
    if k == 0:
        return MultipleTestingCorrection(
            method="holm",
            alpha=alpha,
            raw_p_values=[],
            adjusted_alpha=[],
            rejected=[],
            labels=list(labels) if labels else [],
        )
    order = sorted(range(k), key=lambda i: raw[i])
    rejected_ordered = [False] * k
    threshold_ordered = [0.0] * k
    cascade_fail = False
    for rank, original_idx in enumerate(order):
        threshold = alpha / (k - rank)
        threshold_ordered[original_idx] = threshold
        if cascade_fail:
            rejected_ordered[original_idx] = False
            continue
        if raw[original_idx] < threshold:
            rejected_ordered[original_idx] = True
        else:
            cascade_fail = True
            rejected_ordered[original_idx] = False
    return MultipleTestingCorrection(
        method="holm",
        alpha=alpha,
        raw_p_values=raw,
        adjusted_alpha=threshold_ordered,
        rejected=rejected_ordered,
        labels=list(labels) if labels else [],
    )
