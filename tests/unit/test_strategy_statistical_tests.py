"""Unit tests for the formal statistical tests module.

These tests focus on:

1. *Calibration* — identical series produce p ≈ 1, deliberately separated
   series produce p < 0.05 (asymptotically; tested with large N).
2. *Edge cases* — empty inputs / single observation / NaN returns must
   NOT throw; they should return well-defined "no signal" results.
3. *Determinism* — block bootstrap with a fixed seed is reproducible.
4. *Test mechanics* — HAC bandwidth tuning changes the variance estimate;
   2-sided vs 1-sided p-values track sign of the differential; multiple-
   testing corrections behave as advertised on a Bonferroni example.

All tests use NumPy RNG with explicit seeds — no flaky failures. They
also run in under a second each (the block bootstrap is the slowest
piece and is small-N here).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.backtest.strategy_statistical_tests import (
    BlockBootstrapResult,
    DMResult,
    MinimumDetectableEffect,
    SharpeTestResult,
    bonferroni_correct,
    diebold_mariano_test,
    dm_power_for_information_ratio,
    holm_correct,
    minimum_detectable_effect,
    minimum_detectable_effect_from_dm,
    politis_romano_block_bootstrap,
    results_to_dataframe,
    sharpe_ratio_test,
)

# ---------------------------------------------------------------------------
# Diebold-Mariano test
# ---------------------------------------------------------------------------


def test_dm_identical_series_returns_no_difference() -> None:
    """Two identical series → p_value ≈ 1.0 and DM ≈ 0."""

    rng = np.random.default_rng(seed=0)
    returns = rng.normal(0.0005, 0.01, size=250).tolist()

    result = diebold_mariano_test(returns, returns, loss_fn="negative_return")

    assert isinstance(result, DMResult)
    # Identical series → degenerate variance → DM stat at 0.
    assert result.dm_statistic == 0.0
    assert result.p_value == pytest.approx(1.0)
    assert result.n_obs == 250


def test_dm_clear_winner_yields_significant_p_value() -> None:
    """Synthetic strategy A clearly better than B → p < 0.05.

    Both series have independent noise plus A gets a +20 bps daily edge.
    With N=1000 the asymptotic normal regime applies cleanly.
    """

    rng = np.random.default_rng(seed=1)
    a_noise = rng.normal(0.0, 0.01, size=1000)
    b_noise = rng.normal(0.0, 0.01, size=1000)
    returns_a = (a_noise + 0.002).tolist()  # +20 bps daily edge
    returns_b = b_noise.tolist()

    result = diebold_mariano_test(
        returns_a, returns_b, loss_fn="negative_return", h=1,
    )

    # A is clearly better; loss differential should be strongly negative.
    assert result.mean_loss_differential < 0.0
    # 2-sided p-value should clearly reject the null at α=0.05.
    assert result.p_value < 0.05
    # 1-sided "A is better" p-value should also reject cleanly.
    assert result.p_value_one_sided < 0.05


def test_dm_unknown_loss_function_raises() -> None:
    """Bogus loss_fn string must raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported loss_fn"):
        diebold_mariano_test([0.1, 0.2, 0.3], [0.1, 0.1, 0.1], loss_fn="invalid")


def test_dm_empty_input_returns_neutral_result() -> None:
    """Edge case: empty series produces a "no signal" result, no crash."""

    result = diebold_mariano_test([], [])
    assert result.n_obs == 0
    assert result.p_value == 1.0
    assert "insufficient" in result.note


def test_dm_handles_nan_returns_by_dropping() -> None:
    """NaN bars are dropped pairwise — the test still runs."""

    rng = np.random.default_rng(seed=2)
    a = rng.normal(0.001, 0.01, size=100)
    b = rng.normal(0.001, 0.01, size=100)
    a[3] = np.nan
    b[7] = np.inf

    result = diebold_mariano_test(a.tolist(), b.tolist())
    # 2 bars were poisoned (one NaN, one Inf at different positions) so 98 finite.
    assert result.n_obs == 98


