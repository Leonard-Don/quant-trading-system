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
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Union

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


@dataclass(frozen=True)
class MinimumDetectableEffect:
    """Inversion of the DM test: the smallest edge the sample *could* detect.

    The DM tests in this module answer "is the observed spread
    significant?" and the walk-forward summary reports the honest
    *no* — the ETF rotation strategy is statistically indistinguishable
    from buy-and-hold on the 5y sample. :func:`minimum_detectable_effect`
    answers the dual question: holding the *observed HAC variance
    structure* fixed, what *true* effect size would the DM test need to
    reject H0 at the requested power? That number is the **Minimum
    Detectable Effect (MDE)** — a falsifiable alpha target.

    All three effect-size views describe the *same* underlying threshold;
    they differ only in units:

    * ``mde_ir`` — the MDE expressed as an annualised **Information
      Ratio** (annualised excess return ÷ annualised tracking error).
      This is the annualisation-invariant headline: ``mde_ir`` does not
      depend on how many rebalances per year you assume.
    * ``mde_excess_return_annual`` — the MDE as an annualised excess
      return (geometric-free, simple sum of per-period means × periods).
      *Does* depend on ``periods_per_year``.
    * ``mde_excess_return_per_period`` — the MDE as a per-rebalance
      excess return; the rawest form, multiply by ``periods_per_year``
      to annualise.

    Diagnostics:

    * ``observed_ir`` — the sample IR actually realised (signed). When
      ``|observed_ir| < mde_ir`` the strategy sits *inside* the noise
      floor: you cannot tell it apart from buy-and-hold on this sample,
      regardless of which direction the point estimate leans.
    * ``required_ncp`` — the non-centrality parameter the ``|DM|``
      statistic must reach, solved from the same two-tail forward-power
      equation used by :func:`dm_power_for_information_ratio`.
    * ``power``/``alpha`` — the inputs the MDE was solved for.
    * ``n_obs`` — sample size (rebalance periods) used.
    * ``hac_variance`` — the per-period Newey-West HAC variance of the
      loss differential that anchors the inversion.
    * ``annualized_tracking_error`` — ``sqrt(hac_variance * periods_per_year)``;
      the volatility of the strategy-minus-benchmark return stream.
    * ``periods_per_year`` — annualisation factor (52 for weekly
      rebalancing, ≈252 for daily).
    * ``note`` — free-form caveat (e.g. degenerate-variance fallback).

    The relationship that makes this exact rather than a simulation:
    the DM statistic is ``DM = sqrt(n) * (d_mean / sqrt(hac_var))`` and
    the signed strategy-excess Information Ratio is ``IR =
    (-d_mean / sqrt(hac_var)) * sqrt(periods_per_year)``, so
    ``observed_IR = -DM * sqrt(periods_per_year / n)``. The MDE is an
    unsigned threshold, therefore ``mde_ir = required_ncp *
    sqrt(periods_per_year / n)``.
    """

    mde_ir: float
    mde_excess_return_annual: float
    mde_excess_return_per_period: float
    observed_ir: float
    observed_excess_return_annual: float
    required_ncp: float
    power: float
    alpha: float
    n_obs: int
    hac_variance: float
    annualized_tracking_error: float
    periods_per_year: float
    note: str = ""

    def to_dict(self) -> dict[str, Union[float, int, str]]:
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
# Power-analysis inversion — Minimum Detectable Effect
# ---------------------------------------------------------------------------


