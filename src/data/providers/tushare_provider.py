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
from datetime import date, datetime, timedelta
from typing import Any, Optional

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

        raw, asset_type = self._call_daily_endpoint(
            ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        return self._normalize_daily_frame(raw, ts_code=ts_code, asset_type=asset_type)

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

    def is_available(self) -> bool:
        """Check token/client availability without using BaseDataProvider's AAPL probe."""

        try:
            today = datetime.now()
            start = today - timedelta(days=7)
            self.get_trade_calendar(start_date=start, end_date=today, exchange="SSE")
            return True
        except Exception:
            return False

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