def test_dm_hac_bandwidth_changes_variance_estimate() -> None:
    """Higher ``h`` (more autocovariance terms) changes the HAC variance.

    On an autocorrelated series the NW variance with h=10 differs from
    h=1 — confirms the bandwidth parameter is actually wired through.
    """

    rng = np.random.default_rng(seed=3)
    eps = rng.normal(0.0, 0.01, size=500)
    # AR(1) with rho=0.5 — strong autocorrelation.
    a = np.zeros(500)
    for t in range(1, 500):
        a[t] = 0.5 * a[t - 1] + eps[t]
    b = rng.normal(0.0, 0.01, size=500)

    r_h1 = diebold_mariano_test(a.tolist(), b.tolist(), h=1)
    r_h10 = diebold_mariano_test(a.tolist(), b.tolist(), h=10)

    assert r_h1.hac_variance != pytest.approx(r_h10.hac_variance, rel=1e-3)


def test_dm_loss_function_supports_all_documented_options() -> None:
    """All advertised loss-fn names are accepted without raising."""

    rng = np.random.default_rng(seed=4)
    a = rng.normal(0.001, 0.01, size=120).tolist()
    b = rng.normal(0.0, 0.01, size=120).tolist()
    for fn in ("squared_error", "absolute_error", "negative_return", "sharpe"):
        result = diebold_mariano_test(a, b, loss_fn=fn)
        assert result.loss_fn == fn
        assert 0.0 <= result.p_value <= 1.0


# ---------------------------------------------------------------------------
# Politis-Romano circular block bootstrap
# ---------------------------------------------------------------------------


def test_block_bootstrap_identical_series_centered_at_zero() -> None:
    """Two identical series → mean differential = 0 and CI brackets 0."""

    rng = np.random.default_rng(seed=10)
    returns = rng.normal(0.0, 0.01, size=300).tolist()
    result = politis_romano_block_bootstrap(returns, returns, n_bootstrap=500)

    assert isinstance(result, BlockBootstrapResult)
    assert result.mean_diff == pytest.approx(0.0, abs=1e-15)
    assert result.ci_low <= 0.0 <= result.ci_high
    # p-value for "differential is non-zero" should be ~1 since obs == 0.
    assert result.p_value_two_sided >= 0.9


def test_block_bootstrap_clear_winner_detected() -> None:
    """A strategy with clear positive drift produces a tight positive CI."""

    rng = np.random.default_rng(seed=11)
    a_noise = rng.normal(0.0, 0.01, size=500)
    b_noise = rng.normal(0.0, 0.01, size=500)
    a = (a_noise + 0.002).tolist()  # +20 bps edge
    b = b_noise.tolist()
    result = politis_romano_block_bootstrap(
        a, b, block_size=10, n_bootstrap=1000, seed=11,
    )

    assert result.mean_diff > 0.0
    # CI for the differential should be well clear of zero.
    assert result.ci_low > 0.0
    # 1-sided p-value should reject the null cleanly.
    assert result.p_value_one_sided < 0.05


def test_block_bootstrap_is_deterministic_with_seed() -> None:
    """Fixed seed → identical results across two calls."""

    rng = np.random.default_rng(seed=12)
    a = rng.normal(0.0, 0.01, size=200).tolist()
    b = rng.normal(0.0, 0.01, size=200).tolist()
    r1 = politis_romano_block_bootstrap(a, b, seed=99, n_bootstrap=300)
    r2 = politis_romano_block_bootstrap(a, b, seed=99, n_bootstrap=300)
    assert r1.mean_diff == r2.mean_diff
    assert r1.ci_low == r2.ci_low
    assert r1.ci_high == r2.ci_high


def test_block_bootstrap_validates_inputs() -> None:
    """Bad block_size / n_bootstrap / ci_level raise ValueError."""

    with pytest.raises(ValueError, match="block_size"):
        politis_romano_block_bootstrap([0.1, 0.2], [0.1, 0.1], block_size=0)
    with pytest.raises(ValueError, match="n_bootstrap"):
        politis_romano_block_bootstrap([0.1, 0.2], [0.1, 0.1], n_bootstrap=0)
    with pytest.raises(ValueError, match="ci_level"):
        politis_romano_block_bootstrap([0.1, 0.2], [0.1, 0.1], ci_level=1.5)


