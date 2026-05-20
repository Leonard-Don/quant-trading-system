"""Unit tests for the falsifiable-alpha-target power script."""

from __future__ import annotations

import pytest

from scripts.power_target import render_markdown, render_terminal, self_check
from src.backtest.strategy_statistical_tests import MinimumDetectableEffect


def _sample_power_result() -> dict[str, object]:
    mde = MinimumDetectableEffect(
        mde_ir=1.1530,
        mde_excess_return_annual=0.1488,
        mde_excess_return_per_period=0.0028615,
        observed_ir=-0.3979,
        observed_excess_return_annual=-0.0513,
        required_ncp=2.8015852,
        power=0.80,
        alpha=0.05,
        n_obs=307,
        hac_variance=0.0003205,
        annualized_tracking_error=0.1290,
        periods_per_year=52.0,
    )
    return {
        "strategy": "rotation",
        "period_start": "2020-01-02",
        "period_end": "2026-05-15",
        "alpha": 0.05,
        "power": 0.80,
        "periods_per_year": 52.0,
        "rebalance_freq_days": 5,
        "window_years": 2.0,
        "step_months": 6,
        "terminal": {
            "dm_statistic": 0.967,
            "dm_pvalue": 0.3337,
            "mean_loss_differential": 0.0009865,
            "mde": mde.to_dict(),
        },
        "per_window": [
            {
                "window_id": 0,
                "start_date": "2020-01-09",
                "end_date": "2022-01-08",
                "n_obs": 97,
                "mde_ir": 2.0513,
                "mde_excess_return_annual": 0.2941,
                "observed_ir": -0.8018,
            }
        ],
    }


def test_self_check_round_trips_mde_power() -> None:
    """Feeding the MDE IR back into the forward formula recovers target power."""

    mde = MinimumDetectableEffect(
        mde_ir=2.8015852 * (52.0 / 307.0) ** 0.5,
        mde_excess_return_annual=0.0,
        mde_excess_return_per_period=0.0,
        observed_ir=0.0,
        observed_excess_return_annual=0.0,
        required_ncp=2.8015852,
        power=0.80,
        alpha=0.05,
        n_obs=307,
        hac_variance=0.0001,
        annualized_tracking_error=0.0721,
        periods_per_year=52.0,
    )

    check = self_check(mde)

    assert check["target_power"] == 0.80
    assert check["recovered_power"] == pytest.approx(0.80, abs=1e-6)
    assert check["abs_error"] < 1e-6


def test_terminal_renderer_calls_out_noise_floor() -> None:
    """Terminal output should surface the failure condition in one screen."""

    output = render_terminal(_sample_power_result())

    assert "MINIMUM DETECTABLE EFFECT" in output
    assert "INSIDE the noise floor" in output
    assert "MDE Information Ratio" in output
    assert "two-tail power solve" in output


def test_markdown_renderer_links_method_and_regeneration_command() -> None:
    """The generated doc should point readers back to the code/script path."""

    output = render_markdown(_sample_power_result())

    assert "Falsifiable alpha target" in output
    assert "Per walk-forward window" in output
    assert "minimum_detectable_effect" in output
    assert "WalkForwardAnalyzer" in output
    assert "statistical_power_diagnostics" in output
    assert "python scripts/power_target.py" in output
