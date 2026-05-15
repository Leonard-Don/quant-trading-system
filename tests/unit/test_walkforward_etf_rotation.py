"""Tests for the walk-forward ETF rotation parameter scan."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import walkforward_etf_rotation
from src.strategy.etf_rotation_strategy import EtfScoringConfig


def _write_prices(tmp_path: Path, periods: int = 600) -> Path:
    dates = pd.bdate_range("2022-01-03", periods=periods)
    rng = np.random.default_rng(11)
    codes = ["510300", "159985", "512400", "518680", "513130"]
    data = {}
    for offset, code in enumerate(codes):
        drift = np.linspace(0.0, 0.25 - 0.05 * offset, len(dates))
        noise = np.cumsum(rng.normal(0.0, 0.004, len(dates)))
        data[code] = 5.0 * np.exp(drift + noise)
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(data, index=dates).to_csv(csv_path)
    return csv_path


# ---------------------------------------------------------------------------
# Grid loading
# ---------------------------------------------------------------------------


def test_load_grid_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"not_a_field": [1, 2]}))
    with pytest.raises(ValueError):
        walkforward_etf_rotation.load_grid(path)


def test_load_grid_strips_underscore_comments(tmp_path: Path) -> None:
    path = tmp_path / "grid.json"
    path.write_text(json.dumps({
        "_note": "ignored",
        "momentum_return20_multiplier": [200.0, 250.0],
    }))
    grid = walkforward_etf_rotation.load_grid(path)
    assert "momentum_return20_multiplier" in grid
    assert "_note" not in grid


def test_expand_grid_cartesian_product() -> None:
    grid = {
        "momentum_return20_multiplier": [200.0, 250.0],
        "premium_hard_threshold": [0.04, 0.05],
    }
    configs = walkforward_etf_rotation.expand_grid(grid)
    assert len(configs) == 4
    multipliers = {c.momentum_return20_multiplier for c in configs}
    thresholds = {c.premium_hard_threshold for c in configs}
    assert multipliers == {200.0, 250.0}
    assert thresholds == {0.04, 0.05}


def test_expand_grid_empty_returns_default_config() -> None:
    configs = walkforward_etf_rotation.expand_grid({})
    assert len(configs) == 1
    assert configs[0] == EtfScoringConfig()


# ---------------------------------------------------------------------------
# Window iteration
# ---------------------------------------------------------------------------


def test_iter_windows_yields_non_overlapping_test_slices() -> None:
    index = pd.bdate_range("2024-01-01", periods=200)
    windows = list(walkforward_etf_rotation.iter_windows(index, train_days=120, test_days=20))

    assert len(windows) > 0
    # Test slices must be contiguous and non-overlapping by default
    for prev, curr in zip(windows, windows[1:]):
        assert prev[1].max() < curr[1].min()


def test_iter_windows_rejects_zero_sizes() -> None:
    index = pd.bdate_range("2024-01-01", periods=50)
    with pytest.raises(ValueError):
        list(walkforward_etf_rotation.iter_windows(index, train_days=0, test_days=10))


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------


def test_run_walkforward_returns_per_window_oos_metrics(tmp_path: Path) -> None:
    csv_path = _write_prices(tmp_path, periods=600)
    grid_path = tmp_path / "grid.json"
    grid_path.write_text(json.dumps({"momentum_return20_multiplier": [200.0, 300.0]}))

    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path,
        train_days=250,
        test_days=60,
    )
    assert result["summary"]["num_windows"] >= 1
    assert len(result["configs"]) == 2
    first = result["windows"][0]
    assert first["best_config_index"] in {0, 1}
    assert first["out_of_sample"] is not None
    assert "sharpe_ratio" in first["out_of_sample"]


def test_run_walkforward_without_grid_uses_default_config(tmp_path: Path) -> None:
    csv_path = _write_prices(tmp_path, periods=500)
    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path=None,
        train_days=250,
        test_days=60,
    )
    assert len(result["configs"]) == 1
    assert result["configs"][0]["momentum_return20_multiplier"] == EtfScoringConfig().momentum_return20_multiplier