def test_block_bootstrap_empty_input_returns_neutral_result() -> None:
    """Edge case: empty input → zero diff, neutral p-values."""

    result = politis_romano_block_bootstrap([], [])
    assert result.n_obs == 0
    assert result.mean_diff == 0.0
    assert result.p_value_two_sided == 1.0


# ---------------------------------------------------------------------------
# Sharpe-ratio difference test
# ---------------------------------------------------------------------------


def test_sharpe_test_identical_series_no_difference() -> None:
    """Two identical series → Sharpe difference = 0 and p ≈ 1."""

    rng = np.random.default_rng(seed=20)
    returns = rng.normal(0.0005, 0.01, size=250).tolist()
    result = sharpe_ratio_test(returns, returns)
    assert isinstance(result, SharpeTestResult)
    assert result.sharpe_difference == pytest.approx(0.0, abs=1e-12)
    assert result.p_value == pytest.approx(1.0)


def test_sharpe_test_clear_winner_detected() -> None:
    """Strategy with much higher mean → Sharpe difference is significant."""

    rng = np.random.default_rng(seed=21)
    a = rng.normal(0.003, 0.01, size=500).tolist()  # higher mean
    b = rng.normal(0.0, 0.01, size=500).tolist()
    result = sharpe_ratio_test(a, b, method="memmel")
    assert result.sharpe_a > result.sharpe_b
    assert result.p_value < 0.05


def test_sharpe_test_supports_both_methods() -> None:
    """Memmel and Jobson-Korkie both accepted, both return valid p-values."""

    rng = np.random.default_rng(seed=22)
    a = rng.normal(0.001, 0.01, size=200).tolist()
    b = rng.normal(0.0, 0.01, size=200).tolist()
    for method in ("memmel", "jobson_korkie"):
        result = sharpe_ratio_test(a, b, method=method)
        assert result.method == method
        assert 0.0 <= result.p_value <= 1.0


def test_sharpe_test_unknown_method_raises() -> None:
    """Bogus method string must raise."""

    with pytest.raises(ValueError, match="method must be"):
        sharpe_ratio_test([0.1, 0.2], [0.1, 0.1], method="bogus")


def test_sharpe_test_handles_zero_variance_gracefully() -> None:
    """Series with zero variance → no crash, returns p=1.0."""

    a = [0.01] * 100  # constant → std=0
    b = [0.001 * i for i in range(100)]
    result = sharpe_ratio_test(a, b)
    assert result.p_value == 1.0
    # No NaN leak.
    assert math.isfinite(result.sharpe_a) or result.sharpe_a == 0.0


def test_sharpe_test_short_series_returns_neutral() -> None:
    """n < 3 → returns neutral SharpeTestResult, no exception."""

    result = sharpe_ratio_test([0.1, 0.2], [0.1, 0.1])
    assert result.n_obs == 2
    assert result.p_value == 1.0


# ---------------------------------------------------------------------------
# Multiple-testing corrections
# ---------------------------------------------------------------------------


def test_bonferroni_rejects_only_below_alpha_over_k() -> None:
    """For 6 tests at α=0.05, only p < 0.05/6 ≈ 0.0083 survive."""

    p_values = [0.001, 0.005, 0.01, 0.02, 0.05, 0.5]
    corr = bonferroni_correct(p_values, alpha=0.05)
    expected = [True, True, False, False, False, False]
    assert corr.rejected == expected
    assert all(t == pytest.approx(0.05 / 6) for t in corr.adjusted_alpha)


def test_holm_is_less_conservative_than_bonferroni() -> None:
    """Holm rejects at least as many tests as Bonferroni does."""

    p_values = [0.001, 0.005, 0.01, 0.02, 0.05, 0.5]
    b = bonferroni_correct(p_values, alpha=0.05)
    h = holm_correct(p_values, alpha=0.05)
    n_b = sum(b.rejected)
    n_h = sum(h.rejected)
    assert n_h >= n_b


