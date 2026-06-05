"""DataFrame reporting helpers and the walk-forward statistical-test pipeline.

Extracted verbatim from ``strategy_statistical_tests`` and re-exported there
so the public import path is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from .core import (
    _LOSS_FN_RETURN,
    diebold_mariano_test,
    politis_romano_block_bootstrap,
    sharpe_ratio_test,
)
from .corrections import holm_correct
from .results import BlockBootstrapResult, DMResult, SharpeTestResult


def results_to_dataframe(
    results: Sequence[Union[DMResult, BlockBootstrapResult, SharpeTestResult]],
    labels: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Flatten a list of test-result dataclasses into a DataFrame.

    Convenience used by the CLI for terminal-friendly tables. The
    ``labels`` argument prepends a ``pair`` column when supplied.
    """

    rows: list[dict[str, object]] = []
    for i, res in enumerate(results):
        row: dict[str, object] = dict(res.to_dict())  # type: ignore[arg-type]
        if labels is not None and i < len(labels):
            row = {"pair": labels[i], **row}
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Walk-forward statistical tests
# ---------------------------------------------------------------------------


def _resolve_period_index(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    index: Optional[Sequence[Any]] = None,
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Coerce ``(returns_a, returns_b, index)`` into aligned numpy arrays + DatetimeIndex.

    Accepts:
    * Two ``pd.Series`` with date indices — index inferred from the first.
    * Two array-likes plus an explicit ``index`` argument.

    The walk-forward windows need a *time* axis so the caller can slice
    by calendar months — without one we can only walk by observation
    count, which collapses to the terminal-period test as the window
    grows. Raises ``ValueError`` when no usable index is available.
    """

    if isinstance(returns_a, pd.Series) and isinstance(returns_b, pd.Series):
        # Align on the intersection of both indices so a missing day in
        # either series doesn't pollute the walk-forward slicing.
        aligned_idx = returns_a.index.intersection(returns_b.index)
        if len(aligned_idx) == 0:
            raise ValueError(
                "returns_a and returns_b share zero index entries; cannot "
                "build a walk-forward time axis"
            )
        a_series = returns_a.reindex(aligned_idx)
        b_series = returns_b.reindex(aligned_idx)
        ts_index = pd.DatetimeIndex(pd.to_datetime(aligned_idx))
        return (
            np.asarray(a_series.to_numpy(), dtype=float),
            np.asarray(b_series.to_numpy(), dtype=float),
            ts_index,
        )

    a_arr = np.asarray(returns_a, dtype=float)
    b_arr = np.asarray(returns_b, dtype=float)
    if a_arr.shape != b_arr.shape:
        raise ValueError(
            f"returns_a (len={a_arr.size}) and returns_b (len={b_arr.size}) "
            "must have the same length — align them on dates first"
        )
    if index is None:
        raise ValueError(
            "walk_forward_statistical_tests requires either two pd.Series "
            "with date indices, or an explicit ``index=`` argument matching "
            "the length of returns_a / returns_b"
        )
    ts_index = pd.DatetimeIndex(pd.to_datetime(list(index)))
    if len(ts_index) != a_arr.size:
        raise ValueError(
            f"index length ({len(ts_index)}) does not match returns length "
            f"({a_arr.size})"
        )
    return a_arr, b_arr, ts_index


def _iter_walk_forward_bounds(
    period_index: pd.DatetimeIndex,
    *,
    window_years: float,
    step_months: int,
) -> Iterator[tuple[int, pd.Timestamp, pd.Timestamp, slice]]:
    """Yield ``(window_id, start_ts, end_ts, slice_obj)`` for each rolling window.

    ``window_years`` is fractional so the caller can say ``window=2`` or
    ``window=0.5`` (six months). ``step_months`` is an integer — months
    are the natural cadence for re-baselining and matches the existing
    walkforward analyzer's contract.

    The slice walks the *observation index* (so downstream just does
    ``returns_a[slice_obj]`` without needing to re-derive timestamps).
    A window is emitted only if it contains at least one observation;
    skipping empties keeps the per-window DataFrame clean.
    """

    if window_years <= 0:
        raise ValueError(f"window_years must be > 0; got {window_years!r}")
    if step_months <= 0:
        raise ValueError(f"step_months must be > 0; got {step_months!r}")
    if len(period_index) == 0:
        return

    window_months = round(float(window_years) * 12.0)
    if window_months < 1:
        raise ValueError(
            f"window_years={window_years!r} resolves to < 1 month; "
            "use a longer window"
        )
    window_delta = pd.DateOffset(months=window_months)
    step_delta = pd.DateOffset(months=step_months)
    one_day = pd.Timedelta(days=1)

    period_start = period_index[0]
    period_end = period_index[-1]

    window_id = 0
    cursor = period_start
    while True:
        window_end = (cursor + window_delta) - one_day
        if window_end > period_end:
            return
        mask = (period_index >= cursor) & (period_index <= window_end)
        positions = np.flatnonzero(mask)
        if positions.size == 0:
            # No observations fell in this window (e.g. holiday-only span);
            # advance the cursor without emitting.
            cursor = cursor + step_delta
            continue
        first = int(positions[0])
        last = int(positions[-1])
        yield window_id, cursor, window_end, slice(first, last + 1)
        window_id += 1
        cursor = cursor + step_delta


def walk_forward_statistical_tests(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    *,
    index: Optional[Sequence[Any]] = None,
    window_years: float = 2.0,
    step_months: int = 6,
    loss_fn: str = _LOSS_FN_RETURN,
    h: int = 1,
    block_size: int = 10,
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    seed: int = 42,
    apply_holm: bool = True,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Run DM + Sharpe + block-bootstrap on every walk-forward window.

    Reuses the same primitives the terminal-period tests do, applied
    sequentially to slices of the aligned return series. Returns a
    DataFrame with one row per window plus (optionally) Holm-corrected
    rejection flags for the DM p-value column.

    Parameters
    ----------
    returns_a, returns_b
        Either two :class:`pd.Series` with date indices (preferred), or
        two array-likes plus an explicit ``index`` argument.
    index
        Date-like sequence with one entry per observation. Required when
        ``returns_a``/``returns_b`` are not pandas Series.
    window_years
        Window length in years (fractional allowed: ``0.5`` for six
        months, ``2`` for two years). Resolved to whole months via
        ``round(window_years * 12)``.
    step_months
        Cursor step in months. Default 6.
    loss_fn, h
        Passed through to :func:`diebold_mariano_test`. The default
        ``loss_fn="negative_return"`` matches the terminal-period DM
        test in :class:`StrategyComparator`.
    block_size, n_bootstrap, ci_level, seed
        Passed through to :func:`politis_romano_block_bootstrap`. The
        seed is deterministic so two runs produce identical output.
    apply_holm
        When ``True`` (default), apply Holm-Bonferroni step-down
        correction across the per-window DM p-values and add three
        columns:

        * ``dm_holm_threshold`` — the per-window cutoff used.
        * ``dm_holm_rejected`` — boolean: did this window survive Holm?
        * ``dm_holm_alpha`` — the user-supplied family-wise α.

        When ``False`` the columns are absent.
    alpha
        Family-wise significance level for Holm. Default 0.05.

    Returns
    -------
    pd.DataFrame
        One row per emitted window. Columns:

        * ``window_id`` — 0-indexed sequence number
        * ``start_date`` / ``end_date`` — ISO strings (calendar bounds)
        * ``n_obs`` — observations inside the window after NaN/Inf drop
        * ``dm_stat`` / ``dm_pvalue`` — Diebold-Mariano on this slice
        * ``sharpe_z`` / ``sharpe_pvalue`` — Memmel Sharpe difference
        * ``boot_lower`` / ``boot_upper`` — bootstrap CI on E[r_a - r_b]
        * ``boot_pvalue`` — bootstrap 2-sided p-value
        * ``dm_holm_*`` (when ``apply_holm=True``)

    Notes
    -----
    Windows are independent backtests on overlapping data — they
    double-count their overlap. That's the same caveat the walkforward
    analyzer carries; the goal here is *temporal stability of the
    significance test*, not unbiased ensemble inference.

    Empty windows (no observations after slicing) are silently dropped
    so the returned DataFrame has no degenerate rows. If every window
    is empty, the DataFrame returns with zero rows and the documented
    column schema preserved.
    """

    a_arr, b_arr, ts_index = _resolve_period_index(returns_a, returns_b, index)
    if len(ts_index) == 0:
        empty_cols = [
            "window_id",
            "start_date",
            "end_date",
            "n_obs",
            "dm_stat",
            "dm_pvalue",
            "sharpe_z",
            "sharpe_pvalue",
            "boot_lower",
            "boot_upper",
            "boot_pvalue",
        ]
        if apply_holm:
            empty_cols.extend(
                ["dm_holm_threshold", "dm_holm_rejected", "dm_holm_alpha"]
            )
        return pd.DataFrame(columns=empty_cols)

    rows: list[dict[str, Union[float, int, str, bool]]] = []
    for window_id, start_ts, end_ts, sl in _iter_walk_forward_bounds(
        ts_index,
        window_years=window_years,
        step_months=step_months,
    ):
        a_slice = a_arr[sl]
        b_slice = b_arr[sl]
        # Use _aligned_arrays internally via the existing helpers so
        # NaN/Inf drop is consistent with the terminal-period path.
        dm = diebold_mariano_test(
            a_slice.tolist(),
            b_slice.tolist(),
            loss_fn=loss_fn,
            h=h,
        )
        sh = sharpe_ratio_test(
            a_slice.tolist(),
            b_slice.tolist(),
            method="memmel",
        )
        boot = politis_romano_block_bootstrap(
            a_slice.tolist(),
            b_slice.tolist(),
            block_size=block_size,
            n_bootstrap=n_bootstrap,
            ci_level=ci_level,
            seed=seed,
        )
        rows.append(
            {
                "window_id": int(window_id),
                "start_date": str(start_ts.date()),
                "end_date": str(end_ts.date()),
                # n_obs from DM result reflects post-NaN/Inf drop — that's
                # the honest "observations actually consumed" count.
                "n_obs": int(dm.n_obs),
                "dm_stat": float(dm.dm_statistic),
                "dm_pvalue": float(dm.p_value),
                "sharpe_z": float(sh.z_statistic),
                "sharpe_pvalue": float(sh.p_value),
                "boot_lower": float(boot.ci_low),
                "boot_upper": float(boot.ci_high),
                "boot_pvalue": float(boot.p_value_two_sided),
            }
        )

    df = pd.DataFrame(rows)
    if apply_holm and not df.empty:
        correction = holm_correct(
            df["dm_pvalue"].tolist(),
            alpha=alpha,
            labels=df["window_id"].astype(str).tolist(),
        )
        df["dm_holm_threshold"] = correction.adjusted_alpha
        df["dm_holm_rejected"] = correction.rejected
        df["dm_holm_alpha"] = alpha
    return df
