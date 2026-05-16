import pandas as pd
import pytest

from src.backtest.signal_adapter import SignalAdapter


def test_normalize_single_asset_auto_detects_event_mode():
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    normalized = SignalAdapter.normalize_single_asset(
        pd.Series([0, 1, -1, 0], index=index),
        index=index,
    )

    assert normalized.mode == "event"
    assert normalized.values.tolist() == [0, 1, -1, 0]


def test_normalize_single_asset_auto_detects_target_mode():
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    normalized = SignalAdapter.normalize_single_asset(
        pd.Series([0.0, 0.35, 0.65, 1.0], index=index),
        index=index,
    )

    assert normalized.mode == "target"
    assert normalized.values.tolist() == [0.0, 0.35, 0.65, 1.0]


def test_single_asset_to_target_exposure_builds_held_exposure_path():
    index = pd.date_range("2024-01-01", periods=5, freq="D")
    exposure = SignalAdapter.single_asset_to_target_exposure(
        pd.Series([0, 1, 0, -1, 0], index=index),
        index=index,
    )

    assert exposure.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_normalize_target_weights_caps_gross_exposure():
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    weights = SignalAdapter.normalize_target_weights(
        pd.DataFrame({"A": [0.9, 0.3], "B": [0.8, -0.9]}, index=index),
        index=index,
        columns=["A", "B"],
        max_abs_weight=1.0,
        max_gross_exposure=1.0,
    )

    assert weights.abs().sum(axis=1).max() == pytest.approx(1.0)
    assert weights.loc[index[1], "B"] < 0


def test_normalize_target_weights_preserves_sub_cap_weights():
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    raw = pd.DataFrame({"A": [0.3, 0.0], "B": [0.2, 0.4]}, index=index)
    weights = SignalAdapter.normalize_target_weights(
        raw,
        index=index,
        columns=["A", "B"],
        max_abs_weight=1.0,
        max_gross_exposure=1.0,
    )

    # Row 0: gross = 0.5 < cap → preserve as-is, no down-scaling
    assert weights.loc[index[0], "A"] == pytest.approx(0.3)
    assert weights.loc[index[0], "B"] == pytest.approx(0.2)
    # Row 1: gross = 0.4 < cap → preserve as-is
    assert weights.loc[index[1], "A"] == pytest.approx(0.0)
    assert weights.loc[index[1], "B"] == pytest.approx(0.4)
