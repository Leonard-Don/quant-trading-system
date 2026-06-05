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

Implementation note
-------------------
The implementations live in the focused sibling modules under
:mod:`src.backtest.statistical_tests` (``results``, ``core``,
``corrections``, ``power``, ``reporting``). They are re-exported here so
the original ``src.backtest.strategy_statistical_tests`` import path and
its public (and private) surface stay byte-for-byte compatible.
"""

from __future__ import annotations

from src.backtest.statistical_tests.core import (
    _LOSS_FN_ABSOLUTE,
    _LOSS_FN_RETURN,
    _LOSS_FN_SHARPE,
    _LOSS_FN_SQUARED,
    SUPPORTED_LOSS_FUNCTIONS,
    _aligned_arrays,
    _loss_differential,
    _newey_west_variance,
    _validate_hac_horizon,
    diebold_mariano_test,
    logger,
    politis_romano_block_bootstrap,
    sharpe_ratio_test,
)
from src.backtest.statistical_tests.corrections import (
    bonferroni_correct,
    holm_correct,
)
from src.backtest.statistical_tests.power import (
    _required_noncentrality,
    _two_sided_normal_power,
    dm_power_for_information_ratio,
    minimum_detectable_effect,
    minimum_detectable_effect_from_dm,
)
from src.backtest.statistical_tests.reporting import (
    _iter_walk_forward_bounds,
    _resolve_period_index,
    results_to_dataframe,
    walk_forward_statistical_tests,
)
from src.backtest.statistical_tests.results import (
    BlockBootstrapResult,
    DMResult,
    MinimumDetectableEffect,
    MultipleTestingCorrection,
    SharpeTestResult,
    WalkForwardTestResult,
)

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

# Private helpers re-exported for backward compatibility with any callers
# that reached into module internals. Bound to a throwaway tuple so linters
# treat the imports as used while keeping them importable from this module.
_PRIVATE_REEXPORTS = (
    _LOSS_FN_SQUARED,
    _LOSS_FN_ABSOLUTE,
    _LOSS_FN_RETURN,
    _LOSS_FN_SHARPE,
    _aligned_arrays,
    _iter_walk_forward_bounds,
    _loss_differential,
    _newey_west_variance,
    _required_noncentrality,
    _resolve_period_index,
    _two_sided_normal_power,
    _validate_hac_horizon,
    logger,
)