def _required_noncentrality(*, alpha: float, power: float) -> float:
    """Non-centrality the ``|DM|`` statistic must reach for the target power.

    For a two-sided z-test the rejection region is ``|DM| > z_{1-α/2}``.
    Under H1 the statistic is (asymptotically) ``N(ncp, 1)`` with
    ``ncp = |true effect| / SE``. The forward power calculation keeps
    both rejection tails, so the inverse solves the same equation
    numerically:

    ``power = Φ(ncp - z_{1-α/2}) + Φ(-ncp - z_{1-α/2})``.
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    if not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0,1); got {power}")
    z_alpha = float(stats.norm.ppf(1.0 - alpha / 2.0))
    if power <= alpha:
        return 0.0

    lower = 0.0
    upper = max(z_alpha + float(stats.norm.ppf(power)), 1.0)
    while _two_sided_normal_power(upper, z_alpha) < power:
        upper *= 2.0

    for _ in range(80):
        mid = (lower + upper) / 2.0
        if _two_sided_normal_power(mid, z_alpha) < power:
            lower = mid
        else:
            upper = mid
    return float(upper)


def _two_sided_normal_power(ncp: float, z_alpha: float) -> float:
    """Power for ``|N(ncp, 1)| > z_alpha``."""

    upper = float(stats.norm.cdf(float(ncp) - z_alpha))
    lower = float(stats.norm.cdf(-float(ncp) - z_alpha))
    return float(np.clip(upper + lower, 0.0, 1.0))


def minimum_detectable_effect(
    hac_variance: float,
    n_obs: int,
    *,
    observed_mean_differential: float = 0.0,
    alpha: float = 0.05,
    power: float = 0.80,
    periods_per_year: float = 52.0,
) -> MinimumDetectableEffect:
    """Invert the Diebold-Mariano test: solve for the smallest detectable edge.

    The DM test reports whether an *observed* spread is significant.
    This function answers the dual, design-time question — given the
    *variance structure already measured on the sample*, what *true*
    effect size would the DM test need before it rejects H0 at the
    requested ``power``? That threshold is the **Minimum Detectable
    Effect**: below it, a strategy is statistically inseparable from its
    benchmark on this sample no matter how the point estimate leans.

    The math is numerically solved (no simulation). The DM statistic for
    ``loss_fn="negative_return"`` is ``DM = d_mean / sqrt(hac_var / n)``
    where ``d_mean`` is the mean loss differential and ``-d_mean`` is the
    per-period excess return. Under H1 with a true per-period excess
    return ``μ_e``, the statistic ``|DM|`` has non-centrality
    ``ncp = |μ_e| / sqrt(hac_var / n)``. Setting ``ncp`` equal to the
    required value :func:`_required_noncentrality` and solving::

        mde_excess_return_per_period = required_ncp * sqrt(hac_var / n)

    The Information-Ratio form is annualisation-invariant::

        mde_ir = required_ncp * sqrt(periods_per_year / n)

    The signed observed strategy-excess IR carries the opposite sign from
    the negative-return loss differential:
    ``observed_IR = -DM * sqrt(periods_per_year / n)``. The MDE itself
    is unsigned, so it uses the required non-centrality magnitude rather
    than the observed DM sign. The per-year factor in the numerator's
    annualised mean and the denominator's annualised tracking error both
    scale by ``sqrt(periods_per_year)``, so the only sample-size
    dependence left is ``sqrt(1/n)``.

    Parameters
    ----------
    hac_variance
        Per-period Newey-West HAC variance of the loss differential —
        i.e. :attr:`DMResult.hac_variance`. This is *the* quantity the
        inversion holds fixed: it captures both the raw dispersion of
        the strategy-minus-benchmark return stream and the autocorrelation
        penalty the HAC estimator applies.
    n_obs
        Number of rebalance periods in the sample (:attr:`DMResult.n_obs`).
    observed_mean_differential
        The sample mean loss differential (:attr:`DMResult.mean_loss_differential`).
        Only used to populate the ``observed_ir`` /
        ``observed_excess_return_annual`` diagnostics — it does **not**
        affect the MDE itself. Defaults to 0.0 (diagnostics then read 0).
    alpha
        Two-sided significance level. Default 0.05.
    power
        Target statistical power (1 - β). Default 0.80 — the
        conventional "80% power" design point.
    periods_per_year
        Annualisation factor: rebalances per year. 52 for the weekly
        cadence the ETF rotation walk-forward uses; ≈252 for daily.

    Returns
    -------
    MinimumDetectableEffect
        The MDE in IR / annualised-return / per-period units plus the
        observed-effect diagnostics and the inversion inputs.

    Raises
    ------
    ValueError
        If ``hac_variance`` is negative/non-finite, ``alpha`` or ``power``
        are outside ``(0, 1)``, ``periods_per_year`` is not positive, or
        ``n_obs < 2``.
    """

    if periods_per_year <= 0.0:
        raise ValueError(
            f"periods_per_year must be > 0; got {periods_per_year}"
        )
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2 to invert the test; got {n_obs}")

    required_ncp = _required_noncentrality(alpha=alpha, power=power)

    note = ""
    hv = float(hac_variance)
    if not math.isfinite(hv) or hv < 0.0:
        raise ValueError(f"hac_variance must be finite and >= 0; got {hac_variance}")
    if hv <= 1e-30:
        # Degenerate variance — the differential is essentially constant,
        # so any non-zero effect is "infinitely" detectable. Report zeros
        # and a note rather than dividing by ~0.
        note = "degenerate_zero_variance"
        se = 0.0
        ann_te = 0.0
        mde_per_period = 0.0
        mde_annual = 0.0
        mde_ir = 0.0
        observed_ir = 0.0
        observed_annual = 0.0
    else:
        se = math.sqrt(hv / n_obs)
        ann_te = math.sqrt(hv * periods_per_year)
        mde_per_period = required_ncp * se
        mde_annual = mde_per_period * periods_per_year
        mde_ir = required_ncp * math.sqrt(periods_per_year / n_obs)
        # Observed diagnostics. d_mean is the loss differential; for
        # loss_fn="negative_return" the excess return is -d_mean.
        observed_excess_per_period = -float(observed_mean_differential)
        observed_annual = observed_excess_per_period * periods_per_year
        observed_ir = (
            (observed_excess_per_period / math.sqrt(hv))
            * math.sqrt(periods_per_year)
        )

    return MinimumDetectableEffect(
        mde_ir=float(mde_ir),
        mde_excess_return_annual=float(mde_annual),
        mde_excess_return_per_period=float(mde_per_period),
        observed_ir=float(observed_ir),
        observed_excess_return_annual=float(observed_annual),
        required_ncp=float(required_ncp),
        power=float(power),
        alpha=float(alpha),
        n_obs=int(n_obs),
        hac_variance=hv,
        annualized_tracking_error=float(ann_te),
        periods_per_year=float(periods_per_year),
        note=note,
    )


def minimum_detectable_effect_from_dm(
    dm_result: DMResult,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    periods_per_year: float = 52.0,
) -> MinimumDetectableEffect:
    """Convenience: invert a :class:`DMResult` straight into an MDE.

    Pulls ``hac_variance``, ``n_obs`` and ``mean_loss_differential`` off
    a completed :func:`diebold_mariano_test` result so the caller does
    not have to unpack them by hand. Equivalent to calling
    :func:`minimum_detectable_effect` with those three fields.

    Raises ``ValueError`` if the DM result used a loss function other
    than ``"negative_return"`` — the IR / excess-return interpretation
    of the inversion only holds for that loss (squared-error and the
    others measure a different quantity).
    """

    if dm_result.loss_fn != _LOSS_FN_RETURN:
        raise ValueError(
            "minimum_detectable_effect_from_dm requires a DMResult computed "
            f"with loss_fn={_LOSS_FN_RETURN!r}; got {dm_result.loss_fn!r}. "
            "The excess-return / Information-Ratio inversion is only "
            "meaningful for the negative-return loss."
        )
    return minimum_detectable_effect(
        dm_result.hac_variance,
        dm_result.n_obs,
        observed_mean_differential=dm_result.mean_loss_differential,
        alpha=alpha,
        power=power,
        periods_per_year=periods_per_year,
    )


def dm_power_for_information_ratio(
    information_ratio: float,
    n_obs: int,
    *,
    alpha: float = 0.05,
    periods_per_year: float = 52.0,
) -> float:
    """Forward power calculation: probability the DM test rejects H0.

    The inverse of :func:`minimum_detectable_effect` — given a *true*
    annualised Information Ratio and a sample size, return the two-sided
    DM test's power at level ``alpha``. Used to sanity-check the MDE
    (feeding ``mde_ir`` back in must yield ≈ the ``power`` it was solved
    for) and to draw power curves.

    Under H1 the non-centrality is ``ncp = |IR| * sqrt(n / periods_per_year)``
    and ``power = Φ(ncp - z_{1-α/2}) + Φ(-ncp - z_{1-α/2})`` (both tails).
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    if periods_per_year <= 0.0:
        raise ValueError(
            f"periods_per_year must be > 0; got {periods_per_year}"
        )
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2; got {n_obs}")
    z_alpha = float(stats.norm.ppf(1.0 - alpha / 2.0))
    ncp = abs(float(information_ratio)) * math.sqrt(n_obs / periods_per_year)
    return _two_sided_normal_power(ncp, z_alpha)


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


