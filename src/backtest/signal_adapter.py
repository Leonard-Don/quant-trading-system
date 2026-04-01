"""Signal normalization helpers for backtest engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class NormalizedSingleAssetSignals:
    values: pd.Series
    mode: str  # event | target


class SignalAdapter:
    """Normalize strategy outputs into execution-ready signal structures."""

    @staticmethod
    def normalize_single_asset(
        raw_signals,
        *,
        index: pd.Index,
        signal_mode: str = "auto",
    ) -> NormalizedSingleAssetSignals:
        if isinstance(raw_signals, pd.DataFrame):
            if "signal" in raw_signals.columns:
                series = raw_signals["signal"]
            else:
                series = raw_signals.iloc[:, 0]
        elif isinstance(raw_signals, pd.Series):
            series = raw_signals
        else:
            series = pd.Series(list(raw_signals), index=index)

        series = pd.Series(series, copy=False)
        if not series.index.equals(index):
            series = series.reindex(index).fillna(0)
        series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        mode = SignalAdapter._resolve_single_asset_mode(series, signal_mode)
        if mode == "event":
            series = series.clip(-1, 1).round().astype(int)
        else:
            series = series.clip(0.0, 1.0).astype(float)

        return NormalizedSingleAssetSignals(values=series, mode=mode)

    @staticmethod
    def single_asset_to_target_exposure(
        raw_signals,
        *,
        index: pd.Index,
        signal_mode: str = "auto",
    ) -> pd.Series:
        normalized = SignalAdapter.normalize_single_asset(
            raw_signals,
            index=index,
            signal_mode=signal_mode,
        )
        if normalized.mode == "target":
            return normalized.values.clip(0.0, 1.0).astype(float)

        exposure = []
        current = 0.0
        for value in normalized.values.astype(int):
            if value == 1:
                current = 1.0
            elif value == -1:
                current = 0.0
            exposure.append(current)
        return pd.Series(exposure, index=index, dtype=float)

    @staticmethod
    def normalize_target_weights(
        raw_signals,
        *,
        index: pd.Index,
        columns: Iterable[str],
        max_abs_weight: float = 1.0,
        max_gross_exposure: float | None = 1.0,
    ) -> pd.DataFrame:
        columns = list(columns)
        if isinstance(raw_signals, pd.Series):
            if len(columns) != 1:
                raise ValueError("Series target weights only supported for single-asset portfolios")
            frame = raw_signals.to_frame(columns[0])
        elif isinstance(raw_signals, pd.DataFrame):
            frame = raw_signals.copy()
        else:
            frame = pd.DataFrame(raw_signals, index=index, columns=columns)

        frame = frame.reindex(index=index, columns=columns).fillna(0.0)
        frame = frame.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        frame = frame.clip(lower=-abs(max_abs_weight), upper=abs(max_abs_weight))

        if max_gross_exposure is not None:
            gross = frame.abs().sum(axis=1)
            scale = gross.where(gross <= max_gross_exposure, max_gross_exposure / gross.replace(0, np.nan))
            scale = scale.fillna(1.0)
            frame = frame.mul(scale, axis=0)

        return frame.astype(float)

    @staticmethod
    def _resolve_single_asset_mode(series: pd.Series, signal_mode: str) -> str:
        if signal_mode in {"event", "target"}:
            return signal_mode

        unique_values = set(np.round(series.dropna().astype(float), 8).tolist())
        if unique_values.issubset({-1.0, 0.0, 1.0}):
            return "event"
        return "target"
