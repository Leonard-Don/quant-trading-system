import importlib


def _report(name, *, oos_p_value, passes=True, oos_ic=0.05):
    return {
        "name": name,
        "n_dates": 40,
        "mean_ic": 0.04,
        "icir": 0.3,
        "oos_mean_ic": oos_ic,
        "oos_n": 12,
        "oos_icir": 0.4,
        "oos_t_stat": 2.0,
        "oos_p_value": oos_p_value,
        "sign_stable": True,
        "passes": passes,
        "yearly_ic": {2023: 0.04},
    }


def test_holm_correction_annotates_reports_across_all_cells():
    # Multiple-testing control must span EVERY (factor, horizon) cell evaluated
    # in the run — that is the actual number of hypotheses tested. Holm at
    # alpha=0.05 with k=2 finite p-values: 0.001 < 0.05/2 -> significant;
    # 0.30 > 0.05 -> not. A NaN p-value (untestable cell) is annotated None.
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_horizon = {
        5: [_report("alpha", oos_p_value=0.001)],
        20: [
            _report("alpha", oos_p_value=0.30),
            _report("beta", oos_p_value=float("nan"), passes=False),
        ],
    }
    correction = mod.apply_holm_correction(reports_by_horizon, alpha=0.05)
    by_label = {
        (h, r["name"]): r["holm_significant"]
        for h, reps in reports_by_horizon.items()
        for r in reps
    }
    assert by_label[(5, "alpha")] is True
    assert by_label[(20, "alpha")] is False
    assert by_label[(20, "beta")] is None
    assert correction.method == "holm"
    assert len(correction.raw_p_values) == 2  # NaN cell excluded from the family


def test_multi_horizon_markdown_surfaces_holm_verdicts():
    # The scorecard doc must show the Holm verdict next to each passing pair so
    # a "PASS" can never silently dodge the data-snooping control.
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_horizon = {
        20: [
            _report("alpha", oos_p_value=0.001),
            _report("beta", oos_p_value=0.40, passes=True),
        ],
    }
    mod.apply_holm_correction(reports_by_horizon, alpha=0.05)
    md = mod.build_multi_horizon_markdown(
        reports_by_horizon, universe_label="test", n_symbols=50
    )
    assert "Holm" in md
    assert "alpha@20 (Holm✓)" in md
    assert "beta@20 (Holm✗)" in md


def test_scorecard_markdown_back_compat_without_new_keys():
    # Old-shape reports (no oos_p_value / holm_significant) must still render.
    mod = importlib.import_module("scripts.run_factor_scorecard")
    legacy = {
        "name": "roe",
        "n_dates": 40,
        "mean_ic": 0.04,
        "icir": 0.3,
        "oos_mean_ic": 0.035,
        "sign_stable": True,
        "passes": True,
        "yearly_ic": {2023: 0.04},
    }
    md = mod.build_scorecard_markdown([legacy])
    assert "roe" in md and "PASS" in md


def test_build_scorecard_table_and_monthly_dates():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports = [
        {
            "name": "roe",
            "n_dates": 40,
            "mean_ic": 0.04,
            "icir": 0.3,
            "oos_mean_ic": 0.035,
            "sign_stable": True,
            "passes": True,
            "yearly_ic": {2023: 0.04},
        },
        {
            "name": "random",
            "n_dates": 40,
            "mean_ic": 0.0,
            "icir": 0.0,
            "oos_mean_ic": 0.0,
            "sign_stable": False,
            "passes": False,
            "yearly_ic": {2023: 0.0},
        },
    ]
    md = mod.build_scorecard_markdown(reports)
    assert "roe" in md and "PASS" in md and "FAIL" in md
    import pandas as pd

    dates = mod.monthly_rebalance_dates(pd.bdate_range("2023-01-01", "2023-06-30"))
    assert len(dates) >= 5 and all(isinstance(d, pd.Timestamp) for d in dates)
