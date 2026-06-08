"""Tushare data provider for A-share / ETF end-of-day research data.

This provider deliberately treats Tushare as an **EOD / historical** source. It
is useful for A-share daily bars, ETF/fund daily bars, trading calendars, market
mood statistics, limit-up/down summaries, and industry/board after-close data.
It is not a real-time quote source, so quote payloads are explicitly labelled as
``eod_snapshot``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time as _time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import pandas as pd

from .base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

_DAILY_INTERVALS = {"1d", "1day", "daily", "d"}
_SUPPORTED_EXCHANGES = {"SH", "SZ", "BJ"}
_FUND_PREFIXES = (
    "15",  # Shenzhen ETF
    "16",  # Shenzhen LOF / fund
    "18",  # Shenzhen fund
    "50",  # Shanghai ETF
    "51",
    "52",
    "56",
    "58",  # STAR/科创 ETF family
)

# Default client-side TTLs (seconds). Valuation / quote / history churn intraday
# but are fine to reuse for ~half a minute; financials only move quarterly so
# they can be held far longer. These are overridable via the ``cache_ttl``
# config (a scalar applies to every read path). ``get_latest_quote`` delegates
# to ``get_historical_data`` and therefore inherits ``_DEFAULT_TTL_HISTORICAL``.
_DEFAULT_TTL_VALUATION = 45
_DEFAULT_TTL_HISTORICAL = 45
_DEFAULT_TTL_FINANCIAL = 300  # a few minutes — quarterly data barely changes
_RATE_WINDOW_SECONDS = 60.0


class _TTLCache:
    """Minimal dependency-free ``{key: (value, expires_at)}`` TTL cache.

    ``cachetools`` is not a project dependency, so this keeps things light. The
    clock is injectable (``time_func``) so tests are fully deterministic, and
    ``ttl<=0`` on a ``set`` disables caching for that entry (every read stays a
    miss).
    """

    _MISS = object()

    def __init__(self, *, time_func: Callable[[], float] = _time.monotonic):
        self._time = time_func
        self._store: dict[Any, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any:
        """Return the cached value, or the unique ``_MISS`` sentinel."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return self._MISS
            value, expires_at = entry
            if self._time() >= expires_at:
                self._store.pop(key, None)
                return self._MISS
            return value

    def set(self, key: Any, value: Any, ttl: float) -> None:
        if ttl is None or ttl <= 0:
            return  # ttl<=0 -> caching disabled, keep behavior deterministic
        with self._lock:
            self._store[key] = (value, self._time() + float(ttl))

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class _SlidingWindowRateLimiter:
    """Per-minute sliding-window throttle.

    ``try_acquire()`` records a request timestamp and returns ``True`` while the
    number of requests in the trailing 60s window stays under ``max_per_minute``;
    once the window is full it returns ``False`` so callers can short-circuit
    gracefully instead of hammering Tushare's per-minute limit. The clock is
    injectable for deterministic tests.
    """

    def __init__(self, max_per_minute: int, *, time_func: Callable[[], float] = _time.monotonic):
        self._max = max(0, int(max_per_minute))
        self._time = time_func
        self._window = _RATE_WINDOW_SECONDS
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        if self._max <= 0:
            return True  # no configured limit -> never throttle
        now = self._time()
        with self._lock:
            cutoff = now - self._window
            while self._hits and self._hits[0] <= cutoff:
                self._hits.popleft()
            if len(self._hits) >= self._max:
                return False
            self._hits.append(now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class TushareProvider(BaseDataProvider):
    """Tushare Pro provider wired into the shared data-provider interface."""

    name: str = "tushare"
    priority: int = 45
    rate_limit: int = 200
    requires_api_key: bool = True

    def __init__(self, api_key: Optional[str] = None, config: Optional[dict[str, Any]] = None):
        super().__init__(api_key=api_key, config=config or {})
        self._pro_client = self.config.get("pro_client")
        self._tushare_module = self.config.get("tushare_module")

        # Injectable clock so caching/throttling are deterministic under test.
        clock = self.config.get("clock")
        self._clock: Callable[[], float] = clock if callable(clock) else _time.monotonic

        # Optional per-instance override for the per-minute budget; default to
        # the class attribute (200) so production keeps today's headroom.
        rate_limit = self.config.get("rate_limit")
        if rate_limit is not None:
            self.rate_limit = int(rate_limit)

        # ``cache_ttl`` as a scalar overrides ALL read-path TTLs (0 disables the
        # cache, which tests use for determinism). When unset, each read path
        # uses its tuned default.
        self._cache_ttl_override = self.config.get("cache_ttl")

        self._cache = _TTLCache(time_func=self._clock)
        self._rate_limiter = _SlidingWindowRateLimiter(self.rate_limit, time_func=self._clock)

    # ------------------------------------------------------------------
    # Cache / throttle plumbing
    # ------------------------------------------------------------------
    def _ttl_for(self, default_ttl: float) -> float:
        """Resolve the effective TTL, honoring a scalar ``cache_ttl`` override."""
        if self._cache_ttl_override is not None:
            return float(self._cache_ttl_override)
        return float(default_ttl)

    def clear_cache(self) -> None:
        """Drop all cached read results (test/reset hook)."""
        self._cache.clear()

    def reset_throttle(self) -> None:
        """Forget the per-minute request window (test/reset hook)."""
        self._rate_limiter.clear()

    def _acquire_or_short_circuit(self) -> bool:
        """Try to claim a per-minute token.

        Returns ``True`` when the call may proceed. On exhaustion it returns
        ``False`` and logs once at WARNING so the silent-degradation pain is at
        least observable; callers translate that into their existing fallback
        contract (error dict / empty frame) rather than raising.
        """
        if self._rate_limiter.try_acquire():
            return True
        logger.warning(
            "Tushare per-minute rate budget (%s/min) exhausted; short-circuiting to fallback",
            self.rate_limit,
        )
        return False

    # ------------------------------------------------------------------
    # Symbol / date normalization
    # ------------------------------------------------------------------
    @classmethod
    def normalize_symbol(cls, symbol: str) -> str:
        """Normalize common A-share symbols to Tushare ``ts_code`` format."""

        raw = str(symbol or "").strip().upper().replace("_", ".")
        if not raw:
            return ""

        suffix_match = re.fullmatch(r"(\d{6})\.(SH|SS|SZ|BJ)", raw)
        if suffix_match:
            code, exchange = suffix_match.group(1), suffix_match.group(2)
            # Yahoo / this system uses ``.SS`` for the Shanghai exchange, while
            # Tushare's ``ts_code`` uses ``.SH``. Map it so Shanghai stocks and
            # ETFs (e.g. ``600519.SS`` / ``510300.SS``) resolve instead of
            # silently returning an empty frame.
            if exchange == "SS":
                exchange = "SH"
            return f"{code}.{exchange}"

        prefix_match = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", raw)
        if prefix_match:
            return f"{prefix_match.group(2)}.{prefix_match.group(1)}"

        if re.fullmatch(r"\d{6}", raw):
            exchange = cls._infer_exchange(raw)
            return f"{raw}.{exchange}" if exchange else raw

        return raw

    @staticmethod
    def _infer_exchange(code: str) -> Optional[str]:
        if code.startswith(("43", "83", "87", "88", "92")):
            return "BJ"
        if code.startswith(("5", "6", "9")):
            return "SH"
        if code.startswith(("0", "1", "2", "3")):
            return "SZ"
        return None

    @staticmethod
    def _format_tushare_date(value: Optional[date | datetime | str]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        text = str(value).strip()
        if not text:
            return None
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 8:
            return digits[:8]
        return text

    @staticmethod
    def _iso_trade_date(value: Any) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) >= 8:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
        return str(value or "")

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _latest_row(frame: pd.DataFrame, date_col: str) -> pd.Series:
        """Return the most recent row of a Tushare frame by its date column."""
        if date_col in getattr(frame, "columns", []):
            frame = frame.sort_values(date_col, ascending=False)
        return frame.iloc[0]

    @classmethod
    def _is_supported_ts_code(cls, ts_code: str) -> bool:
        return bool(re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", ts_code or ""))

    @classmethod
    def _is_fund_ts_code(cls, ts_code: str) -> bool:
        code = str(ts_code or "").split(".", 1)[0]
        return code.startswith(_FUND_PREFIXES)

    # ------------------------------------------------------------------
    # Tushare client
    # ------------------------------------------------------------------
    def _get_token(self) -> str:
        token = str(self.api_key or os.getenv("TUSHARE_TOKEN") or os.getenv("TS_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("Tushare token missing; set TUSHARE_TOKEN in the environment")
        return token

    def _get_pro_client(self):
        if self._pro_client is not None:
            return self._pro_client

        token = self._get_token()
        try:
            ts = self._tushare_module
            if ts is None:
                import tushare as ts  # type: ignore[import-not-found]

            # Current tushare accepts token in pro_api(); set_token is kept as a
            # compatibility fallback for older installs.
            try:
                self._pro_client = ts.pro_api(token)
            except TypeError:
                ts.set_token(token)
                self._pro_client = ts.pro_api()
            return self._pro_client
        except ImportError as exc:
            raise RuntimeError("tushare package is not installed") from exc
        except Exception as exc:
            raise RuntimeError(f"tushare initialization failed: {type(exc).__name__}") from exc

    def _call_daily_endpoint(
        self,
        ts_code: str,
        *,
        start_date: Optional[date | datetime | str] = None,
        end_date: Optional[date | datetime | str] = None,
    ) -> tuple[pd.DataFrame, str]:
        pro = self._get_pro_client()
        kwargs: dict[str, Any] = {"ts_code": ts_code}
        start = self._format_tushare_date(start_date)
        end = self._format_tushare_date(end_date)
        if start:
            kwargs["start_date"] = start
        if end:
            kwargs["end_date"] = end

        if self._is_fund_ts_code(ts_code) and hasattr(pro, "fund_daily"):
            return pro.fund_daily(**kwargs), "fund"
        return pro.daily(**kwargs), "stock"

    # ------------------------------------------------------------------
    # BaseDataProvider interface
    # ------------------------------------------------------------------
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch daily A-share / ETF history from Tushare Pro."""

        if str(interval or "").strip().lower() not in _DAILY_INTERVALS:
            return pd.DataFrame()

        ts_code = self.normalize_symbol(symbol)
        if not self._is_supported_ts_code(ts_code):
            return pd.DataFrame()

        # Cache key uses day-granularity dates so two reads on the same trading
        # day (e.g. repeated quote refreshes that pass ``datetime.now()``) hit
        # the same entry instead of refetching.
        cache_key = (
            "historical",
            ts_code,
            self._format_tushare_date(start_date),
            self._format_tushare_date(end_date),
        )
        cached = self._cache.get(cache_key)
        if cached is not self._cache._MISS:
            return cached.copy()

        # Throttle guards the real API call; on exhaustion degrade to an empty
        # frame — the existing contract callers already handle.
        if not self._acquire_or_short_circuit():
            return pd.DataFrame()

        raw, asset_type = self._call_daily_endpoint(
            ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        frame = self._normalize_daily_frame(raw, ts_code=ts_code, asset_type=asset_type)
        self._cache.set(cache_key, frame, self._ttl_for(_DEFAULT_TTL_HISTORICAL))
        return frame.copy()

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        """Return the latest available Tushare daily bar as an EOD snapshot."""

        ts_code = self.normalize_symbol(symbol)
        if not self._is_supported_ts_code(ts_code):
            return {"symbol": symbol, "error": "unsupported_tushare_symbol", "source": self.name}

        end = datetime.now()
        start = end - timedelta(days=21)
        frame = self.get_historical_data(ts_code, start_date=start, end_date=end, interval="1d")
        if frame.empty:
            return {"symbol": ts_code, "error": "empty_eod_snapshot", "source": self.name}

        latest = frame.iloc[-1]
        as_of = frame.index[-1]
        as_of_iso = as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else str(as_of)
        price = self._to_float(latest.get("close"))
        pct_chg = self._to_float(latest.get("pct_chg"))
        previous_close = price / (1 + pct_chg / 100) if pct_chg != -100 else 0.0
        change = self._to_float(latest.get("change"), price - previous_close)
        timestamp = as_of.to_pydatetime() if hasattr(as_of, "to_pydatetime") else as_of
        return {
            "symbol": ts_code,
            "price": price,
            "change": change,
            "change_percent": pct_chg,
            "volume": self._to_float(latest.get("volume")),
            "timestamp": timestamp,
            "as_of": as_of_iso,
            "source": self.name,
            "mode": "eod_snapshot",
        }

    def get_stock_valuation(self, symbol: str) -> dict[str, Any]:
        """Per-stock EOD valuation (PE/PB/市值/换手率) from Tushare ``daily_basic``.

        Returns the same display shape the AKShare/Tencent valuation produces
        (``market_cap`` in raw yuan), so it can be wired in as a primary source
        for the leader-detail view where the AKShare/EastMoney spot scrape is
        frequently blocked or slow. EOD figures — acceptable for research detail.
        """
        ts_code = self.normalize_symbol(symbol)
        if not self._is_supported_ts_code(ts_code):
            return {"symbol": symbol, "error": "unsupported_tushare_symbol", "source": self.name}

        cache_key = ("valuation", str(symbol), ts_code)
        cached = self._cache.get(cache_key)
        if cached is not self._cache._MISS:
            return dict(cached)

        # Throttle the real API call; on exhaustion degrade to a fallback-shaped
        # error dict (callers already branch on ``error``) — never raise.
        if not self._acquire_or_short_circuit():
            return {"symbol": symbol, "error": "tushare_rate_limited", "source": self.name}

        try:
            pro = self._get_pro_client()
            end = datetime.now()
            start = end - timedelta(days=21)
            frame = pro.daily_basic(
                ts_code=ts_code,
                start_date=self._format_tushare_date(start),
                end_date=self._format_tushare_date(end),
            )
        except Exception as exc:  # noqa: BLE001 - any client error degrades to fallback
            return {
                "symbol": symbol,
                "error": f"tushare_daily_basic_failed: {type(exc).__name__}",
                "source": self.name,
            }

        if frame is None or getattr(frame, "empty", True):
            return {"symbol": symbol, "error": "empty_daily_basic", "source": self.name}

        row = self._latest_row(frame, "trade_date")
        total_mv = self._to_float(row.get("total_mv"))  # 万元
        result = {
            "symbol": str(symbol),
            "name": "",
            "market_cap": total_mv * 10000.0,  # 万元 -> 元
            "pe_ttm": self._to_float(row.get("pe_ttm")),
            "pb": self._to_float(row.get("pb")),
            "turnover": self._to_float(row.get("turnover_rate")),
            "amount": 0.0,
            "change_pct": 0.0,
            "source": self.name,
        }
        self._cache.set(cache_key, result, self._ttl_for(_DEFAULT_TTL_VALUATION))
        return result

    def get_stock_financial_data(self, symbol: str) -> dict[str, Any]:
        """Per-stock financials (ROE / 营收同比 / 净利同比) from ``fina_indicator``."""
        ts_code = self.normalize_symbol(symbol)
        neutral = {"roe": 0.0, "revenue_yoy": 0.0, "profit_yoy": 0.0}
        if not self._is_supported_ts_code(ts_code):
            return {**neutral, "error": "unsupported_tushare_symbol", "source": self.name}

        cache_key = ("financial", ts_code)
        cached = self._cache.get(cache_key)
        if cached is not self._cache._MISS:
            return dict(cached)

        if not self._acquire_or_short_circuit():
            return {**neutral, "error": "tushare_rate_limited", "source": self.name}

        try:
            pro = self._get_pro_client()
            frame = pro.fina_indicator(ts_code=ts_code)
        except Exception as exc:  # noqa: BLE001 - any client error degrades to fallback
            return {**neutral, "error": f"tushare_fina_indicator_failed: {type(exc).__name__}", "source": self.name}

        if frame is None or getattr(frame, "empty", True):
            return {**neutral, "error": "empty_fina_indicator", "source": self.name}

        row = self._latest_row(frame, "end_date")
        result = {
            "roe": self._to_float(row.get("roe")),
            "revenue_yoy": self._to_float(row.get("or_yoy")),
            "profit_yoy": self._to_float(row.get("netprofit_yoy")),
            "source": self.name,
        }
        # Financials only change quarterly -> a longer TTL is safe.
        self._cache.set(cache_key, result, self._ttl_for(_DEFAULT_TTL_FINANCIAL))
        return result

    def get_financial_indicators(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Historical ``fina_indicator`` with ``ann_date`` (point-in-time, for factors).

        Returns the full quarterly frame (incl. ``ann_date``/``end_date`` and the
        indicator columns) for ``symbol`` like ``'600000.SH'`` between ``start`` and
        ``end`` (``YYYYMMDD``). Degrades to an empty frame on rate-limit exhaustion,
        matching the existing read-path contract.
        """
        ts_code = self.normalize_symbol(symbol)
        if not self._is_supported_ts_code(ts_code):
            return pd.DataFrame()
        if not self._acquire_or_short_circuit():
            return pd.DataFrame()
        pro = self._get_pro_client()
        df = pro.fina_indicator(
            ts_code=ts_code,
            start_date=self._format_tushare_date(start),
            end_date=self._format_tushare_date(end),
        )
        return df if df is not None else pd.DataFrame()

    def get_moneyflow(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Historical ``moneyflow`` (per-day net inflow components, for factors).

        Returns the daily moneyflow frame (incl. ``trade_date`` and the
        ``net_mf_amount`` / buy-sell amount columns) for ``symbol`` between ``start``
        and ``end`` (``YYYYMMDD``). Degrades to an empty frame on rate-limit
        exhaustion.
        """
        ts_code = self.normalize_symbol(symbol)
        if not self._is_supported_ts_code(ts_code):
            return pd.DataFrame()
        if not self._acquire_or_short_circuit():
            return pd.DataFrame()
        pro = self._get_pro_client()
        df = pro.moneyflow(
            ts_code=ts_code,
            start_date=self._format_tushare_date(start),
            end_date=self._format_tushare_date(end),
        )
        return df if df is not None else pd.DataFrame()

    def is_available(self) -> bool:
        """Check token/client availability without using BaseDataProvider's AAPL probe."""

        try:
            today = datetime.now()
            start = today - timedelta(days=7)
            self.get_trade_calendar(start_date=start, end_date=today, exchange="SSE")
            return True
        except Exception:
            return False

    def health_check(self) -> dict[str, Any]:
        """Report whether Tushare is actually usable, with a classified reason.

        Distinguishes ``ok`` / ``token_missing`` / ``token_invalid`` /
        ``rate_limited`` / ``error`` so a configured-but-dead token (or a
        per-minute rate limit) is surfaced instead of silently degrading A-share
        data to the slow AKShare fallback.
        """
        try:
            self._get_pro_client()
        except RuntimeError as exc:
            msg = str(exc)
            reason = "token_missing" if "token missing" in msg.lower() else "init_error"
            return {"ok": False, "reason": reason, "detail": msg}

        try:
            today = datetime.now()
            start = today - timedelta(days=7)
            self.get_trade_calendar(start_date=start, end_date=today, exchange="SSE")
            return {"ok": True, "reason": "ok", "detail": "tushare reachable"}
        except Exception as exc:  # noqa: BLE001 - classify any client error
            msg = str(exc)
            low = msg.lower()
            if "您的token" in msg or "token" in low:
                reason = "token_invalid"
            elif "每分钟" in msg or "频率" in msg or "积分" in msg or "rate" in low or "limit" in low:
                reason = "rate_limited"
            else:
                reason = "error"
            return {"ok": False, "reason": reason, "detail": f"{type(exc).__name__}: {msg}"}

    # ------------------------------------------------------------------
    # Tushare-specific helpers for A-share research workflows
    # ------------------------------------------------------------------
    def get_trade_calendar(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        *,
        exchange: str = "SSE",
        only_open: bool = True,
    ) -> list[str]:
        pro = self._get_pro_client()
        kwargs: dict[str, Any] = {
            "exchange": str(exchange or "SSE").strip().upper(),
            "start_date": self._format_tushare_date(start_date),
            "end_date": self._format_tushare_date(end_date),
        }
        if only_open:
            kwargs["is_open"] = "1"
        df = pro.trade_cal(**kwargs)
        if df is None or df.empty or "cal_date" not in df.columns:
            return []
        return sorted(self._iso_trade_date(value) for value in df["cal_date"].dropna().tolist())

    def get_stock_basic(self, *, list_status: str = "L") -> pd.DataFrame:
        pro = self._get_pro_client()
        return pro.stock_basic(
            exchange="",
            list_status=list_status,
            fields="ts_code,symbol,name,area,industry,list_date",
        )

    def get_index_constituents(
        self,
        index_code: str,
        trade_date: Optional[date | datetime | str] = None,
    ) -> list[str]:
        """Constituents of an index via Tushare ``index_weight``.

        ``index_weight`` returns one row per ``(trade_date, con_code)``; weights
        are published monthly, so a plain query without a single ``trade_date``
        spans several periods. We keep only the latest published ``trade_date``
        and return its ``con_code`` list (e.g. ``'600519.SH'``), de-duplicated
        while preserving first-seen order.

        ``trade_date=None`` (default) keeps the legacy behavior: query the last
        ~90 days and return the *current* (latest published) constituents.

        When ``trade_date`` is given, the constituents are returned **as-of** that
        date (point-in-time, survivorship-bias-free): the query window ends at the
        as-of date and we keep the latest published period ``<=`` it. A 120-day
        lookback ensures at least one monthly publication lands inside the window.
        Degrades to an empty list on rate-limit exhaustion, matching the read-path
        contract.
        """
        code = str(index_code) if "." in str(index_code) else self.normalize_symbol(index_code)
        if not self._acquire_or_short_circuit():
            return []
        pro = self._get_pro_client()
        if trade_date is not None:
            # Point-in-time: window ENDS at the as-of date so no future (look-ahead)
            # publication can leak in. 120d lookback comfortably spans a monthly cycle.
            as_of = self._format_tushare_date(trade_date)
            end_dt = trade_date if isinstance(trade_date, (date, datetime)) else None
            if end_dt is None:
                end_dt = datetime.strptime(str(as_of), "%Y%m%d")
            start = self._format_tushare_date(end_dt - timedelta(days=120))
            df = pro.index_weight(index_code=code, start_date=start, end_date=as_of)
        else:
            end = datetime.now()
            start = end - timedelta(days=90)
            df = pro.index_weight(
                index_code=code,
                start_date=self._format_tushare_date(start),
                end_date=self._format_tushare_date(end),
            )
        if df is None or getattr(df, "empty", True) or "con_code" not in df.columns:
            return []
        if "trade_date" in df.columns:
            latest = df["trade_date"].astype(str).max()
            df = df[df["trade_date"].astype(str) == latest]
        codes = [str(c) for c in df["con_code"].tolist() if c is not None and str(c)]
        # De-duplicate while preserving first-seen order.
        return list(dict.fromkeys(codes))

    def get_suspended_symbols(self, trade_date: date | datetime | str) -> set[str]:
        """Set of ts_codes SUSPENDED (停牌) on ``trade_date`` via ``suspend_d``.

        Queries ``suspend_d(suspend_type='S', trade_date=...)`` — the by-date form
        (per-symbol queries are unreliable). Returns the set of ``ts_code`` values
        suspended that day so the factor harness can exclude un-tradable names from
        the eligible cross-section. Degrades to an empty set on no data / any client
        error / rate-limit exhaustion (never raises), matching the read-path
        contract.
        """
        if not self._acquire_or_short_circuit():
            return set()
        day = self._format_tushare_date(trade_date)
        try:
            pro = self._get_pro_client()
            df = pro.suspend_d(suspend_type="S", trade_date=day)
        except Exception as exc:  # noqa: BLE001 - any client error degrades to empty set
            logger.warning("Tushare suspend_d failed for %s: %s", day, exc)
            return set()
        if df is None or getattr(df, "empty", True) or "ts_code" not in df.columns:
            return set()
        return {str(c) for c in df["ts_code"].tolist() if c is not None and str(c)}

    def get_market_mood(self, trade_date: date | datetime | str, *, include_bj: bool = True) -> dict[str, Any]:
        """Port the QMT market-mood lens to this project's provider layer."""

        pro = self._get_pro_client()
        day = self._format_tushare_date(trade_date) or ""
        df = pro.daily(trade_date=day, fields="ts_code,trade_date,pct_chg,vol,amount")
        market_df = self._filter_a_share_daily(df, include_bj=include_bj)
        stock_count = len(market_df)
        rise_count = int((market_df["pct_chg"] > 0).sum()) if stock_count else 0
        fall_count = int((market_df["pct_chg"] < 0).sum()) if stock_count else 0
        flat_count = int((market_df["pct_chg"] == 0).sum()) if stock_count else 0
        touch_counts = self._get_limit_touch_counts(pro, day)
        touch_count = touch_counts["limit_up_count"] + touch_counts["blowup_count"]
        blowup_rate = touch_counts["blowup_count"] / touch_count if touch_count else 0.0

        result: dict[str, Any] = {
            "trade_date": day,
            "include_bj": include_bj,
            "stock_count": stock_count,
            "total_amount_yi": round(self._to_float(market_df["amount"].sum()) / 100000, 2)
            if stock_count
            else 0.0,
            "total_vol_wan_shou": round(self._to_float(market_df["vol"].sum()) / 10000, 2)
            if stock_count
            else 0.0,
            "rise_count": rise_count,
            "fall_count": fall_count,
            "flat_count": flat_count,
            "rise_ratio": round(rise_count / stock_count, 4) if stock_count else 0.0,
            "fall_ratio": round(fall_count / stock_count, 4) if stock_count else 0.0,
            "flat_ratio": round(flat_count / stock_count, 4) if stock_count else 0.0,
            "market_median_pct_chg": round(self._to_float(market_df["pct_chg"].median()), 4)
            if stock_count
            else 0.0,
            "strong_count": int((market_df["pct_chg"] >= 3).sum()) if stock_count else 0,
            "weak_count": int((market_df["pct_chg"] <= -3).sum()) if stock_count else 0,
            "big_drop_count": int((market_df["pct_chg"] <= -5).sum()) if stock_count else 0,
            "source": self.name,
            "mode": "eod_snapshot",
        }
        result.update(touch_counts)
        result["touch_count"] = touch_count
        result["blowup_rate"] = round(blowup_rate, 4)
        return result

    def get_industry_moneyflow(self, trade_date: date | datetime | str) -> pd.DataFrame:
        pro = self._get_pro_client()
        return pro.moneyflow_ind_ths(trade_date=self._format_tushare_date(trade_date))

    def get_dc_board_status(
        self,
        trade_date: date | datetime | str,
        *,
        idx_type: str = "行业板块",
    ) -> pd.DataFrame:
        pro = self._get_pro_client()
        return pro.dc_index(
            trade_date=self._format_tushare_date(trade_date),
            idx_type=idx_type,
            fields="ts_code,trade_date,name,leading,leading_code,pct_change,leading_pct,total_mv,turnover_rate,up_num,down_num,idx_type,level",
        )

    # ------------------------------------------------------------------
    # Normalization internals
    # ------------------------------------------------------------------
    def _normalize_daily_frame(
        self,
        raw: pd.DataFrame,
        *,
        ts_code: str,
        asset_type: str,
    ) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()

        frame = raw.copy()
        frame.columns = frame.columns.str.lower()
        if "trade_date" not in frame.columns:
            return pd.DataFrame()

        frame["date"] = pd.to_datetime(frame["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date").set_index("date")
        frame.index.name = "date"
        if "vol" in frame.columns and "volume" not in frame.columns:
            frame = frame.rename(columns={"vol": "volume"})

        for column in ["open", "high", "low", "close", "volume", "amount", "pct_chg", "change"]:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        for column in ["open", "high", "low", "close", "volume"]:
            if column not in frame.columns:
                frame[column] = 0.0
        if "returns" not in frame.columns and "close" in frame.columns:
            frame["returns"] = frame["close"].pct_change()
        frame.attrs["source"] = self.name
        frame.attrs["source_mode"] = "eod"
        frame.attrs["symbol"] = ts_code
        frame.attrs["asset_type"] = asset_type
        return frame

    def _filter_a_share_daily(self, df: pd.DataFrame, *, include_bj: bool) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["ts_code", "pct_chg", "vol", "amount"])
        frame = df.copy()
        frame.columns = frame.columns.str.lower()
        for column in ["pct_chg", "vol", "amount"]:
            if column not in frame.columns:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame = frame[frame["amount"] > 0]
        suffixes = {".SH", ".SZ", ".BJ"} if include_bj else {".SH", ".SZ"}
        return frame[frame["ts_code"].astype(str).str.upper().str.endswith(tuple(suffixes))].copy()

    def _get_limit_touch_counts(self, pro: Any, trade_date: str) -> dict[str, Any]:
        def load(limit_type: str) -> pd.DataFrame:
            try:
                data = pro.limit_list_d(trade_date=trade_date, limit_type=limit_type)
                return data if isinstance(data, pd.DataFrame) else pd.DataFrame()
            except Exception as exc:
                logger.warning("Tushare limit_list_d failed for %s: %s", limit_type, exc)
                return pd.DataFrame()

        limit_up = load("U")
        limit_down = load("D")
        blowup = load("Z")
        max_board_height = 0
        if not limit_up.empty and "limit_times" in limit_up.columns:
            max_board_height = int(pd.to_numeric(limit_up["limit_times"], errors="coerce").fillna(0).max())
        return {
            "limit_up_count": len(limit_up),
            "limit_down_count": len(limit_down),
            "blowup_count": len(blowup),
            "max_board_height": max_board_height,
        }
