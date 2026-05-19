"""Formal statistical hypothesis tests for strategy performance comparisons.

The v0.1 ``StrategyComparator`` (commit ``a54b986``) and the parameter
optimizer's bootstrap CIs (commit ``231c709``) answer "which strategy
posted the higher Sharpe on this window?" and "how wide is the CI on
each Sharpe?", but neither produces a **p-value** for the canonical
research claim *"strategy A has a different (or larger) expected return
/ Sharpe than strategy B"*. Without that, the headline rankings live
in a "looks better in this window" regime and are not statistically
defensible in a paper or production decision.

This module fills that gap by adding three orthogonal tests, all
operating on aligned daily-return series:

* :func:`diebold_mariano_test` — Diebold & Mariano (1995). Tests whether
  the expected **loss differential** between two forecasts (or, in our
  case, two strategy return series) is zero, using a heteroscedasticity
  and autocorrelation consistent (HAC, "Newey-West") variance estimator
  to correct for the serial correlation in trading P&L. Returns a DM
  statistic and a 2-sided p-value.

* :func:`politis_romano_block_bootstrap` — Politis & Romano (1994).
  Circular block bootstrap on the return *differential* ``r_a - r_b``,
  preserving short-horizon autocorrelation that an i.i.d. bootstrap
  would destroy. Returns a mean differential, a (1-α)% CI, and 1-sided
  + 2-sided p-values against H0: ``E[r_a - r_b] = 0``.

* :func:`sharpe_ratio_test` — Memmel (2003) closed-form Sharpe-ratio
  difference test and the Jobson-Korkie (1981) variance estimator both
  reduce the "is Sharpe_a equal to Sharpe_b?" question to a single
  statistic with a known asymptotic distribution. Memmel's correction
  fixes a typo / sign issue in the original Jobson-Korkie variance.

Why three tests, not one
------------------------
DM tests the *mean of a loss differential* — flexible (you choose the
loss function: squared error for forecasting, "negative return" for
return comparisons, or "negative Sharpe contribution" for Sharpe-aware
tests) but is a single-window asymptotic. Block bootstrap is non-
parametric and small-sample-friendly but heavier compute. Memmel /
Jobson-Korkie target the Sharpe ratio directly, which is the metric
the trading community cares about — and they're closed-form, so they
scale to large pairwise grids without bootstrap cost.

Multiple-testing aware
----------------------
Every pairwise comparator (rotation/MR/blend/buy-hold = 4 strategies =
6 unordered pairs) tests 6 null hypotheses simultaneously, so any
"significant" result must survive Bonferroni (α/6) or Holm-Bonferroni
to be honestly defensible. :func:`bonferroni_correct` and
:func:`holm_correct` ship the corrected α thresholds and rejection
flags alongside the raw p-values.

References
----------
* Diebold, F. X. & Mariano, R. S. (1995). Comparing Predictive Accuracy.
  Journal of Business & Economic Statistics, 13(3), 253-263.
* Politis, D. N. & Romano, J. P. (1994). The Stationary Bootstrap.
  Journal of the American Statistical Association, 89(428), 1303-1313.
* Jobson, J. D. & Korkie, B. M. (1981). Performance Hypothesis Testing
  with the Sharpe and Treynor Measures. Journal of Finance, 36(4),
  889-908.
* Memmel, C. (2003). Performance Hypothesis Testing with the Sharpe
  Ratio. Finance Letters, 1(1), 21-23.
* Newey, W. K. & West, K. D. (1987). A Simple, Positive Semi-Definite,
  Heteroskedasticity and Autocorrelation Consistent Covariance Matrix.
  Econometrica, 55(3), 703-708.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Optional, Union

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DMResult:
    """Diebold-Mariano test result.

    * ``dm_statistic`` — the DM test statistic (asymptotically N(0, 1)).
    * ``p_value`` — 2-sided p-value against H0: mean loss differential
      is zero.
    * ``p_value_one_sided`` — 1-sided p-value: P(DM <= -|stat|) i.e.
      A's loss is *smaller* than B's (strategy A is better).
    * ``mean_loss_differential`` — sample mean of loss_a - loss_b. If
      positive, strategy A has higher loss (worse).
    * ``hac_variance`` — HAC (Newey-West) variance estimate; useful
      diagnostic when bandwidth choice is being tuned.
    * ``n_obs`` — observations used (after NaN-dropping).
    * ``loss_fn`` — name of the loss function applied.
    * ``h`` — forecast horizon used for Newey-West lag truncation.
    * ``note`` — free-form caveat (e.g. "fell back to t-distribution due
      to small sample") so downstream consumers can flag low-confidence
      results without re-deriving them.
    """

    dm_statistic: float
    p_value: float
    p_value_one_sided: float
    mean_loss_differential: float
    hac_variance: float
    n_obs: int
    loss_fn: str
    h: int
    note: str = ""

    def to_dict(self) -> dict[str, Union[float, int, str]]:
        return asdict(self)


@dataclass(frozen=True)
class BlockBootstrapResult:
    """Politis-Romano circular block bootstrap result.

    Operates on the return *differential* ``r_a - r_b`` so it tests
    the same null as the DM test but non-parametrically.
    """

    mean_diff: float
    ci_low: float
    ci_high: float
    ci_level: float
    p_value_two_sided: float
    p_value_one_sided: float
    block_size: int
    n_bootstrap: int
    n_obs: int

    def to_dict(self) -> dict[str, Union[float, int]]:
        return asdict(self)


@dataclass(frozen=True)
class SharpeTestResult:
    """Closed-form Sharpe-ratio difference test.

    H0: ``Sharpe_a == Sharpe_b``.

    * ``sharpe_a`` / ``sharpe_b`` — per-period Sharpe (no annualization).
    * ``sharpe_difference`` — ``sharpe_a - sharpe_b``.
    * ``z_statistic`` — under H0 ~ N(0, 1).
    * ``p_value`` — 2-sided p-value.
    * ``method`` — ``"memmel"`` or ``"jobson_korkie"``.
    * ``variance_estimate`` — variance of the Sharpe difference used to
      build the z stat. Surfaces it for downstream re-use (e.g. building
      CIs by hand).
    """

    sharpe_a: float
    sharpe_b: float
    sharpe_difference: float
    z_statistic: float
    p_value: float
    variance_estimate: float
    method: str
    n_obs: int

    def to_dict(self) -> dict[str, Union[float, int, str]]:
        return asdict(self)


@dataclass(frozen=True)
class MultipleTestingCorrection:
    """Bonferroni / Holm multiple-testing rejection table.

    Lets downstream report renderers show "which raw p-values survive
    the correction?" without re-doing the bookkeeping client-side.
    """

    method: str  # "bonferroni" | "holm"
    alpha: float
    raw_p_values: list[float]
    adjusted_alpha: list[float]
    rejected: list[bool]
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Loss functions used by DM
# ---------------------------------------------------------------------------


_LOSS_FN_SQUARED = "squared_error"
_LOSS_FN_ABSOLUTE = "absolute_error"
_LOSS_FN_RETURN = "negative_return"
_LOSS_FN_SHARPE = "sharpe"

SUPPORTED_LOSS_FUNCTIONS: tuple[str, ...] = (
    _LOSS_FN_SQUARED,
    _LOSS_FN_ABSOLUTE,
    _LOSS_FN_RETURN,
    _LOSS_FN_SHARPE,
)


def _loss_differential(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    loss_fn: str,
) -> np.ndarray:
    """Return the element-wise loss differential ``L_a - L_b``.

    For DM applied to strategies, we treat returns as "forecasts of
    zero" — a higher *return* is a *smaller* loss. Hence:

    * ``squared_error`` — ``returns**2`` distance from zero. Detects
      "which strategy has lower volatility about zero?". Rarely the
      right answer for return comparisons; included because DM(1995)
      uses it as the canonical example.
    * ``absolute_error`` — ``|returns|`` (same logic).
    * ``negative_return`` — ``-returns``. The most defensible choice
      when comparing strategies: strategy A is better iff its
      *expected return* exceeds B's, equivalent to E[loss_a] <
      E[loss_b] under this loss function.
    * ``sharpe`` — Sharpe-contribution-equivalent loss; we use
      ``-returns / sigma`` where sigma is the pooled std so the loss
      mean matches the Sharpe ordering.
    """

    if loss_fn == _LOSS_FN_SQUARED:
        return returns_a**2 - returns_b**2
    if loss_fn == _LOSS_FN_ABSOLUTE:
        return np.abs(returns_a) - np.abs(returns_b)
    if loss_fn == _LOSS_FN_RETURN:
        return -returns_a - (-returns_b)
    if loss_fn == _LOSS_FN_SHARPE:
        sigma = float(np.std(np.concatenate([returns_a, returns_b]), ddof=1))
        if sigma <= 1e-15:
            return np.zeros_like(returns_a)
        return -returns_a / sigma - (-returns_b / sigma)
    raise ValueError(
        f"Unsupported loss_fn={loss_fn!r}; choose from {SUPPORTED_LOSS_FUNCTIONS}"
    )


# ---------------------------------------------------------------------------
# HAC (Newey-West) variance
# ---------------------------------------------------------------------------


def _newey_west_variance(d: np.ndarray, h: int) -> float:
    """Newey-West HAC variance for the loss differential series.

    Uses the standard Bartlett kernel with truncation lag ``L = h - 1``
    (i.e. an h-step-ahead forecast eats the first h-1 autocovariances
    of the loss-differential). Mirrors the formula in Diebold-Mariano
    (1995, eq. 5).
    """

    n = d.size
    if n < 2:
        return 0.0
    d_mean = float(d.mean())
    centered = d - d_mean
    gamma0 = float((centered**2).sum()) / n
    L = max(0, h - 1)
    L = min(L, n - 1)
    var = gamma0
    for k in range(1, L + 1):
        cov_k = float((centered[k:] * centered[:-k]).sum()) / n
        weight = 1.0 - k / (L + 1)
        var += 2.0 * weight * cov_k
    # NW variance can be negative in pathological cases (negative
    # autocovariances dominating). Floor at gamma0 — DM(1995) recommends
    # the same fallback.
    if var <= 0:
        var = gamma0
    return float(var)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aligned_arrays(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert two return sequences to aligned float arrays, dropping NaN/Inf.

    The two series must already be the same length (we don't try to
    align by date — the caller is expected to feed aligned daily
    returns). Drops bars where either series is NaN/Inf so the test
    isn't polluted by missing data.
    """

    a = np.asarray(returns_a, dtype=float)
    b = np.asarray(returns_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(
            f"returns_a (len={a.size}) and returns_b (len={b.size}) "
            "must have the same length — align them on dates first"
        )
    if a.ndim != 1:
        raise ValueError("return series must be 1-D")
    finite_mask = np.isfinite(a) & np.isfinite(b)
    return a[finite_mask], b[finite_mask]


# ---------------------------------------------------------------------------
# Diebold-Mariano test
# ---------------------------------------------------------------------------


def diebold_mariano_test(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    *,
    loss_fn: str = _LOSS_FN_RETURN,
    h: int = 1,
) -> DMResult:
    """Diebold-Mariano test on two aligned return series.

    H0: ``E[L(r_a) - L(r_b)] == 0``. Under H0, the DM statistic is
    asymptotically standard normal; for finite samples we fall back to
    a t-distribution with ``n - 1`` degrees of freedom (Harvey-Leybourne
    -Newbold 1997 small-sample correction would be a future tightening).

    Parameters
    ----------
    returns_a, returns_b
        Aligned daily (or per-period) return series.
    loss_fn
        One of :data:`SUPPORTED_LOSS_FUNCTIONS`. Defaults to
        ``"negative_return"`` (strategy A is better iff its expected
        return is higher).
    h
        Forecast horizon used for HAC bandwidth selection
        (``L = h - 1``). For one-step-ahead return comparisons the
        canonical choice is ``h=1`` (i.e. no autocovariance correction);
        bump it to 5-10 for weekly-rebalanced strategies where returns
        are autocorrelated.

    Returns
    -------
    DMResult
        Carries the DM statistic, both 2-sided and 1-sided p-values,
        and the HAC variance for diagnostics.
    """

    a, b = _aligned_arrays(returns_a, returns_b)
    n = a.size
    note = ""
    if n < 3:
        return DMResult(
            dm_statistic=0.0,
            p_value=1.0,
            p_value_one_sided=1.0,
            mean_loss_differential=0.0,
            hac_variance=0.0,
            n_obs=n,
            loss_fn=loss_fn,
            h=h,
            note="insufficient_observations(<3)",
        )

    d = _loss_differential(a, b, loss_fn)
    d_mean = float(d.mean())
    nw_var = _newey_west_variance(d, h)
    if nw_var <= 1e-30:
        # Series is essentially identical: differential is degenerate.
        return DMResult(
            dm_statistic=0.0,
            p_value=1.0,
            p_value_one_sided=1.0,
            mean_loss_differential=d_mean,
            hac_variance=nw_var,
            n_obs=n,
            loss_fn=loss_fn,
            h=h,
            note="degenerate_zero_variance",
        )

    se = math.sqrt(nw_var / n)
    dm_stat = d_mean / se

    # Use t-distribution for small samples (n < 30) — gives wider tails
    # and more honest p-values when the asymptotic normal approximation
    # is shaky.
    if n < 30:
        p_two = float(2.0 * (1.0 - stats.t.cdf(abs(dm_stat), df=n - 1)))
        # 1-sided: H1: strategy A better than B → mean loss differential < 0.
        p_one = float(stats.t.cdf(dm_stat, df=n - 1))
        note = "small_sample_t_distribution"
    else:
        p_two = float(2.0 * (1.0 - stats.norm.cdf(abs(dm_stat))))
        p_one = float(stats.norm.cdf(dm_stat))

    return DMResult(
        dm_statistic=float(dm_stat),
        p_value=float(np.clip(p_two, 0.0, 1.0)),
        p_value_one_sided=float(np.clip(p_one, 0.0, 1.0)),
        mean_loss_differential=float(d_mean),
        hac_variance=float(nw_var),
        n_obs=n,
        loss_fn=loss_fn,
        h=h,
        note=note,
    )


# ---------------------------------------------------------------------------
# Politis-Romano circular block bootstrap
# ---------------------------------------------------------------------------


def politis_romano_block_bootstrap(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    *,
    block_size: int = 10,
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> BlockBootstrapResult:
    """Circular block bootstrap on the return differential ``r_a - r_b``.

    Resamples the differential series in *blocks* of length
    ``block_size`` (with wraparound) ``n_bootstrap`` times. The mean of
    each bootstrap sample produces an empirical distribution of the
    expected differential under stationary i.i.d.-block reshuffling.

    Returns the point estimate (sample mean), a (1-α)% CI from the
    bootstrap quantiles, and p-values:

    * **2-sided** p_value = ``2 * min(P(mean* <= 0), P(mean* >= 0))``
      (using the bootstrap distribution itself).
    * **1-sided** p_value = ``P(mean* <= 0)`` if observed mean > 0 else
      ``P(mean* >= 0)`` — tests "is A strictly better than B?".

    Parameters
    ----------
    returns_a, returns_b
        Aligned per-period return series.
    block_size
        Block length in periods. Standard rule-of-thumb ``L ≈ N^(1/3)``;
        the default ``10`` works for daily series of length ~300 (one
        trading year). Bumped up for shorter horizons or strongly
        autocorrelated series.
    n_bootstrap
        Number of bootstrap replicates. 1000 is enough for 95% CIs;
        10_000 for tail-sensitive tests.
    ci_level
        Coverage of the returned CI (default 0.95).
    seed
        RNG seed for determinism.
    """

    a, b = _aligned_arrays(returns_a, returns_b)
    n = a.size
    if n < 2:
        return BlockBootstrapResult(
            mean_diff=0.0,
            ci_low=0.0,
            ci_high=0.0,
            ci_level=ci_level,
            p_value_two_sided=1.0,
            p_value_one_sided=1.0,
            block_size=block_size,
            n_bootstrap=n_bootstrap,
            n_obs=n,
        )
    if block_size < 1:
        raise ValueError(f"block_size must be >= 1; got {block_size}")
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be >= 1; got {n_bootstrap}")
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0,1); got {ci_level}")

    diff = a - b
    sample_mean = float(diff.mean())
    rng = np.random.default_rng(seed)

    effective_block = min(block_size, n)
    # Number of blocks per replicate — we want output length ~= n. Use
    # ceil so we always produce at least n samples, then truncate.
    n_blocks = math.ceil(n / effective_block)

    boot_means = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        starts = rng.integers(0, n, size=n_blocks)
        # Build the resampled differential by concatenating blocks with
        # wraparound. Vectorised via fancy indexing for speed.
        offsets = np.arange(effective_block)
        idx_matrix = (starts[:, None] + offsets[None, :]) % n  # (n_blocks, block_size)
        sample = diff[idx_matrix.flatten()][:n]
        boot_means[i] = float(sample.mean())

    boot_means.sort()
    alpha = 1.0 - ci_level
    lo = float(np.quantile(boot_means, alpha / 2.0))
    hi = float(np.quantile(boot_means, 1.0 - alpha / 2.0))

    # p-values via the bootstrap distribution. Re-centre at zero (the
    # null) so we test "given H0: mean=0, how likely is |sample_mean|?".
    centered = boot_means - sample_mean
    # 2-sided: probability that a centred-at-zero bootstrap sample lies
    # at least |sample_mean| away from 0.
    p_two = float(np.mean(np.abs(centered) >= abs(sample_mean)))
    # 1-sided: probability that the centred bootstrap mean exceeds the
    # observed deviation in the OPPOSITE direction of the sample mean.
    if sample_mean >= 0:
        p_one = float(np.mean(centered >= sample_mean))
    else:
        p_one = float(np.mean(centered <= sample_mean))

    return BlockBootstrapResult(
        mean_diff=sample_mean,
        ci_low=lo,
        ci_high=hi,
        ci_level=ci_level,
        p_value_two_sided=float(np.clip(p_two, 0.0, 1.0)),
        p_value_one_sided=float(np.clip(p_one, 0.0, 1.0)),
        block_size=effective_block,
        n_bootstrap=n_bootstrap,
        n_obs=n,
    )


# ---------------------------------------------------------------------------
# Sharpe-ratio difference test (Memmel / Jobson-Korkie)
# ---------------------------------------------------------------------------


def sharpe_ratio_test(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    *,
    method: str = "memmel",
) -> SharpeTestResult:
    """Test whether two strategies have equal Sharpe ratios.

    The Jobson-Korkie (1981) test produces a variance estimator for the
    Sharpe difference; Memmel (2003) corrects a sign / typo in the JK
    formula. Both reduce to a z-statistic that is asymptotically N(0,1)
    under H0.

    For two return series ``r_a``, ``r_b`` with means ``mu_a``,
    ``mu_b``, std devs ``sigma_a``, ``sigma_b``, and Pearson correlation
    ``rho``, Memmel's variance estimate is::

        var_diff = (1/n) * [
            2 * (1 - rho)
            + 0.5 * (Sharpe_a^2 + Sharpe_b^2 - 2*Sharpe_a*Sharpe_b*rho^2)
        ]

    The z-statistic is ``(Sharpe_a - Sharpe_b) / sqrt(var_diff)``.

    Parameters
    ----------
    returns_a, returns_b
        Aligned per-period return series.
    method
        ``"memmel"`` (default; recommended) or ``"jobson_korkie"``
        (kept for reproducibility against older papers — drops the
        ``-2*Sharpe_a*Sharpe_b*rho^2`` cross term).
    """

    if method not in {"memmel", "jobson_korkie"}:
        raise ValueError(
            f"method must be 'memmel' or 'jobson_korkie'; got {method!r}"
        )
    a, b = _aligned_arrays(returns_a, returns_b)
    n = a.size
    if n < 3:
        return SharpeTestResult(
            sharpe_a=0.0,
            sharpe_b=0.0,
            sharpe_difference=0.0,
            z_statistic=0.0,
            p_value=1.0,
            variance_estimate=0.0,
            method=method,
            n_obs=n,
        )

    mu_a = float(a.mean())
    mu_b = float(b.mean())
    sigma_a = float(a.std(ddof=1))
    sigma_b = float(b.std(ddof=1))
    if sigma_a < 1e-15 or sigma_b < 1e-15:
        return SharpeTestResult(
            sharpe_a=0.0 if sigma_a < 1e-15 else mu_a / sigma_a,
            sharpe_b=0.0 if sigma_b < 1e-15 else mu_b / sigma_b,
            sharpe_difference=0.0,
            z_statistic=0.0,
            p_value=1.0,
            variance_estimate=0.0,
            method=method,
            n_obs=n,
        )

    sharpe_a = mu_a / sigma_a
    sharpe_b = mu_b / sigma_b
    # Pearson correlation (ddof=1 alignment with the std estimators).
    rho_matrix = np.corrcoef(a, b)
    rho = float(rho_matrix[0, 1]) if rho_matrix.size == 4 else 0.0
    if not math.isfinite(rho):
        rho = 0.0

    diff = sharpe_a - sharpe_b

    if method == "memmel":
        var_diff = (
            2.0 * (1.0 - rho)
            + 0.5 * (sharpe_a**2 + sharpe_b**2 - 2.0 * sharpe_a * sharpe_b * rho**2)
        ) / n
    else:
        # Jobson-Korkie (1981) — original (kept for backward-compat).
        var_diff = (
            2.0 * (1.0 - rho)
            + 0.5 * (sharpe_a**2 + sharpe_b**2 - sharpe_a * sharpe_b * (1.0 + rho**2))
        ) / n

    if var_diff <= 1e-30:
        return SharpeTestResult(
            sharpe_a=sharpe_a,
            sharpe_b=sharpe_b,
            sharpe_difference=diff,
            z_statistic=0.0,
            p_value=1.0,
            variance_estimate=float(var_diff),
            method=method,
            n_obs=n,
        )

    z = diff / math.sqrt(var_diff)
    p_two = float(2.0 * (1.0 - stats.norm.cdf(abs(z))))
    return SharpeTestResult(
        sharpe_a=float(sharpe_a),
        sharpe_b=float(sharpe_b),
        sharpe_difference=float(diff),
        z_statistic=float(z),
        p_value=float(np.clip(p_two, 0.0, 1.0)),
        variance_estimate=float(var_diff),
        method=method,
        n_obs=n,
    )


# ---------------------------------------------------------------------------
# Multiple-testing corrections
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------


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


__all__ = [
    "SUPPORTED_LOSS_FUNCTIONS",
    "BlockBootstrapResult",
    "DMResult",
    "MultipleTestingCorrection",
    "SharpeTestResult",
    "bonferroni_correct",
    "diebold_mariano_test",
    "holm_correct",
    "politis_romano_block_bootstrap",
    "results_to_dataframe",
    "sharpe_ratio_test",
]