def test_holm_cascades_failures_correctly() -> None:
    """First failure to reject blocks all higher-ranked tests.

    Sorted p values are [0.001, 0.02, 0.5]:
      - rank 0: 0.001 < α/3=0.0167 → reject
      - rank 1: 0.02 < α/2=0.025 → reject
      - rank 2: 0.5 > α/1=0.05 → cascade (already last so no effect).

    To exercise the cascade, swap the middle for a borderline-fail
    value: [0.001, 0.03, 0.002]. Sorted: [0.001, 0.002, 0.03].
      - rank 0: 0.001 < 0.0167 → reject
      - rank 1: 0.002 < 0.025 → reject
      - rank 2: 0.03 > 0.05 → wait, 0.03 < 0.05 so reject. Use a value
        > α: [0.001, 0.5, 0.002]. Sorted: [0.001, 0.002, 0.5].
      - rank 0: 0.001 < 0.0167 → reject
      - rank 1: 0.002 < 0.025 → reject
      - rank 2: 0.5 > 0.05 → fail (last test, no cascade).
    Result: only the 0.5 fails.
    """

    p_values = [0.001, 0.5, 0.002]
    corr = holm_correct(p_values, alpha=0.05)
    # 0.5 is too high to survive; the other two reject.
    assert corr.rejected == [True, False, True]


def test_holm_cascade_blocks_later_tests() -> None:
    """When a mid-rank test fails, every later (larger) p-value is blocked."""

    # Sorted: [0.001, 0.04, 0.045]. Thresholds: α/3=0.0167, α/2=0.025, α/1=0.05.
    #   - 0.001 < 0.0167 → reject
    #   - 0.04 > 0.025 → fail → cascade
    #   - 0.045 < 0.05 but blocked by cascade.
    p_values = [0.001, 0.04, 0.045]
    corr = holm_correct(p_values, alpha=0.05)
    assert corr.rejected == [True, False, False]


def test_multiple_testing_correction_empty_input() -> None:
    """Zero p-values → empty correction tables, no crash."""

    corr = bonferroni_correct([])
    assert corr.rejected == []
    assert corr.adjusted_alpha == []


def test_results_to_dataframe_round_trips_with_labels() -> None:
    """Helper turns a list of test results into a labelled DataFrame."""

    rng = np.random.default_rng(seed=30)
    a = rng.normal(0.001, 0.01, size=200).tolist()
    b = rng.normal(0.0, 0.01, size=200).tolist()
    r1 = diebold_mariano_test(a, b)
    r2 = diebold_mariano_test(b, a)
    df = results_to_dataframe([r1, r2], labels=["A vs B", "B vs A"])
    assert next(iter(df.columns)) == "pair"
    assert df.shape[0] == 2
    assert "dm_statistic" in df.columns


# ---------------------------------------------------------------------------
# Power-analysis inversion / Minimum Detectable Effect
# ---------------------------------------------------------------------------


def test_minimum_detectable_effect_inverts_dm_power_formula() -> None:
    """MDE IR should round-trip through the forward DM power formula."""

    result = minimum_detectable_effect(
        hac_variance=0.0004,
        n_obs=100,
        observed_mean_differential=-0.001,
        alpha=0.05,
        power=0.80,
        periods_per_year=52.0,
    )

    assert isinstance(result, MinimumDetectableEffect)
    assert result.required_ncp == pytest.approx(2.8015818, rel=1e-6)
    assert result.mde_excess_return_per_period == pytest.approx(
        0.00560316,
        rel=1e-6,
    )
    assert result.mde_excess_return_annual == pytest.approx(0.2913645, rel=1e-6)
    assert result.mde_ir == pytest.approx(
        result.required_ncp * math.sqrt(52.0 / 100.0),
        rel=1e-12,
    )
    assert result.observed_excess_return_annual == pytest.approx(0.052)
    assert result.observed_ir == pytest.approx(0.360555, rel=1e-6)

    recovered_power = dm_power_for_information_ratio(
        result.mde_ir,
        result.n_obs,
        alpha=result.alpha,
        periods_per_year=result.periods_per_year,
    )
    assert recovered_power == pytest.approx(result.power, abs=1e-6)


def test_minimum_detectable_effect_inverts_dm_power_formula_for_wider_alpha() -> None:
    """Two-sided MDE inversion should include both rejection tails."""

    result = minimum_detectable_effect(
        hac_variance=0.0004,
        n_obs=307,
        alpha=0.10,
        power=0.80,
        periods_per_year=52.0,
    )

    recovered_power = dm_power_for_information_ratio(
        result.mde_ir,
        result.n_obs,
        alpha=result.alpha,
        periods_per_year=result.periods_per_year,
    )
    assert recovered_power == pytest.approx(result.power, abs=1e-6)


