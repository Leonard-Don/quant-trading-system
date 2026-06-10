from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp

from src.data.factor_panel import FactorPanel


def forward_returns(panel: FactorPanel, as_of, horizon: int) -> pd.Series:
    as_of = pd.Timestamp(as_of)
    out = {}
    for sym in panel.symbols:
        df = panel.prices[sym]
        pos = df.index.searchsorted(as_of)
        if pos >= len(df) or df.index[pos] != as_of:  # as_of must be a trading day for this symbol
            continue
        fwd = pos + horizon
        if fwd >= len(df):
            continue
        c0, c1 = df["close"].iloc[pos], df["close"].iloc[fwd]
        if c0 and np.isfinite(c0) and np.isfinite(c1):
            out[sym] = float(c1 / c0 - 1.0)
    return pd.Series(out, dtype=float)


def _rank_ic(factor_vals: pd.Series, fwd: pd.Series, direction: int) -> float:
    common = factor_vals.dropna().index.intersection(fwd.dropna().index)
    if len(common) < 5:
        return np.nan
    f = factor_vals.loc[common].astype(float) * direction
    r = fwd.loc[common].astype(float)
    rho, _ = spearmanr(f, r)
    return float(rho) if np.isfinite(rho) else np.nan


def factor_ic_series(
    factor,
    panel: FactorPanel,
    dates,
    horizon: int,
    eligible_by_date: dict[pd.Timestamp, set[str]] | None = None,
) -> pd.Series:
    """Rank-IC of ``factor`` on each rebalance date.

    ``eligible_by_date`` (optional) is a ``{date: set_of_eligible_symbols}`` map.
    When provided, on each date the cross-section (factor values AND forward
    returns) is restricted to that date's eligible symbols BEFORE computing rank
    IC — this is how survivorship-free / suspension-filtered eligibility is wired
    in. ``None`` (default) means no filter = legacy behavior.
    """
    direction = getattr(factor, "direction", 1)
    rows = {}
    for d in dates:
        d = pd.Timestamp(d)
        fvals = factor.compute(panel, d)
        fwd = forward_returns(panel, d, horizon)
        if eligible_by_date is not None:
            eligible = eligible_by_date.get(d)
            if eligible is not None:
                fvals = fvals[fvals.index.isin(eligible)]
                fwd = fwd[fwd.index.isin(eligible)]
        ic = _rank_ic(fvals, fwd, direction)
        if np.isfinite(ic):
            rows[d] = ic
    return pd.Series(rows, dtype=float).sort_index()


def passes_ic_gate(oos_ic: float, icir: float, sign_stable: bool, threshold: float = 0.03) -> bool:
    """A factor passes only if its OUT-OF-SAMPLE IC is positive AND material in the SAME
    direction (>= threshold) — not merely large in magnitude. ``direction`` is already applied
    when the IC is computed, so positive = predicts as intended. A sign flip OOS (positive
    in-sample, negative OOS) is overfit, not signal, and MUST fail (a previous ``abs(oos_ic)``
    gate wrongly let such factors through)."""
    return bool(
        np.isfinite(oos_ic)
        and oos_ic >= threshold
        and np.isfinite(icir)
        and icir > 0
        and sign_stable
    )


def evaluate_factor(
    factor,
    panel: FactorPanel,
    dates,
    horizon: int,
    train_frac: float = 0.7,
    eligible_by_date: dict[pd.Timestamp, set[str]] | None = None,
) -> dict:
    ic = factor_ic_series(factor, panel, dates, horizon, eligible_by_date=eligible_by_date)
    if ic.empty:
        return {
            "name": factor.name,
            "n_dates": 0,
            "mean_ic": np.nan,
            "icir": np.nan,
            "oos_mean_ic": np.nan,
            "oos_n": 0,
            "oos_icir": np.nan,
            "oos_t_stat": np.nan,
            "oos_p_value": np.nan,
            "yearly_ic": {},
            "passes": False,
        }
    split = int(len(ic) * train_frac)
    oos = ic.iloc[split:]
    icir = float(ic.mean() / ic.std(ddof=0)) if ic.std(ddof=0) else np.nan
    # OOS-only dispersion + a one-sided t-test (H1: mean OOS IC > 0). The
    # full-sample icir above mixes the train segment, so it can't be the only
    # strength statistic a reader (or the Holm correction) sees.
    oos_icir = (
        float(oos.mean() / oos.std(ddof=0)) if len(oos) and oos.std(ddof=0) else np.nan
    )
    if len(oos) >= 3:
        t_res = ttest_1samp(oos.to_numpy(), 0.0, alternative="greater")
        oos_t_stat, oos_p_value = float(t_res.statistic), float(t_res.pvalue)
    else:
        oos_t_stat, oos_p_value = np.nan, np.nan
    yearly = {int(y): float(v.mean()) for y, v in ic.groupby(ic.index.year)}
    mean_ic, oos_ic = float(ic.mean()), float(oos.mean()) if len(oos) else np.nan
    signs = list(yearly.values())
    stable = len(signs) >= 2 and (all(s >= 0 for s in signs) or all(s <= 0 for s in signs))
    passes = passes_ic_gate(oos_ic, icir, stable)
    return {
        "name": factor.name,
        "n_dates": len(ic),
        "mean_ic": mean_ic,
        "icir": icir,
        "oos_mean_ic": oos_ic,
        "oos_n": len(oos),
        "oos_icir": oos_icir,
        "oos_t_stat": oos_t_stat,
        "oos_p_value": oos_p_value,
        "yearly_ic": yearly,
        "sign_stable": stable,
        "passes": passes,
    }
