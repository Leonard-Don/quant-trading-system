"""Result dataclasses for the formal statistical hypothesis tests.

These dataclasses are the public return types of the statistical-test
functions in the sibling modules. They are re-exported from
:mod:`src.backtest.strategy_statistical_tests` so the original import
path is unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Union


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

    * ``note`` — free-form caveat, e.g. ``"insufficient_observations"``
      when the series is too short relative to ``block_size`` for the
      bootstrap distribution to be meaningful.  Downstream consumers
      should treat any non-empty note as a low-confidence flag.
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
    note: str = ""

    def to_dict(self) -> dict[str, Union[float, int, str]]:
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