def test_minimum_detectable_effect_from_dm_uses_negative_return_diagnostics() -> None:
    """The DM wrapper should carry the observed spread into MDE diagnostics."""

    dm = diebold_mariano_test(
        [0.03, 0.01, 0.02, 0.04, 0.00, 0.03],
        [0.00, 0.00, 0.01, 0.00, 0.01, 0.00],
        loss_fn="negative_return",
    )
    result = minimum_detectable_effect_from_dm(
        dm,
        alpha=0.10,
        power=0.75,
        periods_per_year=12.0,
    )

    assert result.n_obs == dm.n_obs
    assert result.hac_variance == dm.hac_variance
    assert result.observed_excess_return_annual == pytest.approx(
        -dm.mean_loss_differential * 12.0
    )
    assert result.alpha == 0.10
    assert result.power == 0.75


def test_minimum_detectable_effect_rejects_invalid_design_inputs() -> None:
    """Invalid alpha / power / period count should fail loudly."""

    with pytest.raises(ValueError, match="alpha"):
        minimum_detectable_effect(0.01, 20, alpha=0.0)
    with pytest.raises(ValueError, match="power"):
        minimum_detectable_effect(0.01, 20, power=1.0)
    with pytest.raises(ValueError, match="periods_per_year"):
        minimum_detectable_effect(0.01, 20, periods_per_year=0.0)
    with pytest.raises(ValueError, match="periods_per_year"):
        minimum_detectable_effect(0.01, 20, periods_per_year=float("nan"))
    with pytest.raises(ValueError, match="n_obs"):
        minimum_detectable_effect(0.01, 1)
    for n_obs in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="n_obs"):
            minimum_detectable_effect(0.01, n_obs)
    with pytest.raises(ValueError, match="hac_variance"):
        minimum_detectable_effect(-0.01, 20)
    with pytest.raises(ValueError, match="hac_variance"):
        minimum_detectable_effect(float("nan"), 20)
    with pytest.raises(ValueError, match="hac_variance"):
        minimum_detectable_effect(float("inf"), 20)


def test_minimum_detectable_effect_rejects_non_finite_observed_differential() -> None:
    """Observed diagnostics should not leak non-finite values into reports."""

    for observed_mean_differential in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="observed_mean_differential"):
            minimum_detectable_effect(
                0.01,
                20,
                observed_mean_differential=observed_mean_differential,
            )


def test_minimum_detectable_effect_handles_degenerate_variance() -> None:
    """A zero-variance differential should return a documented neutral MDE."""

    result = minimum_detectable_effect(
        hac_variance=0.0,
        n_obs=20,
        observed_mean_differential=-0.01,
    )

    assert result.note == "degenerate_zero_variance"
    assert result.mde_ir == 0.0
    assert result.mde_excess_return_annual == 0.0
    assert result.annualized_tracking_error == 0.0


def test_dm_power_for_information_ratio_rejects_non_finite_periods() -> None:
    """Forward-power diagnostics should not emit non-finite probabilities."""

    with pytest.raises(ValueError, match="periods_per_year"):
        dm_power_for_information_ratio(0.8, 20, periods_per_year=float("nan"))


def test_dm_power_for_information_ratio_rejects_non_finite_n_obs() -> None:
    """Forward-power diagnostics should reject impossible sample sizes."""

    for n_obs in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="n_obs"):
            dm_power_for_information_ratio(0.8, n_obs)


def test_dm_power_for_information_ratio_rejects_non_finite_ir() -> None:
    """Forward-power diagnostics should reject impossible true-effect sizes."""

    for information_ratio in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="information_ratio"):
            dm_power_for_information_ratio(information_ratio, 20)


def test_minimum_detectable_effect_from_dm_rejects_non_return_loss() -> None:
    """IR / excess-return inversion is only valid for negative-return DM."""

    dm = diebold_mariano_test(
        [0.01, 0.02, 0.03, 0.04],
        [0.02, 0.01, 0.02, 0.01],
        loss_fn="squared_error",
    )

    with pytest.raises(ValueError, match="negative-return loss"):
        minimum_detectable_effect_from_dm(dm)
