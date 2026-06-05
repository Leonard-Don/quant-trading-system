"""Core statistical-test primitives: loss functions, HAC variance, alignment
helpers, and the three orthogonal pairwise tests (Diebold-Mariano,
Politis-Romano block bootstrap, Memmel/Jobson-Korkie Sharpe difference).

Extracted verbatim from ``strategy_statistical_tests`` and re-exported there
so the public import path is unchanged.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

from .results import BlockBootstrapResult, DMResult, SharpeTestResult

logger = logging.getLogger(__name__)


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


def _validate_hac_horizon(h: int) -> int:
    """Validate the Newey-West forecast horizon used by the DM test."""

    h_value = float(h)
    if not math.isfinite(h_value) or h_value < 1 or not h_value.is_integer():
        raise ValueError(f"h must be a finite integer >= 1; got {h}")
    return int(h_value)


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

    h_value = _validate_hac_horizon(h)
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
            h=h_value,
            note="insufficient_observations(<3)",
        )

    d = _loss_differential(a, b, loss_fn)
    d_mean = float(d.mean())
    nw_var = _newey_west_variance(d, h_value)
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
            h=h_value,
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
        h=h_value,
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

    # Insufficient-observations guard: when n_blocks < 3 (fewer than 3
    # independent chunks), every bootstrap replicate is a near-identity
    # permutation of the full series.  The centred bootstrap distribution
    # collapses toward all-zero, causing the 2-sided p-value to be
    # spuriously 0.0 — a false "maximally significant" result that fires
    # precisely when the sample is too short to conclude anything.
    #
    # Threshold rule: require at least 3 blocks so that the empirical
    # bootstrap distribution has at least 3 distinct support points.  This
    # catches both the degenerate case (block_size >= n_obs → n_blocks = 1)
    # and the near-degenerate case (n_blocks = 2, which gives essentially
    # binary resampling with negligible distributional spread).
    #
    # We do NOT silently clamp block_size — that hides the condition and
    # makes the result look well-supported.  Instead we return an honest
    # "no signal" result with p=1.0 and flag it via the note field.
    _MIN_BLOCKS = 3
    if n_blocks < _MIN_BLOCKS:
        _note = (
            f"insufficient_observations: n_obs={n}, block_size={effective_block}, "
            f"n_blocks={n_blocks} < {_MIN_BLOCKS}; bootstrap distribution is "
            "degenerate — p-values suppressed"
        )
        logger.debug(_note)
        return BlockBootstrapResult(
            mean_diff=sample_mean,
            ci_low=float("nan"),
            ci_high=float("nan"),
            ci_level=ci_level,
            p_value_two_sided=1.0,
            p_value_one_sided=1.0,
            block_size=effective_block,
            n_bootstrap=n_bootstrap,
            n_obs=n,
            note=_note,
        )

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
