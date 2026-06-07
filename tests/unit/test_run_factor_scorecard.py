import importlib


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
