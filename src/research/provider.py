"""Research-pipeline AkshareProvider: a thin, fakeable wrapper around an akshare client.

The production ``src.data.providers.akshare_provider.AKShareProvider`` is large and
includes circuit breakers, multi-tier persistent caches, and proxy management — all
necessary for the live trading service, but heavyweight for research/backtest code
that wants to:

* Run in CI without the akshare package installed.
* Inject deterministic fakes in unit tests.
* Return frames already wrapped in the schema/provenance contract.

``AkshareProvider`` (in this module) is the lightweight counterpart. It takes a
``client`` — anything with the akshare methods we care about — and a ``now`` callable
for testability. If ``client`` is ``None``, fetch methods return empty
``NormalizedFrame`` instances with ``synthetic=False, fallback=True`` provenance so
the consumer can decide whether to substitute its own synthetic data.

Tests inject ``FakeAkshareClient`` (defined in :mod:`src.research.testing`) — but
crucially the production class never imports akshare at module load time, so this
module is safe to import on environments without akshare.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import pandas as pd

from .normalized_frame import (
    FrameProvenance,
    FrameSchema,
    NormalizedFrame,
)

DAILY_BAR_SCHEMA = FrameSchema(
    index=("date", "datetime64[ns]"),
    value_columns={
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "float64",
    },
    required=("open", "high", "low", "close"),
)


_AKSHARE_DAILY_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AkshareCallContext:
    """Bundle of arguments passed to a client method — kept explicit for fakes."""

    symbol: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]


class AkshareProvider:
    """Fakeable research adapter for akshare-shaped clients.

    Parameters
    ----------
    client:
        Optional object that exposes the akshare methods we wrap. Pass ``None`` to
        operate in "no upstream" mode — fetches return empty frames with explicit
        fallback provenance so callers can short-circuit or substitute synthetic
        data.
    now:
        Callable returning a UTC ``datetime``. Defaults to ``datetime.now(timezone.utc)``;
        overrideable so tests get deterministic provenance timestamps.
    source_id:
        Identifier baked into provenance. Defaults to ``"akshare"`` so cross-source
        health dashboards group entries from this adapter under a single label.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        now: Callable[[], datetime] = _utcnow,
        source_id: str = "akshare",
    ) -> None:
        self._client = client
        self._now = now
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> NormalizedFrame:
        """Return daily OHLCV bars as a ``NormalizedFrame``.

        The fake client is expected to expose
        ``stock_zh_a_hist(symbol, start_date, end_date) -> pandas.DataFrame``. The
        DataFrame can be either the akshare-native Chinese-named columns (我们 will
        rename them) or already-normalized English columns.
        """
        symbol = (symbol or "").strip()
        if not symbol:
            raise ValueError("symbol is required")

        if self._client is None:
            return self._empty_frame(reason="client_not_configured", fallback=True)

        ctx = AkshareCallContext(symbol=symbol, start_date=start_date, end_date=end_date)
        try:
            raw = self._invoke_daily(ctx)
        except Exception as exc:
            return self._empty_frame(
                reason=f"upstream_error: {type(exc).__name__}: {exc}",
                fallback=True,
            )

        if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
            return self._empty_frame(reason="upstream_returned_empty", fallback=True)

        normalized_raw = self._normalize_columns(raw)
        as_of = self._infer_as_of(normalized_raw)
        provenance = FrameProvenance(
            source_id=self._source_id,
            as_of=as_of,
            fallback=False,
            synthetic=False,
            reason=None,
        )
        return NormalizedFrame.from_raw(normalized_raw, DAILY_BAR_SCHEMA, provenance)

    def _invoke_daily(self, ctx: AkshareCallContext) -> pd.DataFrame:
        # Prefer the wrapper method name used by the existing AKShareProvider so
        # fakes can be reused. Fall back to ``stock_zh_a_hist`` for raw akshare.
        candidate = getattr(self._client, "fetch_daily_bars", None)
        if callable(candidate):
            return candidate(
                symbol=ctx.symbol,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
            )
        candidate = getattr(self._client, "stock_zh_a_hist", None)
        if callable(candidate):
            return candidate(
                symbol=ctx.symbol,
                start_date=_format_yyyymmdd(ctx.start_date),
                end_date=_format_yyyymmdd(ctx.end_date),
            )
        raise AttributeError("client must expose either fetch_daily_bars or stock_zh_a_hist")

    def _normalize_columns(self, raw: pd.DataFrame) -> pd.DataFrame:
        # Map Chinese akshare columns to canonical English names when present.
        rename_map = {k: v for k, v in _AKSHARE_DAILY_COLUMN_MAP.items() if k in raw.columns}
        if rename_map:
            raw = raw.rename(columns=rename_map)
        return raw

    def _infer_as_of(self, raw: pd.DataFrame) -> Optional[datetime]:
        # Prefer the last sample's timestamp; never substitute "now" — that would
        # pretend the data is fresher than it is.
        if "date" in raw.columns:
            try:
                ts = pd.to_datetime(raw["date"].iloc[-1])
            except (IndexError, ValueError, TypeError):
                return None
            if pd.isna(ts):
                return None
            ts_py = ts.to_pydatetime()
            if ts_py.tzinfo is None:
                ts_py = ts_py.replace(tzinfo=timezone.utc)
            return ts_py
        if isinstance(raw.index, pd.DatetimeIndex) and len(raw.index) > 0:
            ts_py = raw.index[-1].to_pydatetime()
            if ts_py.tzinfo is None:
                ts_py = ts_py.replace(tzinfo=timezone.utc)
            return ts_py
        return None

    def _empty_frame(self, *, reason: str, fallback: bool) -> NormalizedFrame:
        empty = pd.DataFrame(
            {col: pd.Series(dtype=dtype) for col, dtype in DAILY_BAR_SCHEMA.value_columns.items()}
        )
        empty.index = pd.DatetimeIndex([], name=DAILY_BAR_SCHEMA.index_name)
        provenance = FrameProvenance(
            source_id=self._source_id,
            as_of=None,
            fallback=fallback,
            synthetic=False,
            reason=reason,
        )
        return NormalizedFrame.from_raw(empty, DAILY_BAR_SCHEMA, provenance)


def _format_yyyymmdd(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y%m%d")


__all__: Sequence[str] = (
    "DAILY_BAR_SCHEMA",
    "AkshareCallContext",
    "AkshareProvider",
)
