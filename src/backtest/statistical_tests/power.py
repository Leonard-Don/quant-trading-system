"""Power-analysis inversion: the Minimum Detectable Effect and the forward
DM-test power calculation.

Extracted verbatim from ``strategy_statistical_tests`` and re-exported there
so the public import path is unchanged.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from .core import _LOSS_FN_RETURN
from .results import DMResult, MinimumDetectableEffect


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
        ``n_obs`` / ``observed_mean_differential`` are non-finite, or
        ``n_obs`` is less than 2.
    """

    if not math.isfinite(periods_per_year) or periods_per_year <= 0.0:
        raise ValueError(
            f"periods_per_year must be > 0; got {periods_per_year}"
        )
    n_obs_value = float(n_obs)
    if not math.isfinite(n_obs_value) or n_obs_value < 2:
        raise ValueError(f"n_obs must be >= 2 to invert the test; got {n_obs}")
    observed_mean_value = float(observed_mean_differential)
    if not math.isfinite(observed_mean_value):
        raise ValueError(
            "observed_mean_differential must be finite; "
            f"got {observed_mean_differential}"
        )

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
        se = math.sqrt(hv / n_obs_value)
        ann_te = math.sqrt(hv * periods_per_year)
        mde_per_period = required_ncp * se
        mde_annual = mde_per_period * periods_per_year
        mde_ir = required_ncp * math.sqrt(periods_per_year / n_obs_value)
        # Observed diagnostics. d_mean is the loss differential; for
        # loss_fn="negative_return" the excess return is -d_mean.
        observed_excess_per_period = -observed_mean_value
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
        n_obs=int(n_obs_value),
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
    if not math.isfinite(periods_per_year) or periods_per_year <= 0.0:
        raise ValueError(
            f"periods_per_year must be > 0; got {periods_per_year}"
        )
    n_obs_value = float(n_obs)
    if not math.isfinite(n_obs_value) or n_obs_value < 2:
        raise ValueError(f"n_obs must be >= 2; got {n_obs}")
    ir = float(information_ratio)
    if not math.isfinite(ir):
        raise ValueError(f"information_ratio must be finite; got {information_ratio}")
    z_alpha = float(stats.norm.ppf(1.0 - alpha / 2.0))
    ncp = abs(ir) * math.sqrt(n_obs_value / periods_per_year)
    return _two_sided_normal_power(ncp, z_alpha)
