"""
同花顺主导的行业数据适配器（THS-first Adapter）
将 THS 作为行业热度主数据源，AKShare / Tushare / Sina / 腾讯仅作为补充与兜底。
"""

import copy
import pandas as pd
from typing import Dict, Any, List, Optional
import logging
import requests
import py_mini_racer
import json
import fcntl
import re
import akshare as ak
import time
from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from . import _tushare_normalize
from .sina_provider import SinaFinanceProvider
from .akshare_provider import AKShareProvider
from .circuit_breaker import CircuitBreaker
from .sina_ths import parsing as _parsing
from .sina_ths.mappings import (
    INDUSTRY_ENRICHMENT_ALIASES,
    SINA_NEW_NODE_NAME_MAP,
    SINA_PROXY_NODE_NAME_MAP,
    SINA_TO_THS_MAP,  # noqa: F401  re-exported for backward-compatible import path
    SW_INDEX_ALIAS_MAP,
    map_sina_to_ths,
    map_ths_to_sina,
)

logger = logging.getLogger(__name__)


class SinaIndustryAdapter:
    """
    同花顺主导的行业数据适配器（THS-first Adapter）

    数据来源：
    - 同花顺（THS）：行业目录、行业热度、涨跌幅、资金流向、行业指数、领涨股
    - AKShare：行业补充元数据、成分股、财务和历史行情
    - Tushare：盘后行业资金流、东方财富板块状态、领涨股和市场情绪兜底
    - 新浪财经（Sina Finance）：行业列表、成分股、实时行情兜底
    - 腾讯财经：单股估值核心字段兜底

    使用示例:
        from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
        from src.analytics.industry_analyzer import IndustryAnalyzer

        provider = SinaIndustryAdapter()
        analyzer = IndustryAnalyzer(provider)

        hot_industries = analyzer.rank_industries(top_n=10)
    """

    _symbol_cache_lock = threading.Lock()

    _stock_name_to_symbol_cache: Dict[str, str] = {}
    _stock_name_cache_time: float = 0
    _stock_name_cache_loaded: bool = False
    _ths_catalog_shared_cache: pd.DataFrame | None = None
    _ths_catalog_shared_cache_time: float = 0
    _ths_summary_shared_cache: pd.DataFrame | None = None
    _ths_summary_shared_cache_time: float = 0
    _ths_request_token_lock = threading.Lock()
    _ths_js_content_cache: str | None = None
    _ths_hexin_v_cache: str | None = None
    _ths_hexin_v_cache_time: float = 0
    _ths_hexin_v_ttl_seconds: int = 45
    _sina_cached_stock_nodes: frozenset[str] | None = None
    _sina_cached_stock_nodes_time: float = 0
    _candidate_industry_names_cache: Dict[str, tuple[str, ...]] = {}
    _cached_sina_industry_codes_cache: Dict[str, Dict[str, Any]] = {}
    _cached_sina_industry_codes_ttl_seconds: int = 600
    _sina_industry_list_shared_cache: pd.DataFrame | None = None
    _sina_industry_list_shared_cache_time: float = 0
    _sina_industry_list_ttl_seconds: int = 600
    _sina_industry_list_lock = threading.Lock()
    _ths_catalog_snapshot_path = (
        Path(__file__).resolve().parents[3] / "cache" / "ths_industry_catalog_snapshot.json"
    )
    _symbol_cache_path = (
        Path(__file__).resolve().parents[3] / "cache" / "industry_symbol_cache.json"
    )
    _history_cache_path = Path(__file__).resolve().parents[3] / "cache" / "history_cache.json"
    _industry_market_cap_snapshot_path = (
        Path(__file__).resolve().parents[3] / "cache" / "industry_market_cap_snapshot.json"
    )
    _history_cache: Dict[str, Any] = {}
    _history_cache_loaded: bool = False
    _market_cap_snapshot_payload_cache: Dict[str, Any] | None = None
    _market_cap_snapshot_payload_cache_meta: tuple[str, int, int] | None = None
    _market_cap_snapshot_stale_after_hours: int = 24
    _akshare_valuation_snapshot_cache: pd.DataFrame | None = None
    _akshare_valuation_snapshot_cache_time: float = 0
    _akshare_valuation_snapshot_failure_at: float = 0
    _akshare_valuation_snapshot_ttl_seconds: int = 4 * 60 * 60
    _akshare_valuation_snapshot_cooldown_seconds: int = 5 * 60
    _akshare_valuation_snapshot_refresh_lock = threading.Lock()
    _akshare_valuation_snapshot_refresh_executor = ThreadPoolExecutor(max_workers=1)
    _akshare_valuation_snapshot_refresh_future: Future | None = None
    _circuit_breakers: Dict[str, CircuitBreaker] = {}
    _circuit_breaker_lock = threading.Lock()

    # Pure leaf helpers extracted to ./sina_ths/parsing.py. Re-bound under their
    # historical method names via staticmethod aliases so call sites and behavior
    # are unchanged.
    _numeric_series_or_default = staticmethod(_parsing.numeric_series_or_default)
    _build_name_aliases = staticmethod(_parsing.build_name_aliases)

    @classmethod
    def _ensure_symbol_cache_loaded(cls):
        if cls._stock_name_cache_loaded:
            return

        cache_path = cls._symbol_cache_path
        try:
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                cache = payload.get("cache", {})
                if isinstance(cache, dict):
                    for name, code in cache.items():
                        clean_name = str(name or "").strip()
                        clean_code = str(code or "").strip()
                        if clean_name and clean_code.isdigit():
                            cls._stock_name_to_symbol_cache[clean_name] = clean_code
                    cls._stock_name_cache_time = float(payload.get("updated_at") or 0)
                    logger.info(
                        "Loaded persistent industry symbol cache with %s entries",
                        len(cls._stock_name_to_symbol_cache),
                    )
        except Exception as e:
            logger.warning(f"Failed to load persistent symbol cache: {e}")
        finally:
            cls._stock_name_cache_loaded = True

    @classmethod
    def _persist_symbol_cache(cls):
        if not cls._stock_name_to_symbol_cache:
            return

        try:
            cls._symbol_cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": cls._stock_name_cache_time or time.time(),
                "cache": dict(sorted(cls._stock_name_to_symbol_cache.items())),
            }
            cls._symbol_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist symbol cache: {e}")

    @classmethod
    def _update_symbol_cache_from_pairs(cls, pairs: List[tuple[str, str]]):
        """把已知的 股票名 -> 代码 对写回共享缓存。"""
        cls._ensure_symbol_cache_loaded()
        changed = False
        for name, code in pairs:
            clean_name = str(name or "").strip()
            clean_code = str(code or "").strip()
            if clean_name and clean_code.isdigit():
                for alias in cls._build_name_aliases(clean_name):
                    if cls._stock_name_to_symbol_cache.get(alias) != clean_code:
                        cls._stock_name_to_symbol_cache[alias] = clean_code
                        changed = True
        if changed:
            cls._stock_name_cache_time = time.time()
            cls._persist_symbol_cache()

    @classmethod
    def _ensure_history_cache_loaded(cls):
        if cls._history_cache_loaded:
            return
        try:
            if cls._history_cache_path.exists():
                with open(cls._history_cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cls._history_cache = data.get("cache", {})
                    logger.info("Loaded history cache with %s entries", len(cls._history_cache))
        except Exception as e:
            logger.warning(f"Failed to load history cache: {e}")
        finally:
            cls._history_cache_loaded = True

    @classmethod
    def _persist_history_cache(cls):
        try:
            cls._history_cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"updated_at": time.time(), "cache": cls._history_cache}
            with open(cls._history_cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist history cache: {e}")

    @classmethod
    def _load_persistent_ths_catalog(cls) -> pd.DataFrame:
        try:
            if not cls._ths_catalog_snapshot_path.exists():
                return pd.DataFrame()
            payload = json.loads(cls._ths_catalog_snapshot_path.read_text(encoding="utf-8"))
            rows = payload.get("data", [])
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            logger.info("Loaded persistent THS industry catalog with %s entries", len(df))
            return df
        except Exception as exc:
            logger.warning(f"Failed to load persistent THS catalog snapshot: {exc}")
            return pd.DataFrame()

    @classmethod
    def _persist_ths_catalog(cls, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        try:
            cls._ths_catalog_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": time.time(),
                "data": df.to_dict(orient="records"),
            }
            cls._ths_catalog_snapshot_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Failed to persist THS catalog snapshot: {exc}")

    @classmethod
    def _reset_market_cap_snapshot_payload_cache(cls) -> None:
        cls._market_cap_snapshot_payload_cache = None
        cls._market_cap_snapshot_payload_cache_meta = None

    @classmethod
    def _load_market_cap_snapshot_payload(cls) -> Dict[str, Any]:
        try:
            path = cls._industry_market_cap_snapshot_path
            if not path.exists():
                cls._reset_market_cap_snapshot_payload_cache()
                return {}
            stat = path.stat()
            cache_meta = cls._market_cap_snapshot_payload_cache_meta
            if cls._market_cap_snapshot_payload_cache is not None and cache_meta == (
                str(path),
                stat.st_mtime_ns,
                stat.st_size,
            ):
                return copy.deepcopy(cls._market_cap_snapshot_payload_cache)

            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
            cls._market_cap_snapshot_payload_cache = copy.deepcopy(payload)
            cls._market_cap_snapshot_payload_cache_meta = (
                str(path),
                stat.st_mtime_ns,
                stat.st_size,
            )
            return payload
        except Exception as e:
            cls._reset_market_cap_snapshot_payload_cache()
            logger.warning(f"Failed to load industry market cap snapshot payload: {e}")
            return {}

    @classmethod
    def _load_persistent_market_cap_snapshot(cls) -> Dict[str, Any]:
        try:
            payload = cls._load_market_cap_snapshot_payload()
            data = payload.get("data", {})
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load industry market cap snapshot: {e}")
            return {}

    @classmethod
    def _write_market_cap_snapshot_payload(cls, payload: Dict[str, Any]) -> None:
        cls._industry_market_cap_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cls._industry_market_cap_snapshot_path.with_name(
            f"{cls._industry_market_cap_snapshot_path.name}.tmp"
        )
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(cls._industry_market_cap_snapshot_path)
        try:
            stat = cls._industry_market_cap_snapshot_path.stat()
            cls._market_cap_snapshot_payload_cache = copy.deepcopy(
                payload if isinstance(payload, dict) else {}
            )
            cls._market_cap_snapshot_payload_cache_meta = (
                str(cls._industry_market_cap_snapshot_path),
                stat.st_mtime_ns,
                stat.st_size,
            )
        except OSError:
            cls._reset_market_cap_snapshot_payload_cache()

    @classmethod
    def _locked_market_cap_snapshot_update(cls, updater) -> None:
        lock_path = cls._industry_market_cap_snapshot_path.with_name(
            f"{cls._industry_market_cap_snapshot_path.name}.lock"
        )
        cls._industry_market_cap_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            payload = cls._load_market_cap_snapshot_payload()
            updated = updater(payload if isinstance(payload, dict) else {})
            if updated is None:
                return
            cls._write_market_cap_snapshot_payload(updated)

    @classmethod
    def get_persistent_market_cap_snapshot_status(cls) -> Dict[str, Any]:
        snapshot = cls._load_persistent_market_cap_snapshot()
        if not snapshot:
            return {
                "entries": 0,
                "fresh_entries": 0,
                "stale_entries": 0,
                "min_age_hours": None,
                "max_age_hours": None,
                "source_counts": {},
            }

        ages: List[float] = []
        stale_entries = 0
        source_counts: Counter[str] = Counter()
        now = time.time()
        stale_after_hours = cls._market_cap_snapshot_stale_after_hours

        for item in snapshot.values():
            source = str(item.get("market_cap_source", "unknown")).strip() or "unknown"
            source_counts[source] += 1
            updated_at = item.get("updated_at")
            if updated_at is None:
                continue
            age_hours = max(0.0, (now - float(updated_at)) / 3600)
            ages.append(age_hours)
            if age_hours >= stale_after_hours:
                stale_entries += 1

        entries = len(snapshot)
        return {
            "entries": entries,
            "fresh_entries": max(0, entries - stale_entries),
            "stale_entries": stale_entries,
            "min_age_hours": min(ages) if ages else None,
            "max_age_hours": max(ages) if ages else None,
            "source_counts": dict(source_counts),
        }

    @classmethod
    def _persist_market_cap_snapshot(cls, df: pd.DataFrame) -> None:
        try:
            if df.empty or "industry_code" not in df.columns:
                return

            caps = cls._numeric_series_or_default(df, "total_market_cap", 0.0)
            sources = df.get("market_cap_source", pd.Series("unknown", index=df.index)).astype(str)
            valid_mask = (
                df["industry_code"].astype(str).str.strip().ne("")
                & caps.gt(1e8)
                & ~sources.str.startswith("estimated")
                & ~sources.str.startswith("snapshot_")
                & sources.ne("unknown")
            )
            if not valid_mask.any():
                return

            snapshot_rows = []
            for _, row in df.loc[valid_mask].iterrows():
                code = str(row.get("industry_code", "")).strip()
                if not code:
                    continue
                snapshot_rows.append(
                    {
                        "industry_code": code,
                        "industry_name": str(row.get("industry_name", "")).strip(),
                        "total_market_cap": float(row.get("total_market_cap", 0) or 0),
                        "market_cap_source": str(row.get("market_cap_source", "unknown")).strip()
                        or "unknown",
                    }
                )
            if not snapshot_rows:
                return

            def update_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
                existing = payload.get("data", {})
                if not isinstance(existing, dict):
                    existing = {}
                else:
                    existing = dict(existing)
                now = time.time()
                changed = False
                for item in snapshot_rows:
                    current = existing.get(item["industry_code"], {})
                    current_name = (
                        str(current.get("industry_name", "")).strip()
                        if isinstance(current, dict)
                        else ""
                    )
                    current_source = (
                        str(current.get("market_cap_source", "unknown")).strip()
                        if isinstance(current, dict)
                        else "unknown"
                    )
                    current_cap = (
                        float(current.get("total_market_cap", 0) or 0)
                        if isinstance(current, dict)
                        else 0.0
                    )
                    same_record = (
                        current_name == item["industry_name"]
                        and current_source == item["market_cap_source"]
                        and abs(current_cap - item["total_market_cap"]) <= 1e-6
                        and isinstance(current, dict)
                        and current.get("updated_at") is not None
                    )
                    if same_record:
                        continue

                    existing[item["industry_code"]] = {
                        "industry_name": item["industry_name"],
                        "total_market_cap": item["total_market_cap"],
                        "market_cap_source": item["market_cap_source"],
                        "updated_at": now,
                    }
                    changed = True
                if not changed:
                    return None
                return {
                    "updated_at": now,
                    "data": existing,
                }

            cls._locked_market_cap_snapshot_update(update_payload)
        except Exception as e:
            logger.warning(f"Failed to persist industry market cap snapshot: {e}")

    def _apply_persistent_market_cap_snapshot(self, df: pd.DataFrame) -> bool:
        if df.empty or "industry_code" not in df.columns:
            return False

        snapshot = self.__class__._load_persistent_market_cap_snapshot()
        if not snapshot:
            return False

        if "total_market_cap" not in df.columns:
            df["total_market_cap"] = 0.0
        if "market_cap_source" not in df.columns:
            df["market_cap_source"] = "unknown"
        if "market_cap_snapshot_age_hours" not in df.columns:
            df["market_cap_snapshot_age_hours"] = pd.NA
        if "market_cap_snapshot_is_stale" not in df.columns:
            df["market_cap_snapshot_is_stale"] = False

        caps = self._numeric_series_or_default(df, "total_market_cap", 0.0)
        sources = df["market_cap_source"].astype(str).fillna("unknown")
        fill_mask = df["industry_code"].astype(str).map(
            lambda code: str(code).strip() in snapshot
        ) & (caps.le(1) | sources.eq("unknown") | sources.str.startswith("estimated"))
        if not fill_mask.any():
            return False

        def snapshot_cap(code: Any) -> float:
            item = snapshot.get(str(code).strip(), {})
            return float(item.get("total_market_cap", 0) or 0)

        def snapshot_source(code: Any) -> str:
            item = snapshot.get(str(code).strip(), {})
            source = str(item.get("market_cap_source", "unknown")).strip() or "unknown"
            return f"snapshot_{source}"

        def snapshot_age_hours(code: Any) -> float | None:
            item = snapshot.get(str(code).strip(), {})
            updated_at = item.get("updated_at")
            if updated_at is None:
                return None
            return max(0.0, (time.time() - float(updated_at)) / 3600)

        def snapshot_is_stale(code: Any) -> bool:
            age = snapshot_age_hours(code)
            if age is None:
                return False
            return age >= self.__class__._market_cap_snapshot_stale_after_hours

        df.loc[fill_mask, "total_market_cap"] = df.loc[fill_mask, "industry_code"].apply(
            snapshot_cap
        )
        df.loc[fill_mask, "market_cap_source"] = df.loc[fill_mask, "industry_code"].apply(
            snapshot_source
        )
        df.loc[fill_mask, "market_cap_snapshot_age_hours"] = df.loc[
            fill_mask, "industry_code"
        ].apply(snapshot_age_hours)
        df.loc[fill_mask, "market_cap_snapshot_is_stale"] = df.loc[
            fill_mask, "industry_code"
        ].apply(snapshot_is_stale)
        self._append_data_source(df, fill_mask, "snapshot")
        return True

    def __init__(self):
        """初始化适配器"""
        self.__class__._ensure_symbol_cache_loaded()
        self.sina = SinaFinanceProvider()
        self.akshare = AKShareProvider()
        self.tushare = self._create_tushare_provider()
        self._industry_cache: Dict[str, pd.DataFrame] = {}
        logger.info("SinaIndustryAdapter initialized")

    @staticmethod
    def _create_tushare_provider():
        try:
            from .tushare_provider import TushareProvider

            return TushareProvider()
        except Exception as exc:
            logger.warning("Tushare industry fallback initialization failed: %s", exc)
            return None

    @classmethod
    def _call_with_circuit(cls, breaker_key: str, fn, *args, **kwargs):
        with cls._circuit_breaker_lock:
            breaker = cls._circuit_breakers.get(breaker_key)
            if breaker is None:
                breaker = CircuitBreaker(
                    failure_threshold=5,
                    recovery_timeout=60.0,
                    name=f"sina_ths.{breaker_key}",
                )
                cls._circuit_breakers[breaker_key] = breaker
        return breaker.call(fn, *args, **kwargs)

    @classmethod
    def get_circuit_status(cls) -> Dict[str, Any]:
        with cls._circuit_breaker_lock:
            return {name: breaker.status() for name, breaker in cls._circuit_breakers.items()}

    def _build_symbol_cache_industry_fallback(self, industry_name: str) -> List[Dict[str, Any]]:
        """使用本地股票名缓存构造高置信度行业兜底，避免单一数据源抖动时成分股完全丢失。"""
        normalized = str(industry_name or "").strip()
        if normalized != "银行":
            return []

        bank_pattern = re.compile(r"(银行|农商行|张家港行)$")
        fallback_stocks: Dict[str, Dict[str, Any]] = {}

        try:
            cached_rows = self.sina._get_persistent_industry_stock_rows("new_jrhy")
            for row in cached_rows:
                name = str(row.get("name", "")).strip()
                symbol = str(row.get("code") or row.get("symbol") or "").strip()
                if not name or not symbol.isdigit() or not bank_pattern.search(name):
                    continue
                fallback_stocks[symbol] = {
                    "symbol": symbol,
                    "code": symbol,
                    "name": name,
                    "change_pct": float(row.get("change_pct", 0) or 0),
                    "market_cap": float(row.get("mktcap", 0) or 0) * 10000,
                    "volume": float(row.get("volume", 0) or 0),
                    "amount": float(row.get("amount", 0) or 0),
                    "pe_ratio": float(row.get("pe_ratio", 0) or 0),
                    "pb_ratio": float(row.get("pb_ratio", 0) or 0),
                }
        except Exception as e:
            logger.warning(
                f"Failed to load cached bank constituents from persistent Sina cache: {e}"
            )

        self.__class__._ensure_symbol_cache_loaded()
        for name, symbol in self.__class__._stock_name_to_symbol_cache.items():
            clean_name = str(name or "").strip()
            clean_symbol = str(symbol or "").strip()
            if not clean_symbol.isdigit() or not bank_pattern.search(clean_name):
                continue
            fallback_stocks.setdefault(
                clean_symbol,
                {
                    "symbol": clean_symbol,
                    "code": clean_symbol,
                    "name": clean_name,
                },
            )

        if fallback_stocks:
            logger.info(
                "Using symbol-cache fallback for %s with %s candidates",
                normalized,
                len(fallback_stocks),
            )
        return list(fallback_stocks.values())

    def _refine_proxy_constituents(
        self,
        industry_name: str,
        stocks: List[Dict[str, Any]],
        industry_code: str | None = None,
    ) -> List[Dict[str, Any]]:
        """对宽口径代理节点做行业内过滤，降低金融综合节点带来的误归类。"""
        normalized = str(industry_name or "").strip()
        resolved_code = str(industry_code or "").strip()
        if not stocks:
            return []

        def keep_by_predicate(predicate) -> List[Dict[str, Any]]:
            filtered = [stock for stock in stocks if predicate(str(stock.get("name", "")).strip())]
            return filtered or stocks

        if normalized == "银行" or (normalized == "银行" and resolved_code == "new_jrhy"):
            bank_pattern = re.compile(r"(银行|农商行|张家港行)$")
            return keep_by_predicate(lambda name: bool(bank_pattern.search(name)))

        if normalized == "证券" and resolved_code == "new_jrhy":
            broker_aliases = {"东方财富", "同花顺", "指南针", "大智慧"}
            return keep_by_predicate(lambda name: ("证券" in name) or (name in broker_aliases))

        if normalized == "保险" and resolved_code == "new_jrhy":
            insurer_aliases = {
                "中国平安",
                "中国太保",
                "中国人寿",
                "中国人保",
                "新华保险",
                "天茂集团",
            }
            return keep_by_predicate(
                lambda name: ("保险" in name) or ("人寿" in name) or (name in insurer_aliases)
            )

        return stocks

    def _get_ths_industry_catalog(self) -> pd.DataFrame:
        """获取 THS 行业目录，作为行业名称与代码的主索引。"""
        now = time.time()
        if (
            self.__class__._ths_catalog_shared_cache is not None
            and not self.__class__._ths_catalog_shared_cache.empty
            and now - self.__class__._ths_catalog_shared_cache_time < 1800
        ):
            return self.__class__._ths_catalog_shared_cache.copy()

        persistent_df = self.__class__._load_persistent_ths_catalog()
        if not persistent_df.empty:
            persistent_df = persistent_df.copy()
            if {"industry_name", "industry_code"}.issubset(persistent_df.columns):
                persistent_df["industry_name"] = (
                    persistent_df["industry_name"].astype(str).str.strip()
                )
                self.__class__._ths_catalog_shared_cache = persistent_df
                self.__class__._ths_catalog_shared_cache_time = now
                return persistent_df.copy()

        try:
            df = self._call_with_circuit(
                "stock_board_industry_name_ths",
                ak.stock_board_industry_name_ths,
            )
            if not df.empty:
                df = df.rename(columns={"name": "industry_name", "code": "industry_code"})
                df["industry_name"] = df["industry_name"].astype(str).str.strip()
                self.__class__._ths_catalog_shared_cache = df
                self.__class__._ths_catalog_shared_cache_time = now
                self.__class__._persist_ths_catalog(df)
                return df.copy()
        except Exception as e:
            logger.warning(f"Failed to fetch THS industry catalog: {e}")

        if (
            self.__class__._ths_catalog_shared_cache is not None
            and not self.__class__._ths_catalog_shared_cache.empty
        ):
            logger.warning("Using stale THS industry catalog cache")
            return self.__class__._ths_catalog_shared_cache.copy()

        return pd.DataFrame()

    def _get_ths_industry_summary(self, cached_only: bool = False) -> pd.DataFrame:
        """获取 THS 行业一览表，作为热度与领涨股的主数据底座。"""
        now = time.time()
        if (
            self.__class__._ths_summary_shared_cache is not None
            and not self.__class__._ths_summary_shared_cache.empty
            and now - self.__class__._ths_summary_shared_cache_time < 600
        ):
            return self.__class__._ths_summary_shared_cache.copy()

        if cached_only:
            if (
                self.__class__._ths_summary_shared_cache is not None
                and not self.__class__._ths_summary_shared_cache.empty
            ):
                logger.info("Using stale THS industry summary cache in cached_only mode")
                return self.__class__._ths_summary_shared_cache.copy()
            return pd.DataFrame()

        try:
            df = self._call_with_circuit(
                "stock_board_industry_summary_ths",
                ak.stock_board_industry_summary_ths,
            )
            if not df.empty:
                df = df.rename(
                    columns={
                        "板块": "industry_name",
                        "涨跌幅": "change_pct",
                        "总成交量": "total_volume",
                        "总成交额": "total_amount",
                        "净流入": "main_net_inflow",
                        "上涨家数": "rise_count",
                        "下跌家数": "fall_count",
                        "均价": "avg_price",
                        "领涨股": "leading_stock",
                        "领涨股-最新价": "leading_stock_price",
                        "领涨股-涨跌幅": "leading_stock_change",
                    }
                )
                df["industry_name"] = df["industry_name"].astype(str).str.strip()
                self.__class__._ths_summary_shared_cache = df
                self.__class__._ths_summary_shared_cache_time = now
                return df.copy()
        except Exception as e:
            logger.warning(f"Failed to fetch THS industry summary: {e}")

        if (
            self.__class__._ths_summary_shared_cache is not None
            and not self.__class__._ths_summary_shared_cache.empty
        ):
            logger.warning("Using stale THS industry summary cache")
            return self.__class__._ths_summary_shared_cache.copy()

        return pd.DataFrame()

    @classmethod
    def _get_ths_js_content(cls) -> str:
        cached = cls._ths_js_content_cache
        if cached:
            return cached

        with cls._ths_request_token_lock:
            cached = cls._ths_js_content_cache
            if cached:
                return cached
            cls._ths_js_content_cache = cls._call_with_circuit(
                "ths_js_content",
                ak.stock_feature.stock_fund_flow._get_file_content_ths,
                "ths.js",
            )
            return cls._ths_js_content_cache

    @classmethod
    def _get_ths_hexin_v(cls, force_refresh: bool = False) -> tuple[str, bool]:
        now = time.time()
        if (
            not force_refresh
            and cls._ths_hexin_v_cache
            and now - cls._ths_hexin_v_cache_time < cls._ths_hexin_v_ttl_seconds
        ):
            return cls._ths_hexin_v_cache, True

        js_content = cls._get_ths_js_content()
        with cls._ths_request_token_lock:
            now = time.time()
            if (
                not force_refresh
                and cls._ths_hexin_v_cache
                and now - cls._ths_hexin_v_cache_time < cls._ths_hexin_v_ttl_seconds
            ):
                return cls._ths_hexin_v_cache, True

            js_code = py_mini_racer.MiniRacer()
            js_code.eval(js_content)
            token = js_code.call("v")
            cls._ths_hexin_v_cache = token
            cls._ths_hexin_v_cache_time = now
            return token, False

    @classmethod
    def _build_ths_request_headers(
        cls,
        headers_base: Dict[str, str],
        force_refresh: bool = False,
    ) -> tuple[Dict[str, str], bool]:
        token, from_cache = cls._get_ths_hexin_v(force_refresh=force_refresh)
        headers = headers_base.copy()
        headers["hexin-v"] = token
        return headers, from_cache

    def _normalize_to_ths_industry_name(self, industry_name: str) -> str:
        """将输入名称归一为 THS 行业名，便于把 THS 作为主索引。"""
        raw_name = str(industry_name or "").strip()
        if not raw_name:
            return raw_name

        ths_catalog = self._get_ths_industry_catalog()
        if not ths_catalog.empty:
            exact = ths_catalog[ths_catalog["industry_name"] == raw_name]
            if not exact.empty:
                return raw_name

        direct_mapped = map_sina_to_ths(raw_name)
        # 这里只接受“输入名本身”或“显式别名字典”带来的候选，
        # 避免把宽泛行业名（如“医药生物”）误降到某个更窄子行业。
        candidate_names = [direct_mapped, raw_name]
        deduped = []
        seen = set()
        for name in candidate_names:
            normalized = str(name or "").strip()
            if normalized and normalized not in seen:
                deduped.append(normalized)
                seen.add(normalized)

        if not ths_catalog.empty:
            ths_catalog = ths_catalog.copy()
            ths_catalog["industry_name"] = ths_catalog["industry_name"].astype(str).str.strip()
            ths_names = set(ths_catalog["industry_name"].astype(str))

            # 1. 显式映射或候选名精确命中
            for name in deduped:
                mapped = map_sina_to_ths(name)
                if mapped in ths_names:
                    return mapped
                if name in ths_names:
                    return name

            # 2. 规范化键唯一命中
            normalized_key = self._normalize_industry_join_key(raw_name)
            ths_catalog["join_key"] = ths_catalog["industry_name"].apply(
                self._normalize_industry_join_key
            )
            exact_key_matches = ths_catalog[ths_catalog["join_key"] == normalized_key]
            if len(exact_key_matches) == 1:
                return str(exact_key_matches.iloc[0]["industry_name"])

            # 3. 受控模糊匹配：只有“唯一候选”时才命中，避免误绑
            fuzzy_seeds = []
            for name in deduped + [normalized_key]:
                cleaned = self._normalize_industry_join_key(name)
                if len(cleaned) >= 2:
                    fuzzy_seeds.append(cleaned)

            for seed in fuzzy_seeds:
                contains_matches = ths_catalog[
                    ths_catalog["industry_name"].str.contains(seed, na=False)
                    | ths_catalog["join_key"].str.contains(seed, na=False)
                ]
                contains_matches = contains_matches.drop_duplicates(subset=["industry_name"])
                if len(contains_matches) == 1:
                    return str(contains_matches.iloc[0]["industry_name"])

        return direct_mapped

    _normalize_industry_join_key = staticmethod(_parsing.normalize_industry_join_key)
    _append_data_source = staticmethod(_parsing.append_data_source)
    _ensure_data_quality_columns = staticmethod(_parsing.ensure_data_quality_columns)

    # Tushare frame-normalization leaf helpers are shared with IndustryAnalyzer
    # (./_tushare_normalize.py). Exposed under their historical method names via
    # staticmethod aliases so existing call sites are unchanged.
    _coerce_tushare_numeric = staticmethod(_tushare_normalize.coerce_numeric)
    _normalize_tushare_columns = staticmethod(_tushare_normalize.normalize_columns)
    _tushare_first_value = staticmethod(_tushare_normalize.first_value)
    _tushare_name_from_row = staticmethod(_tushare_normalize.name_from_row)
    _append_tushare_record_source = staticmethod(_tushare_normalize.append_source)

    @classmethod
    def _normalize_tushare_industry_snapshot(
        cls,
        moneyflow_df: Optional[pd.DataFrame],
        board_df: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        moneyflow = cls._normalize_tushare_columns(moneyflow_df)
        board = cls._normalize_tushare_columns(board_df)
        if moneyflow.empty and board.empty:
            return pd.DataFrame()

        records: Dict[str, Dict[str, Any]] = {}

        for _, row in moneyflow.iterrows():
            industry_name = cls._tushare_name_from_row(row)
            if not industry_name:
                continue
            record = records.setdefault(industry_name, {"industry_name": industry_name})

            change_pct = cls._coerce_tushare_numeric(
                cls._tushare_first_value(row, ["change_pct", "pct_change", "涨跌幅"])
            )
            if change_pct is not None:
                record["change_pct"] = change_pct

            net_amount = cls._coerce_tushare_numeric(
                cls._tushare_first_value(
                    row,
                    [
                        "main_net_inflow",
                        "net_amount",
                        "net_mf_amount",
                        "net_main_amount",
                        "主力净流入-净额",
                        "净额",
                    ],
                ),
                0.0,
            )
            if net_amount is not None and 0 < abs(net_amount) < 1e8:
                net_amount *= 10000
            record["main_net_inflow"] = net_amount or 0.0

            net_ratio = cls._coerce_tushare_numeric(
                cls._tushare_first_value(
                    row,
                    [
                        "main_net_ratio",
                        "net_amount_rate",
                        "net_mf_ratio",
                        "net_main_rate",
                        "主力净流入-净占比",
                    ],
                )
            )
            if net_ratio is not None:
                record["main_net_ratio"] = net_ratio
                record["flow_strength"] = max(min(net_ratio / 100.0, 1.0), -1.0)

            cls._append_tushare_record_source(record, "tushare_moneyflow_ind_ths")

        for _, row in board.iterrows():
            industry_name = cls._tushare_name_from_row(row)
            if not industry_name:
                continue
            record = records.setdefault(industry_name, {"industry_name": industry_name})

            board_change = cls._coerce_tushare_numeric(
                cls._tushare_first_value(row, ["change_pct", "pct_change", "涨跌幅"])
            )
            if board_change is not None:
                record["change_pct"] = board_change

            total_mv = cls._coerce_tushare_numeric(
                cls._tushare_first_value(row, ["total_market_cap", "total_mv", "总市值"])
            )
            if total_mv is not None and total_mv > 0:
                if total_mv < 1e10:
                    total_mv *= 10000
                record["total_market_cap"] = total_mv
                record["market_cap_source"] = "tushare_dc_board"

            turnover_rate = cls._coerce_tushare_numeric(
                cls._tushare_first_value(row, ["turnover_rate", "换手率"]),
                0.0,
            )
            record["turnover_rate"] = turnover_rate or 0.0

            up_num = (
                cls._coerce_tushare_numeric(
                    cls._tushare_first_value(row, ["up_num", "上涨家数"]),
                    0.0,
                )
                or 0.0
            )
            down_num = (
                cls._coerce_tushare_numeric(
                    cls._tushare_first_value(row, ["down_num", "下跌家数"]),
                    0.0,
                )
                or 0.0
            )
            if up_num or down_num:
                record["stock_count"] = int(up_num + down_num)

            leading = cls._tushare_first_value(row, ["leading_stock", "leading", "领涨股"])
            if leading:
                record["leading_stock"] = str(leading).strip()

            leading_code = cls._normalize_stock_symbol(
                cls._tushare_first_value(
                    row,
                    ["leading_stock_code", "leading_code", "领涨股代码"],
                )
            )
            if leading_code:
                record["leading_stock_code"] = leading_code

            leading_pct = cls._coerce_tushare_numeric(
                cls._tushare_first_value(
                    row,
                    ["leading_stock_change", "leading_pct", "领涨股涨跌幅"],
                )
            )
            if leading_pct is not None:
                record["leading_stock_change"] = leading_pct

            cls._append_tushare_record_source(record, "tushare_dc_index")

        if not records:
            return pd.DataFrame()

        result = pd.DataFrame(records.values())
        if "market_cap_source" not in result.columns:
            result["market_cap_source"] = "unknown"
        result["market_cap_source"] = result["market_cap_source"].fillna("unknown")
        return result

    def _candidate_tushare_trade_dates(self, provider) -> List[Any]:
        today = datetime.now()
        candidates: List[Any] = [today]
        calendar_loader = getattr(provider, "get_trade_calendar", None)
        if callable(calendar_loader):
            try:
                start = today - timedelta(days=10)
                open_days = calendar_loader(start_date=start, end_date=today, exchange="SSE")
                for day in reversed(open_days or []):
                    if day not in candidates:
                        candidates.append(day)
            except Exception as exc:
                logger.debug("Tushare trade calendar lookup failed for industry fallback: %s", exc)
        return candidates[:4]

    def _load_tushare_industry_snapshot(self, include_moneyflow: bool = True) -> pd.DataFrame:
        provider = getattr(self, "tushare", None)
        if provider is None:
            return pd.DataFrame()

        moneyflow_loader = getattr(provider, "get_industry_moneyflow", None)
        board_loader = getattr(provider, "get_dc_board_status", None)
        if not callable(moneyflow_loader) and not callable(board_loader):
            return pd.DataFrame()

        for trade_date in self._candidate_tushare_trade_dates(provider):
            moneyflow_df = pd.DataFrame()
            board_df = pd.DataFrame()

            if include_moneyflow and callable(moneyflow_loader):
                try:
                    moneyflow_df = moneyflow_loader(trade_date)
                except Exception as exc:
                    logger.debug(
                        "Tushare industry moneyflow failed for %s: %s",
                        trade_date,
                        exc,
                    )

            if callable(board_loader):
                try:
                    board_df = board_loader(trade_date, idx_type="行业板块")
                except Exception as exc:
                    logger.debug("Tushare dc_index failed for %s: %s", trade_date, exc)

            normalized = self._normalize_tushare_industry_snapshot(moneyflow_df, board_df)
            if not normalized.empty:
                logger.info(
                    "Loaded Tushare after-close industry snapshot for %s with %s rows",
                    trade_date,
                    len(normalized),
                )
                return normalized

        return pd.DataFrame()

    _is_blank = staticmethod(_parsing.is_blank)

    @classmethod
    def _is_missing_or_zero(cls, value: Any) -> bool:
        try:
            if value is None or pd.isna(value):
                return True
            return abs(float(value)) <= 1e-12
        except (TypeError, ValueError):
            return cls._is_blank(value)

    def _enrich_with_tushare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Use paid Tushare after-close data to fill missing industry fields."""
        if df is None or df.empty:
            return df

        snapshot = self._load_tushare_industry_snapshot(include_moneyflow=True)
        if snapshot.empty:
            return df

        result = df.copy()
        snapshot = snapshot.copy()
        snapshot["match_key"] = snapshot["industry_name"].apply(self._normalize_industry_join_key)
        snapshot = snapshot.drop_duplicates(subset=["match_key"], keep="first")
        enrichment_by_key = {
            str(row.get("match_key") or "").strip(): row for _, row in snapshot.iterrows()
        }

        for column, default in {
            "change_pct": 0.0,
            "main_net_inflow": 0.0,
            "main_net_ratio": 0.0,
            "flow_strength": 0.0,
            "total_market_cap": 0.0,
            "turnover_rate": 0.0,
            "stock_count": 0,
            "leading_stock": "",
            "leading_stock_code": "",
            "leading_stock_change": 0.0,
        }.items():
            if column not in result.columns:
                result[column] = default
        if "market_cap_source" not in result.columns:
            result["market_cap_source"] = "unknown"

        matched_indices: List[Any] = []
        for idx, row in result.iterrows():
            match_key = self._normalize_industry_join_key(row.get("industry_name", ""))
            enrichment = enrichment_by_key.get(match_key)
            if enrichment is None:
                continue

            changed = False

            def fill_numeric(column: str, min_value: float | None = None) -> None:
                nonlocal changed
                if column not in enrichment.index:
                    return
                value = self._coerce_tushare_numeric(enrichment.get(column))
                if value is None:
                    return
                if min_value is not None and value <= min_value:
                    return
                if self._is_missing_or_zero(result.at[idx, column]):
                    result.at[idx, column] = value
                    changed = True

            fill_numeric("change_pct")
            fill_numeric("main_net_inflow")
            fill_numeric("main_net_ratio")
            fill_numeric("flow_strength")
            fill_numeric("turnover_rate")
            fill_numeric("stock_count")
            fill_numeric("leading_stock_change")

            cap_value = self._coerce_tushare_numeric(enrichment.get("total_market_cap"), 0.0) or 0.0
            current_cap = self._coerce_tushare_numeric(result.at[idx, "total_market_cap"], 0.0) or 0.0
            current_source = str(result.at[idx, "market_cap_source"] or "unknown").strip()
            should_fill_cap = current_cap <= 1 or current_source in {
                "",
                "unknown",
                "estimated",
                "estimated_from_flow",
                "estimated_from_turnover",
                "constant_fallback",
            }
            if cap_value > 1 and should_fill_cap:
                result.at[idx, "total_market_cap"] = cap_value
                result.at[idx, "market_cap_source"] = str(
                    enrichment.get("market_cap_source") or "tushare_dc_board"
                )
                changed = True

            for column in ("leading_stock", "leading_stock_code"):
                if column in enrichment.index and self._is_blank(result.at[idx, column]):
                    value = str(enrichment.get(column) or "").strip()
                    if value:
                        result.at[idx, column] = value
                        changed = True

            if changed:
                matched_indices.append(idx)
                for source in enrichment.get("data_sources", []) or []:
                    self._append_data_source(
                        result,
                        pd.Series(result.index == idx, index=result.index),
                        str(source),
                    )

        if matched_indices:
            logger.info("Tushare enriched %s industry rows", len(matched_indices))
        return result

    @classmethod
    def _get_cached_sina_stock_nodes(cls) -> frozenset[str]:
        now = time.time()
        if (
            cls._sina_cached_stock_nodes is not None
            and now - cls._sina_cached_stock_nodes_time < 600
        ):
            return cls._sina_cached_stock_nodes

        codes = SinaFinanceProvider._get_persistent_industry_stock_codes()
        cls._sina_cached_stock_nodes = frozenset(codes)
        cls._sina_cached_stock_nodes_time = now
        return cls._sina_cached_stock_nodes

    def _candidate_matches_industry(self, candidate_name: str, industry_name: str) -> bool:
        raw_key = self._normalize_industry_join_key(industry_name)
        candidate_key = self._normalize_industry_join_key(candidate_name)
        if candidate_key == raw_key:
            return True

        mapped_back = map_sina_to_ths(candidate_name)
        mapped_key = self._normalize_industry_join_key(mapped_back)
        return mapped_key == raw_key

    def _get_sina_industry_list(self, allow_live: bool = True) -> pd.DataFrame:
        now = time.time()
        cached = self.__class__._sina_industry_list_shared_cache
        if (
            cached is not None
            and not cached.empty
            and now - self.__class__._sina_industry_list_shared_cache_time
            < self.__class__._sina_industry_list_ttl_seconds
        ):
            return cached.copy()

        persistent_df = SinaFinanceProvider._load_persistent_industry_list()
        if not persistent_df.empty:
            persistent_df = persistent_df.copy()
            self.__class__._sina_industry_list_shared_cache = persistent_df
            self.__class__._sina_industry_list_shared_cache_time = now
            return persistent_df.copy()

        if not allow_live or not hasattr(self.sina, "get_industry_list"):
            if cached is not None and not cached.empty:
                return cached.copy()
            return pd.DataFrame()

        with self.__class__._sina_industry_list_lock:
            now = time.time()
            cached = self.__class__._sina_industry_list_shared_cache
            if (
                cached is not None
                and not cached.empty
                and now - self.__class__._sina_industry_list_shared_cache_time
                < self.__class__._sina_industry_list_ttl_seconds
            ):
                return cached.copy()

            persistent_df = SinaFinanceProvider._load_persistent_industry_list()
            if not persistent_df.empty:
                persistent_df = persistent_df.copy()
                self.__class__._sina_industry_list_shared_cache = persistent_df
                self.__class__._sina_industry_list_shared_cache_time = now
                return persistent_df.copy()

            try:
                live_df = self._call_with_circuit(
                    "sina_industry_list",
                    self.sina.get_industry_list,
                )
                if live_df is not None and not live_df.empty:
                    live_df = live_df.copy()
                    self.__class__._sina_industry_list_shared_cache = live_df
                    self.__class__._sina_industry_list_shared_cache_time = now
                    return live_df.copy()
            except Exception as exc:
                logger.warning(f"Failed to load live Sina industry list: {exc}")

            if cached is not None and not cached.empty:
                return cached.copy()
            return pd.DataFrame()

    def _attach_industry_codes(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        if "industry_code" in df.columns:
            current_codes = df["industry_code"].astype(str).str.strip()
            if current_codes.ne("").all():
                return df

        result = df.copy()
        ths_catalog = self._get_ths_industry_catalog()
        if not ths_catalog.empty:
            code_map = {}
            for _, row in ths_catalog.iterrows():
                industry_name = str(row.get("industry_name", "")).strip()
                industry_code = str(row.get("industry_code", "")).strip()
                if not industry_name or not industry_code:
                    continue
                code_map[industry_name] = industry_code
                code_map[self._normalize_industry_join_key(industry_name)] = industry_code

            result["industry_code"] = result["industry_name"].apply(
                lambda name: (
                    code_map.get(str(name).strip())
                    or code_map.get(self._normalize_industry_join_key(str(name)))
                )
            )

        if (
            "industry_code" not in result.columns or result["industry_code"].isna().any()
        ) and hasattr(self.sina, "get_industry_list"):
            try:
                sina_df = self._get_sina_industry_list(allow_live=True)
                if not sina_df.empty:
                    sina_code_map = {}
                    for _, row in sina_df.iterrows():
                        industry_name = map_sina_to_ths(str(row.get("industry_name", "")).strip())
                        industry_code = str(row.get("industry_code", "")).strip()
                        if not industry_name or not industry_code:
                            continue
                        sina_code_map[industry_name] = industry_code
                        sina_code_map[self._normalize_industry_join_key(industry_name)] = (
                            industry_code
                        )
                    if "industry_code" not in result.columns:
                        result["industry_code"] = pd.NA
                    missing_mask = result["industry_code"].isna() | result["industry_code"].astype(
                        str
                    ).str.strip().eq("")
                    result.loc[missing_mask, "industry_code"] = result.loc[
                        missing_mask, "industry_name"
                    ].apply(
                        lambda name: (
                            sina_code_map.get(str(name).strip())
                            or sina_code_map.get(self._normalize_industry_join_key(str(name)))
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to attach Sina industry codes: {e}")

        return result

    def _resolve_sina_industry_node(
        self,
        industry_name: str,
        industry_code: str | None = None,
        allow_live: bool = True,
    ) -> tuple[str | None, str]:
        candidate_code = str(industry_code or "").strip()
        if candidate_code.startswith("new_"):
            return candidate_code, "sina_stock_sum"

        raw_name = str(industry_name or "").strip()
        cached_new_nodes = self._get_cached_sina_stock_nodes()
        possible_names = []
        if raw_name:
            possible_names.append(raw_name)
            mapped = map_sina_to_ths(raw_name)
            if mapped != raw_name:
                possible_names.append(mapped)
            possible_names.extend(map_ths_to_sina(raw_name))

        ordered_names = []
        seen = set()
        for name in possible_names:
            normalized = str(name or "").strip()
            if normalized and normalized not in seen:
                ordered_names.append(normalized)
                seen.add(normalized)

        fallback_code = None

        def _record_resolved_code(normalized: str, resolved_code: Any) -> str | None:
            nonlocal fallback_code
            resolved_code = str(resolved_code or "").strip()
            if not resolved_code:
                return None
            matches_raw_name = normalized == raw_name or (
                normalized in SINA_NEW_NODE_NAME_MAP
                and self._candidate_matches_industry(normalized, raw_name)
            )
            if resolved_code.startswith("new_") and matches_raw_name:
                return resolved_code
            if not fallback_code and matches_raw_name:
                fallback_code = resolved_code
            return None

        def _scan_lookup(rows_by_name: dict[str, list[dict[str, Any]]]) -> str | None:
            for normalized in ordered_names:
                for row in rows_by_name.get(normalized, []):
                    resolved = _record_resolved_code(normalized, row.get("industry_code"))
                    if resolved:
                        return resolved
            return None

        try:
            persistent_lookup = SinaFinanceProvider._get_persistent_industry_list_lookup()
            resolved_from_persistent = _scan_lookup(persistent_lookup)
            if resolved_from_persistent:
                return resolved_from_persistent, "sina_stock_sum"

            if allow_live and fallback_code is None and hasattr(self.sina, "get_industry_list"):
                live_industries = self._call_with_circuit(
                    "sina_industry_list",
                    self.sina.get_industry_list,
                )
                if live_industries is not None and not live_industries.empty:
                    self.__class__._sina_industry_list_shared_cache = live_industries.copy()
                    self.__class__._sina_industry_list_shared_cache_time = time.time()
                    live_lookup: dict[str, list[dict[str, Any]]] = {}
                    for row in live_industries.to_dict(orient="records"):
                        normalized = str(row.get("industry_name") or "").strip()
                        if not normalized:
                            continue
                        live_lookup.setdefault(normalized, []).append(row)
                    resolved_from_live = _scan_lookup(live_lookup)
                    if resolved_from_live:
                        return resolved_from_live, "sina_stock_sum"
        except Exception as e:
            logger.warning(f"Failed to resolve Sina industry code for {industry_name}: {e}")

        for normalized in ordered_names:
            alias_code = SINA_NEW_NODE_NAME_MAP.get(normalized)
            if not alias_code or alias_code not in cached_new_nodes:
                continue
            if self._candidate_matches_industry(normalized, raw_name):
                return alias_code, "sina_stock_sum"

        proxy_code = SINA_PROXY_NODE_NAME_MAP.get(raw_name)
        if proxy_code and proxy_code in cached_new_nodes:
            return proxy_code, "sina_proxy_stock_sum"

        return fallback_code, "unknown"

    def _resolve_sina_industry_code(
        self,
        industry_name: str,
        industry_code: str | None = None,
        allow_live: bool = True,
    ) -> str | None:
        resolved_code, _ = self._resolve_sina_industry_node(
            industry_name,
            industry_code,
            allow_live=allow_live,
        )
        return resolved_code

    _normalize_sina_stock_rows = staticmethod(_parsing.normalize_sina_stock_rows)

    def _get_candidate_industry_names(self, industry_name: str) -> tuple[str, ...]:
        raw_name = str(industry_name or "").strip()
        if not raw_name:
            return ()

        cached = self.__class__._candidate_industry_names_cache.get(raw_name)
        if cached is not None:
            return cached

        possible_names = [raw_name]
        mapped_name = map_sina_to_ths(raw_name)
        if mapped_name != raw_name:
            possible_names.append(mapped_name)
        possible_names.extend(map_ths_to_sina(raw_name))
        if mapped_name:
            possible_names.extend(map_ths_to_sina(mapped_name))

        ordered_names: List[str] = []
        seen_names = set()
        for name in possible_names:
            normalized = str(name or "").strip()
            if normalized and normalized not in seen_names:
                ordered_names.append(normalized)
                seen_names.add(normalized)

        result = tuple(ordered_names)
        self.__class__._candidate_industry_names_cache[raw_name] = result
        return result

    _normalize_stock_symbol = staticmethod(_parsing.normalize_stock_symbol)

    def _get_cached_sina_industry_codes(self, industry_name: str) -> List[str]:
        raw_name = str(industry_name or "").strip()
        if not raw_name:
            return []

        now = time.time()
        cache_entry = self.__class__._cached_sina_industry_codes_cache.get(raw_name)
        if (
            cache_entry
            and now - float(cache_entry.get("ts") or 0)
            < self.__class__._cached_sina_industry_codes_ttl_seconds
        ):
            return list(cache_entry.get("codes") or [])

        ordered_names = self._get_candidate_industry_names(raw_name)
        candidate_codes: List[str] = []
        cached_new_nodes = self._get_cached_sina_stock_nodes()
        for name in ordered_names:
            alias_code = SINA_NEW_NODE_NAME_MAP.get(name)
            if alias_code and alias_code in cached_new_nodes:
                candidate_codes.append(alias_code)

            proxy_code = SINA_PROXY_NODE_NAME_MAP.get(name)
            if proxy_code and proxy_code in cached_new_nodes:
                candidate_codes.append(proxy_code)

        persistent_lookup = SinaFinanceProvider._get_persistent_industry_list_lookup()
        if persistent_lookup:
            for name in ordered_names:
                matches = persistent_lookup.get(name) or []
                if not matches:
                    continue
                resolved_code = str(matches[0].get("industry_code") or "").strip()
                if resolved_code:
                    candidate_codes.append(resolved_code)

        deduped_codes: List[str] = []
        seen_codes = set()
        for code in candidate_codes:
            normalized = str(code or "").strip()
            if normalized and normalized not in seen_codes:
                deduped_codes.append(normalized)
                seen_codes.add(normalized)

        self.__class__._cached_sina_industry_codes_cache[raw_name] = {
            "ts": now,
            "codes": tuple(deduped_codes),
        }
        return deduped_codes

    def get_cached_stock_list_by_industry(self, industry_name: str) -> List[Dict[str, Any]]:
        """
        仅使用本地持久化快照快速返回行业成分股，不触发远端请求。
        """
        raw_name = str(industry_name or "").strip()
        if not raw_name:
            return []

        for industry_code in self._get_cached_sina_industry_codes(raw_name):
            cached_rows = self.sina._get_persistent_industry_stock_rows(industry_code)
            if not cached_rows:
                continue
            refined_rows = self._refine_proxy_constituents(raw_name, cached_rows, industry_code)
            normalized_rows = self._normalize_sina_stock_rows(refined_rows)
            if normalized_rows:
                persist_snapshot = getattr(self.akshare, "persist_stock_list_snapshot", None)
                if callable(persist_snapshot):
                    try:
                        persist_snapshot(
                            raw_name,
                            normalized_rows,
                            include_market_cap_lookup=False,
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Failed to persist unified stock snapshot for {raw_name}: {exc}"
                        )
                logger.debug(
                    "Using persistent Sina industry stocks snapshot for %s via %s (%s rows)",
                    raw_name,
                    industry_code,
                    len(normalized_rows),
                )
                return normalized_rows

        akshare_cached_loader = getattr(self.akshare, "get_cached_stock_list_by_industry", None)
        if callable(akshare_cached_loader):
            try:
                cached_rows = akshare_cached_loader(
                    raw_name,
                    include_market_cap_lookup=False,
                    allow_stale=True,
                )
                if cached_rows:
                    logger.debug(
                        "Using persistent AKShare industry stocks snapshot for %s (%s rows)",
                        raw_name,
                        len(cached_rows),
                    )
                    return cached_rows
            except TypeError:
                cached_rows = akshare_cached_loader(raw_name)
                if cached_rows:
                    return cached_rows
            except Exception as exc:
                logger.warning(
                    f"AKShare cached industry stocks fallback for {raw_name} failed: {exc}"
                )

        return []

    def _build_persistent_leading_stock_fallback(self, industry_name: str) -> List[Dict[str, Any]]:
        persistent_lookup = SinaFinanceProvider._get_persistent_industry_list_lookup()
        if not persistent_lookup:
            return []

        for name in self._get_candidate_industry_names(industry_name):
            matches = persistent_lookup.get(name) or []
            if not matches:
                continue

            row = matches[0]
            leader_name = str(row.get("leading_stock_name") or "").strip()
            leader_symbol = self._normalize_stock_symbol(row.get("leading_stock_code"))
            if not leader_name or not leader_symbol:
                continue

            try:
                change_pct = float(row.get("leading_stock_change", row.get("change_pct", 0)) or 0)
            except (TypeError, ValueError):
                change_pct = 0.0

            valuation_snapshot: Dict[str, Any] = {}
            try:
                candidate = self.get_stock_valuation(leader_symbol, cached_only=True)
                if isinstance(candidate, dict) and "error" not in candidate:
                    valuation_snapshot = candidate
            except Exception as exc:
                logger.warning(
                    "Failed to hydrate persistent leader fallback valuation for %s: %s",
                    leader_symbol,
                    exc,
                )

            logger.debug(
                "Using persistent Sina leader fallback for %s via %s (%s)",
                industry_name,
                name,
                leader_symbol,
            )
            return [
                {
                    "symbol": leader_symbol,
                    "code": leader_symbol,
                    "name": leader_name,
                    "change_pct": change_pct,
                    "market_cap": float(valuation_snapshot.get("market_cap") or 0),
                    "amount": float(valuation_snapshot.get("amount") or 0),
                    "pe_ratio": float(
                        valuation_snapshot.get("pe_ttm") or valuation_snapshot.get("pe_ratio") or 0
                    ),
                    "pb_ratio": float(
                        valuation_snapshot.get("pb") or valuation_snapshot.get("pb_ratio") or 0
                    ),
                }
            ]

        return []

    def _build_tushare_leading_stock_fallback(self, industry_name: str) -> List[Dict[str, Any]]:
        snapshot = self._load_tushare_industry_snapshot(include_moneyflow=False)
        if snapshot.empty:
            return []

        match_key = self._normalize_industry_join_key(industry_name)
        snapshot = snapshot.copy()
        snapshot["match_key"] = snapshot["industry_name"].apply(self._normalize_industry_join_key)
        matched = snapshot[snapshot["match_key"] == match_key]
        if matched.empty:
            return []

        row = matched.iloc[0]
        leader_name = str(row.get("leading_stock") or "").strip()
        leader_symbol = self._normalize_stock_symbol(row.get("leading_stock_code"))
        if not leader_name or not leader_symbol:
            return []

        try:
            change_pct = float(row.get("leading_stock_change") or row.get("change_pct") or 0)
        except (TypeError, ValueError):
            change_pct = 0.0

        valuation_snapshot: Dict[str, Any] = {}
        try:
            candidate = self.get_stock_valuation(leader_symbol, cached_only=True)
            if isinstance(candidate, dict) and "error" not in candidate:
                valuation_snapshot = candidate
        except Exception as exc:
            logger.warning(
                "Failed to hydrate Tushare leader fallback valuation for %s: %s",
                leader_symbol,
                exc,
            )

        logger.debug(
            "Using Tushare dc_index leader fallback for %s (%s)",
            industry_name,
            leader_symbol,
        )
        return [
            {
                "symbol": leader_symbol,
                "code": leader_symbol,
                "name": leader_name,
                "change_pct": change_pct,
                "market_cap": float(valuation_snapshot.get("market_cap") or 0),
                "amount": float(valuation_snapshot.get("amount") or 0),
                "pe_ratio": float(
                    valuation_snapshot.get("pe_ttm") or valuation_snapshot.get("pe_ratio") or 0
                ),
                "pb_ratio": float(
                    valuation_snapshot.get("pb") or valuation_snapshot.get("pb_ratio") or 0
                ),
                "source": "tushare_dc_index",
            }
        ]

    def get_symbol_by_name(self, name: str) -> str:
        """根据股票名称获取股票代码，如果找不到则返回原名称"""
        if not name:
            return name
        self.__class__._ensure_symbol_cache_loaded()

        current_time = time.time()
        # 缓存 12 小时 (43200 秒)
        if (
            current_time - self.__class__._stock_name_cache_time > 43200
            or not self.__class__._stock_name_to_symbol_cache
        ):
            with self.__class__._symbol_cache_lock:
                refreshed_time = self.__class__._stock_name_cache_time
                if (
                    current_time - refreshed_time > 43200
                    or not self.__class__._stock_name_to_symbol_cache
                ):
                    try:
                        logger.info("Updating stock name -> symbol global cache from AKShare")
                        df = self._call_with_circuit(
                            "stock_info_a_code_name",
                            ak.stock_info_a_code_name,
                        )
                        if not df.empty:
                            new_cache = {}
                            for _, row in df.iterrows():
                                code = str(row["code"])
                                row_name = str(row["name"])
                                for alias in self.__class__._build_name_aliases(row_name):
                                    new_cache[alias] = code

                            self.__class__._stock_name_to_symbol_cache.update(new_cache)
                            self.__class__._stock_name_cache_time = current_time
                            self.__class__._persist_symbol_cache()
                    except Exception as e:
                        logger.error(f"Failed to update stock name cache: {e}")
                        if self.__class__._stock_name_to_symbol_cache:
                            logger.warning("Using stale stock name -> symbol cache")

                        try:
                            industries = self._get_sina_industry_list(allow_live=True)
                            if not industries.empty and {
                                "leading_stock_name",
                                "leading_stock_code",
                            }.issubset(industries.columns):
                                pairs = list(
                                    zip(
                                        industries["leading_stock_name"].astype(str).tolist(),
                                        industries["leading_stock_code"].astype(str).tolist(),
                                    )
                                )
                                self.__class__._update_symbol_cache_from_pairs(pairs)
                        except Exception as fallback_error:
                            logger.warning(
                                f"Failed to build fallback symbol cache from Sina industries: {fallback_error}"
                            )

        for alias in self.__class__._build_name_aliases(name):
            symbol = self.__class__._stock_name_to_symbol_cache.get(alias)
            if symbol:
                return symbol

        return name

    def get_industry_classification(self) -> pd.DataFrame:
        """
        获取行业分类（THS 主；Sina 兜底）

        Returns:
            包含 industry_name 列的 DataFrame
        """
        ths_df = self._get_ths_industry_catalog()
        if not ths_df.empty:
            return ths_df[["industry_name", "industry_code"]].copy()

        df = self._get_sina_industry_list(allow_live=True)
        if df.empty:
            return pd.DataFrame()

        return pd.DataFrame(
            {
                "industry_name": df["industry_name"].apply(map_sina_to_ths),
                "industry_code": df["industry_code"],
            }
        ).drop_duplicates(subset=["industry_name"], keep="first")

    def _resolve_sw_industry_index_code(
        self,
        industry_code: str | None,
        industry_name: str | None = None,
    ) -> str:
        """
        把 THS/Sina 行业代码解析为 AKShare 申万行业指数代码。

        行业热度主链路里经常拿到 THS 的 `881xxx` 代码，但 AKShare 的
        `index_hist_sw` 只接受申万一级行业的 `801xxx`。这里优先用目录名
        做一次宽口径映射，减少可降级场景里的硬错误日志。
        """
        requested_code = str(industry_code or "").strip()
        if requested_code.startswith("801"):
            return requested_code

        resolved_name = str(industry_name or "").strip()
        if not resolved_name and requested_code:
            ths_catalog = self._get_ths_industry_catalog()
            if not ths_catalog.empty and {"industry_name", "industry_code"}.issubset(
                ths_catalog.columns
            ):
                matched = ths_catalog[
                    ths_catalog["industry_code"].astype(str).str.strip() == requested_code
                ]
                if not matched.empty:
                    resolved_name = str(matched.iloc[0].get("industry_name") or "").strip()

        if not resolved_name:
            return ""

        sw_name_map = getattr(self.akshare, "SW_INDUSTRY_MAP", None)
        if not isinstance(sw_name_map, dict) or not sw_name_map:
            sw_name_map = AKShareProvider.SW_INDUSTRY_MAP
        sw_name_map = {
            str(name).strip(): str(code).strip()
            for name, code in sw_name_map.items()
            if str(name or "").strip() and str(code or "").strip()
        }
        sw_key_map = {
            self._normalize_industry_join_key(name): code for name, code in sw_name_map.items()
        }

        candidate_names: List[str] = []
        seen: set[str] = set()

        def add_candidate(name: str | None) -> None:
            normalized = str(name or "").strip()
            if not normalized:
                return
            alias = SW_INDEX_ALIAS_MAP.get(normalized) or SW_INDEX_ALIAS_MAP.get(
                self._normalize_industry_join_key(normalized)
            )
            for candidate in (normalized, alias):
                clean_candidate = str(candidate or "").strip()
                if clean_candidate and clean_candidate not in seen:
                    candidate_names.append(clean_candidate)
                    seen.add(clean_candidate)

        add_candidate(resolved_name)
        add_candidate(map_sina_to_ths(resolved_name))
        add_candidate(INDUSTRY_ENRICHMENT_ALIASES.get(resolved_name))
        add_candidate(self._normalize_industry_join_key(resolved_name))

        for candidate_name in candidate_names:
            if candidate_name in sw_name_map:
                return sw_name_map[candidate_name]

            candidate_key = self._normalize_industry_join_key(candidate_name)
            if candidate_key in sw_key_map:
                return sw_key_map[candidate_key]

            fuzzy_matches = {
                code
                for sw_name, code in sw_name_map.items()
                if candidate_key
                and len(candidate_key) >= 2
                and candidate_key in self._normalize_industry_join_key(sw_name)
            }
            if len(fuzzy_matches) == 1:
                return next(iter(fuzzy_matches))

        return ""

    _dedupe_table_headers = staticmethod(_parsing.dedupe_table_headers)
    _parse_ths_flow_html = staticmethod(_parsing.parse_ths_flow_html)

    def _get_ths_flow_data(self, days: int) -> pd.DataFrame:
        """获取同花顺真实行业资金流向和涨跌幅 (不受代理拦截)"""
        try:
            headers_base = {
                "Host": "data.10jqka.com.cn",
                "Referer": "http://data.10jqka.com.cn/funds/hyzjl/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36",
                "Accept": "text/html, */*; q=0.01",
            }

            if days <= 1:
                base_url = "http://data.10jqka.com.cn/funds/hyzjl/field/tradezdf/order/desc/page/{}/ajax/1/free/1/"
            else:
                supported = [3, 5, 10, 20]
                actual_days = min(supported, key=lambda x: abs(x - days))
                base_url = f"http://data.10jqka.com.cn/funds/hyzjl/board/{actual_days}/field/tradezdf/order/desc/page/{{}}/ajax/1/free/1/"

            request_headers, used_cached_headers = self.__class__._build_ths_request_headers(
                headers_base
            )

            def _fetch_page(page: int, headers: Dict[str, str]) -> pd.DataFrame:
                response = self._call_with_circuit(
                    "ths_flow_http",
                    requests.get,
                    base_url.format(page),
                    headers=headers,
                    timeout=15,
                )
                if response.status_code == 200 and response.text.strip():
                    parsed_df, _ = self.__class__._parse_ths_flow_html(response.text)
                    return parsed_df
                return pd.DataFrame()

            r = self._call_with_circuit(
                "ths_flow_http",
                requests.get,
                base_url.format(1),
                headers=request_headers,
                timeout=15,
            )
            if used_cached_headers and (r.status_code != 200 or not r.text.strip()):
                request_headers, _ = self.__class__._build_ths_request_headers(
                    headers_base,
                    force_refresh=True,
                )
                r = self._call_with_circuit(
                    "ths_flow_http",
                    requests.get,
                    base_url.format(1),
                    headers=request_headers,
                    timeout=15,
                )

            big_df = pd.DataFrame()
            page_num = 1
            if r.status_code == 200 and r.text.strip():
                big_df, page_num = self.__class__._parse_ths_flow_html(r.text)

            if page_num > 1:
                ordered_frames = {}
                with ThreadPoolExecutor(max_workers=min(4, page_num - 1)) as executor:
                    future_map = {
                        executor.submit(_fetch_page, page, request_headers): page
                        for page in range(2, page_num + 1)
                    }
                    for future, page in ((future, future_map[future]) for future in future_map):
                        temp_df = future.result()
                        if not temp_df.empty:
                            ordered_frames[page] = temp_df

                for page in sorted(ordered_frames):
                    big_df = pd.concat([big_df, ordered_frames[page]], ignore_index=True)

            if not big_df.empty and "行业" in big_df.columns:
                big_df["industry_name"] = big_df["行业"].str.replace("Ⅲ", "").str.replace("Ⅱ", "")

            return big_df
        except Exception as e:
            logger.error(f"Failed to fetch THS flow data: {e}")
            return pd.DataFrame()

    def get_industry_money_flow(self, days: int = 5, lightweight: bool = False) -> pd.DataFrame:
        """
        获取行业资金流向（五源架构：THS主 + AKShare辅 + Tushare盘后 + Sina底 + Tencent估值）
        """
        # ========== 第一步：获取 THS 核心数据 ==========
        ths_df = self._get_ths_flow_data(days)

        if not ths_df.empty:
            result = self._process_ths_raw_data(ths_df)
            result = self._ensure_data_quality_columns(result, "ths")
            if lightweight:
                return result

            # ========== 第二步：AKShare 增强（市值、换手率、估值） ==========
            try:
                result = self._enrich_with_akshare(
                    result,
                    prefer_cached_valuation_snapshot=True,
                )
                self._persist_market_cap_snapshot(result)
            except Exception as e:
                logger.warning(f"Failed to enrich with AKShare metadata: {e}")

            # ========== 第三步：Tushare 盘后增强（资金流、板块状态、市值、领涨股） ==========
            try:
                result = self._enrich_with_tushare(result)
                self._persist_market_cap_snapshot(result)
            except Exception as e:
                logger.warning(f"Failed to enrich with Tushare after-close data: {e}")

            # ========== 第四步：Sina & 启发式辅助（市值兜底） ==========
            total_market_caps = self._numeric_series_or_default(result, "total_market_cap", 0.0)
            if "total_market_cap" not in result.columns or total_market_caps.max() <= 1:
                self._apply_persistent_market_cap_snapshot(result)
                logger.info("Falling back to Sina/Heuristics for market cap...")
                sina_df = self._call_with_circuit(
                    "sina_industry_money_flow",
                    self.sina.get_industry_money_flow,
                )
                total_market_caps = self._numeric_series_or_default(result, "total_market_cap", 0.0)
                if total_market_caps.max() > 1:
                    pass
                elif not sina_df.empty:
                    self._compute_industry_market_caps(result)
                    self._persist_market_cap_snapshot(result)
                    # 检查是否成功由于没有抛错机制
                    total_market_caps = self._numeric_series_or_default(
                        result, "total_market_cap", 0.0
                    )
                    if "total_market_cap" not in result.columns or total_market_caps.max() <= 1:
                        result["total_market_cap"] = self._estimate_market_cap_from_flow(result)
                        result["is_estimated_cap"] = True
                        result["market_cap_source"] = "estimated_from_flow"
                else:
                    result["total_market_cap"] = self._estimate_market_cap_from_flow(result)
                    result["is_estimated_cap"] = True
                    result["market_cap_source"] = "estimated_from_flow"

        else:
            # ========== 兜底层：Sina 模式 ==========
            logger.warning("THS data unavailable, falling back to Sina-only")
            sina_df = self._call_with_circuit(
                "sina_industry_money_flow",
                self.sina.get_industry_money_flow,
            )
            if sina_df.empty:
                logger.error("Both THS and Sina data unavailable")
                return pd.DataFrame()

            result = sina_df.copy()
            result = self._attach_industry_codes(result)
            result = self._ensure_data_quality_columns(result, "sina")
            if lightweight:
                return result
            if "main_net_inflow" not in result.columns:
                if "turnover" in result.columns and "change_pct" in result.columns:
                    result["main_net_inflow"] = (
                        result["turnover"].fillna(0) * (result["change_pct"].fillna(0) / 100) * 0.2
                    )
                else:
                    result["main_net_inflow"] = 0.0

            try:
                self._compute_industry_market_caps(result)
                self._persist_market_cap_snapshot(result)
            except Exception as exc:
                logger.warning(
                    "Industry market-cap computation failed; falling back to estimated caps: %s",
                    exc,
                    exc_info=True,
                )
                if "total_market_cap" not in result.columns:
                    if "turnover" in result.columns:
                        result["total_market_cap"] = result["turnover"].abs() * 100
                        result["is_estimated_cap"] = True
                        result["market_cap_source"] = "estimated_from_turnover"
                    else:
                        result["total_market_cap"] = 1.0
                        result["is_estimated_cap"] = True
                        result["market_cap_source"] = "constant_fallback"

            # 保证即便在 Sina 模式下，也拥有 pe_ttm, pb 字段
            if "pe_ttm" not in result.columns:
                result["pe_ttm"] = None
            if "pb" not in result.columns:
                result["pb"] = None

            # Sina 模式下也用 AKShare 增强市值、换手率、估值，实现数据最大化
            try:
                result = self._enrich_with_akshare(
                    result,
                    prefer_cached_valuation_snapshot=True,
                )
                self._persist_market_cap_snapshot(result)
            except Exception as e:
                logger.warning(f"AKShare enrichment in Sina-only mode failed: {e}")

            try:
                result = self._enrich_with_tushare(result)
                self._persist_market_cap_snapshot(result)
            except Exception as e:
                logger.warning(f"Tushare enrichment in Sina-only mode failed: {e}")

            self._apply_persistent_market_cap_snapshot(result)

        # ========== 第五步：兜底默认值填补 ==========
        defaults = {
            "change_pct": 0.0,
            "flow_strength": 0.0,
            "turnover_rate": 0.0,
            "main_net_ratio": 0.0,
            "total_market_cap": 1.0,
            "industry_index": 0.0,
            "total_inflow": 0.0,
            "total_outflow": 0.0,
            "leading_stock_change": 0.0,
            "leading_stock_price": 0.0,
            "stock_count": 0,
        }
        for col, val in defaults.items():
            if col not in result.columns:
                result[col] = val

        self._ensure_flow_strength(result)

        # ========== 第六步：换手率兜底（AKShare 被拦截时用成交额/市值估算） ==========
        turnover_rate = self._numeric_series_or_default(result, "turnover_rate", 0.0)
        mask = (turnover_rate.isna()) | (turnover_rate <= 0)
        if mask.any():
            is_estimated = result.get("is_estimated_cap", pd.Series(False, index=result.index))
            valid_for_turnover = mask & (~is_estimated)

            if valid_for_turnover.any():
                inflow = self._numeric_series_or_default(result, "total_inflow", 0.0)
                outflow = self._numeric_series_or_default(result, "total_outflow", 0.0)
                cap = self._numeric_series_or_default(result, "total_market_cap", 0.0)
                # 流入+流出≈总成交额(亿元)，市值(元)；换手率=(成交额/市值)*100
                vol_yi = inflow + outflow

                valid1 = valid_for_turnover & (cap > 1e7) & (vol_yi > 0)
                if valid1.any():
                    result.loc[valid1, "turnover_rate"] = (
                        vol_yi.loc[valid1] * 1e8 / cap.loc[valid1] * 100
                    ).clip(upper=999)

                # Sina 模式：用 turnover(成交额, 元) 估算
                if "turnover" in result.columns:
                    t = pd.to_numeric(result["turnover"], errors="coerce").fillna(0)
                    fallback = valid_for_turnover & (~valid1) & (cap > 1e7) & (t > 0)
                    if fallback.any():
                        result.loc[fallback, "turnover_rate"] = (
                            t.loc[fallback] / cap.loc[fallback] * 100
                        ).clip(upper=999)

        if "market_cap_source" not in result.columns:
            result["market_cap_source"] = "unknown"
        missing_cap_source = (
            result["market_cap_source"].astype(str).str.strip().eq("")
            | result["market_cap_source"].isna()
        )
        estimated_cap = result.get("is_estimated_cap", pd.Series(False, index=result.index))
        if not isinstance(estimated_cap, pd.Series):
            estimated_cap = pd.Series(bool(estimated_cap), index=result.index)
        estimated_cap = estimated_cap.fillna(False).astype(bool)
        result.loc[missing_cap_source & estimated_cap, "market_cap_source"] = "estimated"
        result.loc[missing_cap_source & ~estimated_cap, "market_cap_source"] = "unknown"

        if "valuation_source" not in result.columns:
            result["valuation_source"] = "unavailable"
        if "valuation_quality" not in result.columns:
            result["valuation_quality"] = "unavailable"

        return result

    def _ensure_flow_strength(self, df: pd.DataFrame) -> None:
        """
        保证行业资金流结果里存在可用的 flow_strength。

        THS 主链有时只返回净流入金额，没有稳定返回资金强度；如果这里不补齐，
        前端聚类分布图会退化成一条水平线。
        """
        if df.empty:
            return

        inflow = self._numeric_series_or_default(df, "main_net_inflow", 0.0)
        if "flow_strength" in df.columns:
            flow_strength = pd.to_numeric(df["flow_strength"], errors="coerce").fillna(0)
        else:
            flow_strength = pd.Series(0.0, index=df.index, dtype=float)

        has_existing_signal = (flow_strength.abs() > 1e-9).any()
        has_inflow_signal = (inflow.abs() > 1e-9).any()
        if has_existing_signal or not has_inflow_signal:
            df["flow_strength"] = flow_strength.astype(float)
            return

        main_net_ratio = self._numeric_series_or_default(df, "main_net_ratio", 0.0)
        if (main_net_ratio.abs() > 1e-9).any():
            df["flow_strength"] = (main_net_ratio / 100.0).clip(-1.0, 1.0)
            return

        max_abs_inflow = float(inflow.abs().max())
        if max_abs_inflow > 0:
            df["flow_strength"] = (inflow / max_abs_inflow).clip(-1.0, 1.0)
        else:
            df["flow_strength"] = 0.0

    def _process_ths_raw_data(self, ths_df: pd.DataFrame) -> pd.DataFrame:
        """解析 THS 原始数据框并提取规范字段"""
        ths_df = ths_df.drop_duplicates(subset=["industry_name"], keep="first").reset_index(
            drop=True
        )

        net_cols = [c for c in ths_df.columns if "净额" in c]
        chg_cols = [
            c
            for c in ths_df.columns
            if ("涨跌幅" in c or "阶段涨跌幅" in c) and not c.endswith(".1")
        ]
        inflow_cols = [c for c in ths_df.columns if "流入" in c and "净" not in c]
        outflow_cols = [c for c in ths_df.columns if "流出" in c]
        index_cols = [c for c in ths_df.columns if "行业指数" in c or "指数" in c]
        leading_chg_cols = [c for c in ths_df.columns if c == "涨跌幅.1"]
        price_cols = [c for c in ths_df.columns if "当前价" in c]
        count_cols = [c for c in ths_df.columns if "公司家数" in c]
        leading_name_cols = [c for c in ths_df.columns if c == "领涨股"]

        result = pd.DataFrame()
        result["industry_name"] = ths_df["industry_name"]

        if chg_cols:
            result["change_pct"] = (
                pd.to_numeric(ths_df[chg_cols[0]].astype(str).str.replace("%", ""), errors="coerce")
                .fillna(0)
                .values
            )
        if net_cols:
            result["main_net_inflow"] = (
                pd.to_numeric(ths_df[net_cols[0]], errors="coerce").fillna(0).values * 1e8
            )
        if inflow_cols:
            result["total_inflow"] = (
                pd.to_numeric(ths_df[inflow_cols[0]], errors="coerce").fillna(0).values
            )
        if outflow_cols:
            result["total_outflow"] = (
                pd.to_numeric(ths_df[outflow_cols[0]], errors="coerce").fillna(0).values
            )
        if index_cols:
            result["industry_index"] = (
                pd.to_numeric(ths_df[index_cols[0]], errors="coerce").fillna(0).values
            )
        if count_cols:
            result["stock_count"] = (
                pd.to_numeric(ths_df[count_cols[0]], errors="coerce").fillna(0).astype(int).values
            )
        if leading_name_cols:
            result["leading_stock"] = (
                ths_df[leading_name_cols[0]]
                .apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else None)
                .values
            )
        if leading_chg_cols:
            result["leading_stock_change"] = (
                pd.to_numeric(
                    ths_df[leading_chg_cols[0]].astype(str).str.replace("%", ""), errors="coerce"
                )
                .fillna(0)
                .values
            )
        if price_cols:
            result["leading_stock_price"] = (
                pd.to_numeric(ths_df[price_cols[0]], errors="coerce").fillna(0).values
            )

        if net_cols and inflow_cols and outflow_cols:
            net_amt = pd.to_numeric(ths_df[net_cols[0]], errors="coerce").fillna(0)
            inflow_amt = result.get("total_inflow", 0)
            outflow_amt = result.get("total_outflow", 0)
            total_amt = inflow_amt + outflow_amt
            result["main_net_ratio"] = pd.Series(
                [n / t * 100 if t > 0 else 0.0 for n, t in zip(net_amt.values, total_amt.values)]
            )

        return self._attach_industry_codes(result)

    @classmethod
    def _refresh_akshare_valuation_snapshot_blocking(cls) -> pd.DataFrame:
        now = time.time()
        if (
            cls._akshare_valuation_snapshot_failure_at
            and now - cls._akshare_valuation_snapshot_failure_at
            < cls._akshare_valuation_snapshot_cooldown_seconds
        ):
            logger.info("Skipping AKShare industry valuation snapshot refresh during cooldown")
            return (
                cls._akshare_valuation_snapshot_cache.copy()
                if cls._akshare_valuation_snapshot_cache is not None
                else pd.DataFrame()
            )

        try:
            valuation_df = cls._call_with_circuit(
                "sw_index_first_info",
                ak.sw_index_first_info,
            )
            if valuation_df is None or valuation_df.empty:
                cls._akshare_valuation_snapshot_failure_at = now
                return (
                    cls._akshare_valuation_snapshot_cache.copy()
                    if cls._akshare_valuation_snapshot_cache is not None
                    else pd.DataFrame()
                )
            cls._akshare_valuation_snapshot_cache = valuation_df.copy()
            cls._akshare_valuation_snapshot_cache_time = now
            cls._akshare_valuation_snapshot_failure_at = 0
            return cls._akshare_valuation_snapshot_cache
        except Exception as exc:
            cls._akshare_valuation_snapshot_failure_at = now
            logger.warning(f"Valuation snapshot refresh failed: {exc}")
            return (
                cls._akshare_valuation_snapshot_cache.copy()
                if cls._akshare_valuation_snapshot_cache is not None
                else pd.DataFrame()
            )

    @classmethod
    def _schedule_akshare_valuation_snapshot_refresh(cls) -> Optional[Future]:
        with cls._akshare_valuation_snapshot_refresh_lock:
            future = cls._akshare_valuation_snapshot_refresh_future
            if future is not None and not future.done():
                return future

            future = cls._akshare_valuation_snapshot_refresh_executor.submit(
                cls._refresh_akshare_valuation_snapshot_blocking
            )
            cls._akshare_valuation_snapshot_refresh_future = future

            def _cleanup(done_future: Future) -> None:
                with cls._akshare_valuation_snapshot_refresh_lock:
                    if cls._akshare_valuation_snapshot_refresh_future is done_future:
                        cls._akshare_valuation_snapshot_refresh_future = None

            future.add_done_callback(_cleanup)
            return future

    @classmethod
    def _get_akshare_valuation_snapshot(
        cls,
        cached_only: bool = False,
        schedule_refresh: bool = False,
    ) -> pd.DataFrame:
        now = time.time()
        if (
            cls._akshare_valuation_snapshot_cache is not None
            and now - cls._akshare_valuation_snapshot_cache_time
            < cls._akshare_valuation_snapshot_ttl_seconds
        ):
            return cls._akshare_valuation_snapshot_cache

        if cached_only:
            if schedule_refresh:
                cls._schedule_akshare_valuation_snapshot_refresh()
            return (
                cls._akshare_valuation_snapshot_cache.copy()
                if cls._akshare_valuation_snapshot_cache is not None
                else pd.DataFrame()
            )

        return cls._refresh_akshare_valuation_snapshot_blocking()

    def _enrich_with_akshare(
        self,
        df: pd.DataFrame,
        include_leader_valuation_fallback: bool = False,
        prefer_cached_valuation_snapshot: bool = False,
    ) -> pd.DataFrame:
        """使用 AKShare 数据增强总市值、换手率和估值指标"""
        df["match_key"] = df["industry_name"].apply(self._normalize_industry_join_key)

        # 1. 补充行业源数据（总市值、换手率）
        try:
            ak_provider = self.akshare
            meta_df = ak_provider._get_industry_metadata()
            if not meta_df.empty:
                meta_df = meta_df.copy()
                meta_df["match_key"] = meta_df["industry_name"].apply(
                    self._normalize_industry_join_key
                )
                meta_df = meta_df.drop_duplicates(subset=["match_key"], keep="first")

                meta_merge_df = meta_df[
                    ["match_key", "total_market_cap", "turnover_rate", "market_cap_source"]
                ].rename(columns={"market_cap_source": "metadata_market_cap_source"})
                df = pd.merge(df, meta_merge_df, on="match_key", how="left")

                # 清洗非数字值
                df["total_market_cap"] = pd.to_numeric(df["total_market_cap"], errors="coerce")
                df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce")
                matched_cap = df["total_market_cap"].notna() & (df["total_market_cap"] > 0)
                if matched_cap.any():
                    source_series = (
                        df.loc[matched_cap, "metadata_market_cap_source"]
                        .astype(str)
                        .replace({"": "akshare_metadata", "nan": "akshare_metadata"})
                    )
                    df.loc[matched_cap, "market_cap_source"] = source_series.where(
                        source_series.ne("unknown"), "akshare_metadata"
                    )
                    self._append_data_source(df, matched_cap, "akshare")
                df = df.drop(columns=["metadata_market_cap_source"], errors="ignore")
        except Exception as e:
            logger.warning(f"Metadata Enrichment failed: {e}")

        # 2. 补充申万行业估值指标 (PE/PB等)
        try:
            ak_sw = self._get_akshare_valuation_snapshot(
                cached_only=prefer_cached_valuation_snapshot,
                schedule_refresh=prefer_cached_valuation_snapshot,
            )
            if not ak_sw.empty:
                ak_sw = ak_sw.copy()
                ak_sw = ak_sw.rename(
                    columns={
                        "行业名称": "ak_name",
                        "TTM(滚动)市盈率": "pe_ttm",
                        "市净率": "pb",
                        "静态股息率": "dividend_yield",
                    }
                )
                ak_sw["match_key"] = ak_sw["ak_name"].apply(self._normalize_industry_join_key)
                ak_sw = ak_sw.drop_duplicates(subset=["match_key"], keep="first")

                df = pd.merge(
                    df,
                    ak_sw[["match_key", "pe_ttm", "pb", "dividend_yield"]],
                    on="match_key",
                    how="left",
                )
                matched_valuation = (
                    df["pe_ttm"].notna() | df["pb"].notna() | df["dividend_yield"].notna()
                )
                if matched_valuation.any():
                    df.loc[matched_valuation, "valuation_source"] = "akshare_sw"
                    df.loc[matched_valuation, "valuation_quality"] = "industry_level"
                    self._append_data_source(df, matched_valuation, "akshare")
        except Exception as e:
            logger.warning(f"Valuation Enrichment failed: {e}")

        # 3. 腾讯极速行情兜底：如果 AKShare 挂了或返回 0.0（无效值）导致 pe_ttm 缺失，直接拿该行业领涨股的估值作为代表
        has_no_pe = "pe_ttm" not in df.columns or df["pe_ttm"].isna().all()
        has_zero_pe = not has_no_pe and (df["pe_ttm"] == 0).all()

        if include_leader_valuation_fallback and (has_no_pe or has_zero_pe):
            logger.info(
                f"Using Tencent fallback (reason: {'missing' if has_no_pe else 'zero'}) to fetch representative PE/PB from leading stocks..."
            )
            import requests

            pe_list, pb_list = [], []
            for _, row in df.iterrows():
                pe_val, pb_val = None, None
                leader = str(row.get("leading_stock", ""))
                sym = self.get_symbol_by_name(leader)
                if sym and sym.isdigit():
                    prefix = (
                        "sh"
                        if sym.startswith("6")
                        else "sz"
                        if sym.startswith(("0", "3"))
                        else "bj"
                    )
                    url = f"http://qt.gtimg.cn/q={prefix}{sym}"
                    try:
                        r = self._call_with_circuit(
                            "em_stock_detail_http",
                            requests.get,
                            url,
                            timeout=3,
                        )
                        if r.status_code == 200 and "v_" in r.text:
                            parts = r.text.split('"')[1].split("~")
                            if len(parts) > 46:
                                # 39: PE(TTM), 46: PB
                                pe_str, pb_str = parts[39], parts[46]
                                if pe_str and pe_str != "0.00":
                                    pe_val = float(pe_str)
                                if pb_str and pb_str != "0.00":
                                    pb_val = float(pb_str)
                    except Exception as exc:
                        logger.debug("Tencent PE/PB probe failed for %s: %s", sym, exc)
                pe_list.append(pe_val)
                pb_list.append(pb_val)

            # 如果之前有空列，或者未创建，则覆盖
            df["pe_ttm"] = pe_list
            df["pb"] = pb_list
            # 股息率腾讯不直接带在基础报价中，留空
            tencent_mask = pd.Series(
                [(pe is not None or pb is not None) for pe, pb in zip(pe_list, pb_list)],
                index=df.index,
            )
            if tencent_mask.any():
                df.loc[tencent_mask, "valuation_source"] = "tencent_leader_proxy"
                df.loc[tencent_mask, "valuation_quality"] = "leader_proxy"
                self._append_data_source(df, tencent_mask, "tencent")

        return df.drop(columns=["match_key"], errors="ignore")

    def _compute_industry_market_caps(self, df: pd.DataFrame):
        """
        通过并行获取各行业成分股，汇总计算行业总市值

        Uses a cache to avoid repeated API calls within a short period.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        # 检查缓存
        cache_key = "_industry_mktcap_cache"
        now = time.time()
        if hasattr(self, cache_key):
            cached_data, cached_time = getattr(self, cache_key)
            if now - cached_time < 600:  # 10 分钟缓存
                # 应用缓存的市值数据
                df["total_market_cap"] = df["industry_code"].map(lambda c: cached_data.get(c, 0))
                df["total_market_cap"] = df["total_market_cap"].fillna(0)
                return

        if "industry_code" not in df.columns or df["industry_code"].isna().all():
            updated = self._attach_industry_codes(df)
            if "industry_code" in updated.columns:
                df["industry_code"] = updated["industry_code"]
        if "industry_code" not in df.columns or df["industry_code"].isna().all():
            logger.warning("No industry_code column, cannot compute market caps")
            return

        industry_codes = df["industry_code"].tolist()
        industry_names = (
            df["industry_name"].tolist() if "industry_name" in df.columns else industry_codes
        )

        mktcap_map = {}

        def fetch_industry_mktcap(code, name):
            """获取单个行业的总市值"""
            try:
                resolved_code, resolved_source = self._resolve_sina_industry_node(name, code)
                if resolved_code:
                    stocks = self._call_with_circuit(
                        "sina_industry_stocks",
                        self.sina.get_industry_stocks,
                        resolved_code,
                        page=1,
                        count=50,
                        fetch_all=True,
                    )
                    total_cap = sum(s.get("mktcap", 0) for s in stocks) * 10000  # 万元->元
                    if total_cap > 0:
                        return code, total_cap, resolved_source

                return code, 0, "unknown"
            except Exception as e:
                logger.debug(f"Failed to get stocks for {name}: {e}")
                return code, 0, "unknown"

        # 并行获取（最多 5 个并发，避免过快请求）
        logger.info(
            f"Computing market caps for {len(industry_codes)} industries via Sina stocks..."
        )
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(fetch_industry_mktcap, code, name): code
                for code, name in zip(industry_codes, industry_names)
            }
            for future in as_completed(futures):
                code, cap, source = future.result()
                mktcap_map[code] = cap
                if source and source != "unknown":
                    if "market_cap_source" not in df.columns:
                        df["market_cap_source"] = "unknown"
                    df.loc[df["industry_code"] == code, "market_cap_source"] = source
                    if source in {"sina_stock_sum", "sina_proxy_stock_sum"}:
                        self._append_data_source(df, df["industry_code"] == code, "sina")

        # 应用市值数据
        df["total_market_cap"] = df["industry_code"].map(mktcap_map).fillna(0)

        nonzero = (df["total_market_cap"] > 0).sum()
        logger.info(f"Industry market caps computed: {nonzero}/{len(df)} have data")

        # 更新缓存
        setattr(self, cache_key, (mktcap_map, now))

    def _estimate_market_cap_from_flow(self, df: pd.DataFrame) -> pd.Series:
        """
        当真实市值数据不可用时，用 THS 成交总额估算行业相对规模。

        估算优先级:
        1. total_inflow + total_outflow（THS 成交总额，亿元）× 1e8 → 元
        2. stock_count × 100亿（行业成分股数 × 平均市值粗估）
        3. 全部回退为 1.0（避免方块等大）
        """
        if "total_inflow" in df.columns and "total_outflow" in df.columns:
            total_volume = df["total_inflow"].fillna(0) + df["total_outflow"].fillna(0)
            if total_volume.sum() > 0:
                logger.info("Estimating market cap from THS trading volume (total_inflow+outflow)")
                # 成交总额（亿元）× 1e8 = 元，再 × 10 作为换手率≈10%的粗略估算
                estimated = total_volume * 1e8 * 10
                # 若个别行业成交为0，用全体中位数填充
                median_val = estimated[estimated > 0].median()
                if pd.notna(median_val) and median_val > 0:
                    estimated = estimated.where(estimated > 0, median_val * 0.5)
                return estimated

        if "stock_count" in df.columns:
            counts = df["stock_count"].fillna(0).astype(float)
            if counts.sum() > 0:
                logger.info("Estimating market cap from stock_count")
                # 每家公司平均约100亿市值，粗略估算
                return counts * 100 * 1e8

        logger.warning("Cannot estimate market cap, using constant 1.0")
        return pd.Series([1.0] * len(df), index=df.index)

    def get_stock_list_by_industry(
        self, industry_name: str, fast_mode: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取行业成分股列表（融合模式：取 AKShare 与 Sina 并集，解决降级时数据过少问题）
        """
        ths_industry_name = self._normalize_to_ths_industry_name(industry_name)
        merged_stocks = {}  # symbol -> data

        def merge_akshare_rows():
            try:
                try:
                    ak_stocks = self.akshare.get_stock_list_by_industry(
                        ths_industry_name,
                        include_market_cap_lookup=not fast_mode,
                        soft_fail=True,
                    )
                except TypeError:
                    ak_stocks = self.akshare.get_stock_list_by_industry(ths_industry_name)
                if ak_stocks:
                    for stock in ak_stocks:
                        merged_stocks[stock["symbol"]] = stock
            except Exception as e:
                logger.warning(
                    f"AKShare get_stock_list failed for industry {ths_industry_name}: {e}"
                )

        if fast_mode:
            try:
                cached_rows = self.get_cached_stock_list_by_industry(ths_industry_name)
                for stock in cached_rows:
                    symbol = str(stock.get("symbol") or stock.get("code") or "").strip()
                    if symbol:
                        merged_stocks[symbol] = stock
            except Exception as exc:
                logger.warning(
                    f"Cached industry stocks fallback for {ths_industry_name} failed: {exc}"
                )
        else:
            merge_akshare_rows()

        # 2. 如果 AKShare 数据较少 (少于 10 只) 或没有数据，优先走可解析的 Sina 节点码。
        if len(merged_stocks) < 10:
            try:
                resolved_code = self._resolve_sina_industry_code(
                    ths_industry_name,
                    allow_live=not fast_mode,
                )
                if resolved_code:
                    sina_stocks = self._call_with_circuit(
                        "sina_industry_stocks",
                        self.sina.get_industry_stocks,
                        resolved_code,
                    )
                    sina_stocks = self._refine_proxy_constituents(
                        ths_industry_name, sina_stocks, resolved_code
                    )
                    for stock in self._normalize_sina_stock_rows(sina_stocks):
                        symbol = str(stock.get("symbol") or "").strip()
                        if symbol and symbol not in merged_stocks:
                            merged_stocks[symbol] = stock
            except Exception as e:
                logger.warning(
                    f"Sina resolved-node fallback for industry {ths_industry_name} failed: {e}"
                )

        # 3. 如果节点码未命中或数据依然偏少，再尝试基于行业列表名称匹配。
        if len(merged_stocks) < 10:
            try:
                matched_named_fallback = False
                possible_names = map_ths_to_sina(ths_industry_name)
                persistent_lookup = SinaFinanceProvider._get_persistent_industry_list_lookup()
                for sina_name in possible_names:
                    for row in persistent_lookup.get(sina_name, []):
                        industry_code = str(row.get("industry_code") or "").strip()
                        if not industry_code:
                            continue
                        sina_stocks = self._call_with_circuit(
                            "sina_industry_stocks",
                            self.sina.get_industry_stocks,
                            industry_code,
                        )
                        sina_stocks = self._refine_proxy_constituents(
                            ths_industry_name, sina_stocks, industry_code
                        )

                        for stock in self._normalize_sina_stock_rows(sina_stocks):
                            symbol = str(stock.get("symbol") or "").strip()
                            if symbol and symbol not in merged_stocks:
                                merged_stocks[symbol] = stock
                        if sina_stocks:
                            matched_named_fallback = True
                            break
                    if matched_named_fallback:
                        break

                if not matched_named_fallback and not fast_mode:
                    live_industries = self._call_with_circuit(
                        "sina_industry_list",
                        self.sina.get_industry_list,
                    )
                    if live_industries is not None and not live_industries.empty:
                        self.__class__._sina_industry_list_shared_cache = live_industries.copy()
                        self.__class__._sina_industry_list_shared_cache_time = time.time()
                        possible_names = map_ths_to_sina(ths_industry_name)
                        for sina_name in possible_names:
                            match = live_industries[live_industries["industry_name"] == sina_name]
                            if match.empty:
                                continue
                            industry_code = match.iloc[0]["industry_code"]
                            sina_stocks = self._call_with_circuit(
                                "sina_industry_stocks",
                                self.sina.get_industry_stocks,
                                industry_code,
                            )
                            sina_stocks = self._refine_proxy_constituents(
                                ths_industry_name, sina_stocks, industry_code
                            )

                            for stock in self._normalize_sina_stock_rows(sina_stocks):
                                symbol = str(stock.get("symbol") or "").strip()
                                if symbol and symbol not in merged_stocks:
                                    merged_stocks[symbol] = stock
                            if sina_stocks:
                                break
            except Exception as e:
                logger.warning(f"Sina named fallback for industry {ths_industry_name} failed: {e}")

        if len(merged_stocks) < 10:
            try:
                heuristic_stocks = self._build_symbol_cache_industry_fallback(ths_industry_name)
                for stock in heuristic_stocks:
                    symbol = str(stock.get("symbol") or stock.get("code") or "").strip()
                    if symbol and symbol not in merged_stocks:
                        merged_stocks[symbol] = stock
            except Exception as e:
                logger.warning(
                    f"Symbol-cache fallback for industry {ths_industry_name} failed: {e}"
                )

        if fast_mode and not merged_stocks:
            try:
                persistent_leader_rows = self._build_persistent_leading_stock_fallback(
                    ths_industry_name
                )
                for stock in persistent_leader_rows:
                    symbol = str(stock.get("symbol") or stock.get("code") or "").strip()
                    if symbol:
                        merged_stocks[symbol] = stock
            except Exception as exc:
                logger.warning(
                    f"Persistent leader fallback for industry {ths_industry_name} failed: {exc}"
                )

        if fast_mode and not merged_stocks:
            logger.info(
                "Fast mode exhausted local fallbacks for %s; skipping live AKShare constituent fetch",
                ths_industry_name,
            )

        result = list(merged_stocks.values())
        if result:
            # 自动更新缓存
            self.__class__._update_symbol_cache_from_pairs(
                [(s.get("name", ""), s.get("symbol", "")) for s in result]
            )
        else:
            log_fn = logger.debug if fast_mode else logger.warning
            log_fn(f"No stocks found for industry {ths_industry_name} from any source.")

        # 3. 最后兜底：如果依然没有数据，尝试使用 THS 领涨股构造最小可用成分股
        if not merged_stocks:
            try:
                ths_summary = self._get_ths_industry_summary(cached_only=fast_mode)
                if not ths_summary.empty:
                    summary_row = ths_summary[ths_summary["industry_name"] == ths_industry_name]
                    if not summary_row.empty:
                        row = summary_row.iloc[0]
                        leader_name = str(row.get("leading_stock") or "").strip()
                        leader_symbol = self.get_symbol_by_name(leader_name)
                        if leader_name and leader_symbol and str(leader_symbol).isdigit():
                            valuation = self.get_stock_valuation(str(leader_symbol))
                            merged_stocks[str(leader_symbol)] = {
                                "symbol": str(leader_symbol),
                                "code": str(leader_symbol),
                                "name": leader_name,
                                "change_pct": float(
                                    row.get("leading_stock_change") or row.get("change_pct") or 0
                                ),
                                "market_cap": float(valuation.get("market_cap") or 0),
                                "pe_ratio": float(valuation.get("pe_ttm") or 0),
                                "pb_ratio": float(valuation.get("pb") or 0),
                            }
            except Exception as e:
                logger.warning(f"Final THS leader fallback failed: {e}")

        if not merged_stocks:
            try:
                tushare_leader_rows = self._build_tushare_leading_stock_fallback(
                    ths_industry_name
                )
                for stock in tushare_leader_rows:
                    symbol = str(stock.get("symbol") or stock.get("code") or "").strip()
                    if symbol:
                        merged_stocks[symbol] = stock
            except Exception as e:
                logger.warning(f"Final Tushare leader fallback failed: {e}")

        result = list(merged_stocks.values())
        if result:
            self.__class__._update_symbol_cache_from_pairs(
                [(s.get("name", ""), s.get("symbol", "")) for s in result]
            )
        else:
            log_fn = logger.debug if fast_mode else logger.warning
            log_fn(f"No stocks found for industry {ths_industry_name} from any source.")

        return result

    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """获取单股最新报价。

        优先新浪实时：单股一次请求、稳定且真正实时，避开 AKShare/东方财富那条会拉
        全市场现货、被拦截时又无超时(挂起数十秒)的路径。新浪不可用时降级 AKShare。
        """
        try:
            prefix = (
                "sh" if symbol.startswith("6") else "sz" if symbol.startswith(("0", "3")) else "bj"
            )
            sina_symbol = f"{prefix}{symbol}"
            data = self._call_with_circuit(
                "sina_stock_realtime",
                self.sina.get_stock_realtime,
                [sina_symbol],
            )
            if not data.empty:
                row = data.iloc[0]
                current_price = float(row.get("price", 0) or 0)
                previous_close = float(row.get("pre_close", 0) or 0)
                updated_at = None
                if row.get("date") and row.get("time"):
                    updated_at = datetime.fromisoformat(f"{row.get('date')}T{row.get('time')}")
                    updated_at = updated_at.isoformat()
                return {
                    "symbol": symbol,
                    "name": row.get("name", ""),
                    "current_price": current_price,
                    "previous_close": previous_close,
                    "change": current_price - previous_close if previous_close else None,
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "open": float(row.get("open", 0) or 0),
                    "bid": float(row.get("bid", 0) or 0),
                    "ask": float(row.get("ask", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "amount": float(row.get("amount", 0) or 0),
                    "source": "sina_realtime",
                    "updated_at": updated_at,
                }
        except Exception as e:
            logger.warning(f"Sina latest quote failed for {symbol}: {e}, falling back to AKShare")

        try:
            quote = self.akshare.get_latest_quote(symbol)
            if "error" not in quote:
                return {
                    "symbol": symbol,
                    "name": quote.get("name", ""),
                    "current_price": quote.get("price"),
                    "previous_close": quote.get("prev_close"),
                    "change": quote.get("change"),
                    "change_percent": quote.get("change_percent"),
                    "high": quote.get("high"),
                    "low": quote.get("low"),
                    "open": quote.get("open"),
                    "volume": quote.get("volume"),
                    "amount": quote.get("amount"),
                    "source": "akshare_realtime",
                    "updated_at": quote.get("timestamp").isoformat()
                    if getattr(quote.get("timestamp"), "isoformat", None)
                    else quote.get("timestamp"),
                }
        except Exception as e:
            logger.warning(f"AKShare latest quote failed for {symbol}: {e}")

        return {"symbol": symbol, "error": "Quote not found"}

    def get_industry_index(
        self, industry_code: str, start_date=None, end_date=None
    ) -> pd.DataFrame:
        """
        获取行业指数历史数据

        优先委托给 AKShare 的申万行业指数接口；新浪侧暂无稳定行业指数历史时，
        这里直接走 AKShare，避免上层分析器拿不到行业走势和真实波动率。

        Args:
            industry_code: 行业代码

        Returns:
            行业指数 OHLCV 数据；失败时返回空 DataFrame
        """
        requested_code = str(industry_code or "").strip()
        resolved_code = self._resolve_sw_industry_index_code(requested_code)
        if not resolved_code:
            logger.info(
                "Skipping industry index history because no SW code mapping was found for %s",
                requested_code,
            )
            return pd.DataFrame()

        if resolved_code != requested_code:
            logger.info(
                "Resolved industry index code %s -> %s before AKShare history lookup",
                requested_code,
                resolved_code,
            )

        try:
            return self.akshare.get_industry_index(
                resolved_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as e:
            logger.warning(
                "Industry index history not available for requested=%s resolved=%s: %s",
                requested_code,
                resolved_code,
                e,
            )
            return pd.DataFrame()

    def get_stock_valuation(self, symbol: str, cached_only: bool = False) -> Dict[str, Any]:
        """
        获取股票估值数据。

        实时明细(cached_only=False)优先走 Tushare daily_basic：单股一次调用、稳定，
        避开 AKShare/东方财富现货被拦截或拉全市场的慢路径；Tushare 不可用时再降级到
        AKShare → 新浪实时 + 腾讯。列表路径(cached_only=True)沿用 AKShare 进程内缓存。
        """
        # Tushare EOD valuation as the primary source for live detail fetches.
        if not cached_only and self.tushare is not None:
            try:
                ts_val = self.tushare.get_stock_valuation(symbol)
            except Exception as exc:  # noqa: BLE001 - degrade to AKShare/Sina chain
                ts_val = None
                logger.warning(f"Tushare valuation failed for {symbol}: {exc}, falling back")
            if isinstance(ts_val, dict) and "error" not in ts_val:
                return ts_val

        try:
            try:
                val = self.akshare.get_stock_valuation(symbol, cached_only=cached_only)
            except TypeError:
                val = self.akshare.get_stock_valuation(symbol)
            if "error" not in val:
                return val
        except Exception as e:
            logger.warning(f"AKShare valuation failed for {symbol}: {e}, falling back to Sina")

        if cached_only:
            return {"symbol": symbol, "error": "Cached valuation unavailable"}

        try:
            # 降级：转换股票代码为新浪格式
            prefix = (
                "sh" if symbol.startswith("6") else "sz" if symbol.startswith(("0", "3")) else "bj"
            )
            sina_symbol = f"{prefix}{symbol}"

            data = self._call_with_circuit(
                "sina_stock_realtime",
                self.sina.get_stock_realtime,
                [sina_symbol],
            )
            if data.empty:
                return {"error": f"No data for {symbol}"}

            row = data.iloc[0]

            # 引入腾讯财经备用接口获取市值、PE、换手率等估值核心参数
            market_cap, pe_ttm, turnover, pb = 0.0, 0.0, 0.0, 0.0
            try:
                import requests

                # 腾讯财经格式: sz000001, sh600000, bj832471 等与新浪拼法完全一致
                url = f"http://qt.gtimg.cn/q={sina_symbol}"
                resp = self._call_with_circuit(
                    "tencent_stock_detail_http",
                    requests.get,
                    url,
                    timeout=5,
                )
                if resp.status_code == 200 and "v_" in resp.text:
                    parts = resp.text.split('"')[1].split("~")
                    if len(parts) > 46:
                        # 45: 总市值(亿), 39: 市盈率TTM, 38: 换手率, 46: 市净率
                        market_cap = float(parts[45]) * 100000000 if parts[45] else 0
                        pe_ttm = float(parts[39]) if parts[39] else 0
                        turnover = float(parts[38]) if parts[38] else 0
                        pb = float(parts[46]) if parts[46] else 0
            except Exception as e:
                logger.warning(f"Tencent fallback failed for {symbol}: {e}")

            pre_close = float(row.get("pre_close", 1))
            current = float(row.get("price", 0))
            change_pct = (current - pre_close) / pre_close * 100 if pre_close > 0 else 0

            return {
                "symbol": symbol,
                "name": row.get("name", ""),
                "market_cap": market_cap,
                "pe_ttm": pe_ttm,
                "pb": pb,
                "turnover": turnover,
                "amount": float(row.get("amount", 0)),
                "change_pct": change_pct,
            }
        except Exception as e:
            logger.warning(f"Error getting fallback valuation for {symbol}: {e}")
            return {"error": str(e)}

    def get_stock_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取股票财务数据（优先 Tushare fina_indicator，再 AKShare，失败返回中性默认值）
        """
        # Tushare fina_indicator (ROE / 营收同比 / 净利同比) as the primary source —
        # AKShare/同花顺 financials are frequently blocked.
        if self.tushare is not None:
            try:
                ts_fin = self.tushare.get_stock_financial_data(symbol)
            except Exception as exc:  # noqa: BLE001 - degrade to AKShare default
                ts_fin = None
                logger.warning(f"Tushare financial data failed for {symbol}: {exc}, falling back")
            if isinstance(ts_fin, dict) and "error" not in ts_fin:
                return ts_fin

        try:
            return self.akshare.get_stock_financial_data(symbol)
        except Exception as e:
            logger.warning(f"AKShare financial data failed for {symbol}: {e}, returning default")
            return {
                "roe": 0,
                "revenue_yoy": 0,
                "profit_yoy": 0,
            }

    def get_historical_data(self, symbol: str, start_date=None, end_date=None) -> pd.DataFrame:
        """
        获取股票历史 K 线数据（增加磁盘持久化缓存，优先 AKShare(EastMoney)，失败则降级）
        """
        self.__class__._ensure_history_cache_loaded()

        from datetime import datetime, timedelta

        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d") if isinstance(end_date, datetime) else str(end_date)

        cache_key = f"{symbol}_{start_str}_{end_str}"

        # 1. 检查缓存 (TTL: 4小时)
        cache_entry = self.__class__._history_cache.get(cache_key)
        if cache_entry:
            timestamp = cache_entry.get("timestamp", 0)
            if time.time() - timestamp < 14400:  # 4小时
                try:
                    df = pd.DataFrame(cache_entry["data"])
                    if not df.empty:
                        df["date"] = pd.to_datetime(df["date"])
                        df.set_index("date", inplace=True)
                        return df
                except Exception as e:
                    logger.warning(f"Error decoding history cache for {symbol}: {e}")

        df = pd.DataFrame()
        # Tushare daily bars first for A-shares: one reliable call that returns
        # the same date-indexed OHLCV frame, avoiding the AKShare/EastMoney
        # historical scrape (frequently blocked, no timeout → hangs ~60s).
        if self.tushare is not None:
            try:
                ts_hist = self.tushare.get_historical_data(symbol, start_date, end_date)
                if ts_hist is not None and not ts_hist.empty and "close" in ts_hist.columns:
                    df = ts_hist
            except Exception as exc:  # noqa: BLE001 - degrade to AKShare/Sina chain
                logger.warning(f"Tushare historical failed for {symbol}: {exc}, falling back")

        if df.empty:
            try:
                df = self.akshare.get_historical_data(symbol, start_date, end_date)
            except Exception as e:
                logger.warning(
                    f"AKShare historical data failed for {symbol}: {e}, falling back to Sina Daily"
                )

        if df.empty:
            try:
                # 降级：转换股票代码为新浪格式
                prefix = (
                    "sh"
                    if symbol.startswith("6")
                    else "sz"
                    if symbol.startswith(("0", "3"))
                    else "bj"
                )
                sina_symbol = f"{prefix}{symbol}"

                df_fallback = self._call_with_circuit(
                    "stock_zh_a_daily",
                    ak.stock_zh_a_daily,
                    symbol=sina_symbol,
                    start_date=start_str,
                    end_date=end_str,
                )
                if not df_fallback.empty and "close" in df_fallback.columns:
                    df_fallback["date"] = pd.to_datetime(df_fallback["date"])
                    df_fallback.set_index("date", inplace=True)
                    df = df_fallback
            except Exception as fallback_e:
                logger.debug(
                    f"Historical data completely failed to load for {symbol}: {fallback_e}"
                )

        # 2. 如果获取成功，存入缓存
        if not df.empty:
            try:
                # 准备序列化数据 (重置索引以便保存日期列)
                cache_data = df.reset_index()
                cache_data["date"] = cache_data["date"].dt.strftime("%Y-%m-%d")

                self.__class__._history_cache[cache_key] = {
                    "timestamp": time.time(),
                    "data": cache_data.to_dict(orient="records"),
                }
                self.__class__._persist_history_cache()
            except Exception as e:
                logger.warning(f"Failed to cache history data for {symbol}: {e}")

        return df


# 工厂函数：自动选择可用的数据提供器
# 工厂函数：自动选择可用的数据提供器
def create_industry_provider():
    """
    创建行业数据提供器

    始终返回 SinaIndustryAdapter，因为该适配器内部已实现了
    对 THS、AKShare、Tushare、Sina、Tencent 的五源数据融合和能力回退机制。

    Returns:
        可用的数据提供器实例
    """
    logger.info(
        "Initializing THS-first industry provider "
        "(THS + AKShare + Tushare + Sina + Tencent)"
    )
    return SinaIndustryAdapter()


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    adapter = SinaIndustryAdapter()

    print("=== Industry Classification ===")
    industries = adapter.get_industry_classification()
    print(industries.head(10).to_string())

    print("\n=== Money Flow ===")
    flow = adapter.get_industry_money_flow()
    print(
        flow[
            [
                "industry_name",
                "change_pct",
                "main_net_inflow",
                "flow_strength",
                "total_market_cap",
                "turnover_rate",
            ]
        ]
        .head(10)
        .to_string()
    )

    print("\n=== Industry Stocks ===")
    if not industries.empty:
        name = industries.iloc[0]["industry_name"]
        stocks = adapter.get_stock_list_by_industry(name)
        print(f"Stocks in {name}: {len(stocks)}")
        for s in stocks[:5]:
            print(f"  {s['code']} {s['name']}: {s['change_pct']}%")