@dataclass(frozen=True)
class WalkForwardTestResult:
    """One row of the walk-forward statistical-tests DataFrame.

    Mirrors the columns in :func:`walk_forward_statistical_tests`'s output
    so callers can construct rows in-place when extending the pipeline
    (e.g. adding new statistical tests).
    """

    window_id: int
    start_date: str
    end_date: str
    n_obs: int
    dm_stat: float
    dm_pvalue: float
    sharpe_z: float
    sharpe_pvalue: float
    boot_lower: float
    boot_upper: float
    boot_pvalue: float

    def to_dict(self) -> dict[str, Union[float, int, str]]:
        return asdict(self)


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


__all__ = [
    "SUPPORTED_LOSS_FUNCTIONS",
    "BlockBootstrapResult",
    "DMResult",
    "MinimumDetectableEffect",
    "MultipleTestingCorrection",
    "SharpeTestResult",
    "WalkForwardTestResult",
    "bonferroni_correct",
    "diebold_mariano_test",
    "dm_power_for_information_ratio",
    "holm_correct",
    "minimum_detectable_effect",
    "minimum_detectable_effect_from_dm",
    "politis_romano_block_bootstrap",
    "results_to_dataframe",
    "sharpe_ratio_test",
    "walk_forward_statistical_tests",
]
