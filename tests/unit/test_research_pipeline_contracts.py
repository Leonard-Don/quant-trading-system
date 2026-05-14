from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.research.backtest_report import BacktestReport
from src.research.data_handler import DataHandler, FeatureMatrixError
from src.research.feature_set import FeatureSet, FeatureSpec
from src.research.model_run import ModelRun, ModelRunValidationError
from src.research.normalized_frame import (
    FIELD_STATUS_ABSENT,
    FIELD_STATUS_HAS_NULLS,
    FIELD_STATUS_PRESENT,
    FrameProvenance,
    FrameSchema,
    FrameValidationError,
    NormalizedFrame,
)
from src.research.provider import AkshareProvider

_SCHEMA = FrameSchema(
    index=("date", "datetime64[ns]"),
    value_columns={"close": "float64", "volume": "float64", "turnover": "float64"},
    required=("close",),
)


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03", "2026-01-06"],
            "close": [10.0, 10.5, 10.0],
            "volume": [1000.0, None, 1200.0],
        }
    )


def _normalized() -> NormalizedFrame:
    return NormalizedFrame.from_raw(
        _raw_frame(),
        _SCHEMA,
        FrameProvenance(source_id="fixture", as_of=datetime(2026, 1, 6, tzinfo=timezone.utc)),
    )


def test_normalized_frame_tracks_present_absent_and_null_fields() -> None:
    frame = _normalized()

    assert frame.field_status["close"] == FIELD_STATUS_PRESENT
    assert frame.field_status["volume"] == FIELD_STATUS_HAS_NULLS
    assert frame.field_status["turnover"] == FIELD_STATUS_ABSENT
    assert frame.provenance.to_dict()["source_id"] == "fixture"


def test_normalized_frame_rejects_missing_index_column() -> None:
    with pytest.raises(FrameValidationError, match="index column"):
        NormalizedFrame.from_raw(
            pd.DataFrame({"close": [10.0], "volume": [1.0]}),
            _SCHEMA,
            FrameProvenance(source_id="fixture"),
        )


def test_normalized_frame_rejects_missing_required_columns() -> None:
    with pytest.raises(FrameValidationError, match="required columns missing"):
        NormalizedFrame.from_raw(
            pd.DataFrame({"date": ["2026-01-02"], "volume": [1.0]}),
            _SCHEMA,
            FrameProvenance(source_id="fixture"),
        )


def test_akshare_provider_is_fakeable_and_never_requires_live_network() -> None:
    class FakeClient:
        def stock_zh_a_hist(self, **kwargs):
            assert kwargs["symbol"] == "600519"
            return pd.DataFrame(
                {
                    "日期": ["2026-01-02"],
                    "开盘": [10.0],
                    "最高": [10.2],
                    "最低": [9.9],
                    "收盘": [10.1],
                    "成交量": [1234.0],
                }
            )

    frame = AkshareProvider(client=FakeClient()).fetch_daily_bars("600519")

    assert frame.provenance.source_id == "akshare"
    assert frame.provenance.fallback is False
    assert list(frame.data.columns) == ["open", "high", "low", "close", "volume"]


def test_akshare_provider_no_client_returns_explicit_fallback_frame() -> None:
    frame = AkshareProvider(client=None).fetch_daily_bars("600519")

    assert frame.data.empty
    assert frame.provenance.fallback is True
    assert frame.provenance.reason == "client_not_configured"


def test_feature_set_and_data_handler_prepare_matrix_with_drop_policy() -> None:
    frame = _normalized()
    feature_set = FeatureSet.of(
        [
            FeatureSpec("close", lambda f: f.data["close"]),
            FeatureSpec("volume", lambda f: f.data["volume"]),
        ]
    )
    matrix, report = DataHandler(null_policy="drop").prepare_with_report(frame, feature_set)

    assert list(matrix.columns) == ["close", "volume"]
    assert len(matrix) == 2
    assert report.rows_in == 3
    assert report.rows_dropped == 1
    assert report.provenance["source_id"] == "fixture"


def test_data_handler_raise_policy_surfaces_null_features() -> None:
    frame = _normalized()
    feature_set = FeatureSet.of([FeatureSpec("volume", lambda f: f.data["volume"])])

    with pytest.raises(FeatureMatrixError, match="nulls"):
        DataHandler(null_policy="raise").prepare(frame, feature_set)


def test_model_run_validates_run_id_and_serializes_metrics() -> None:
    run = ModelRun(
        run_id="research/600519:baseline",
        model_name="ridge",
        params={"alpha": 0.5},
        metrics={"r2": 0.42},
        artifacts={"model": "artifacts/ridge.pkl"},
        created_at=datetime(2026, 1, 7, tzinfo=timezone.utc),
    )

    payload = run.to_dict()
    restored = ModelRun.from_dict(payload)
    assert restored.run_id == run.run_id
    assert payload["metrics"]["r2"] == 0.42

    with pytest.raises(ModelRunValidationError):
        ModelRun(run_id="../bad", model_name="ridge")


def test_backtest_report_embeds_source_health_and_matrix_report() -> None:
    frame = _normalized()
    feature_set = FeatureSet.of([FeatureSpec("close", lambda f: f.data["close"])])
    _matrix, matrix_report = DataHandler().prepare_with_report(frame, feature_set)

    report = BacktestReport(
        report_id="bt-600519",
        returns=(("2026-01-02", 0.01), ("2026-01-03", -0.005)),
        metrics={"sharpe": 1.2, "drawdown": -0.08},
        source_health=(
            {"status": "fresh", "selected_source": "fixture", **matrix_report.to_dict()},
        ),
        notes="strategy=momentum",
    )

    payload = report.to_dict()
    assert payload["source_health"][0]["status"] == "fresh"
    assert payload["source_health"][0]["rows_out"] == 3
    assert payload["period_start"] == "2026-01-02"
