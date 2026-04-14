"""
实时数据管理模块
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..core.base import BaseComponent
from ..utils.cache import cache_manager
from .data_manager import DataManager
from .providers.base_provider import BaseDataProvider
from .providers.provider_factory import get_data_factory


logger = logging.getLogger(__name__)
PROVIDER_FAILURE_THRESHOLD = 3
PROVIDER_COOLDOWN_SECONDS = 60
PROVIDER_FETCH_TIMEOUT_SECONDS = 3
ETF_LIKE_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA", "UVXY", "VXX", "TLT", "FXI", "EEM", "HYG"}
QUOTE_QUALITY_FIELDS = [
    "price",
    "change",
    "change_percent",
    "volume",
    "high",
    "low",
    "open",
    "previous_close",
    "bid",
    "ask",
]


@dataclass
class RealTimeQuote:
    """统一的实时报价数据模型。"""

    symbol: str
    price: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    volume: Optional[int]
    timestamp: datetime
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    previous_close: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典。"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RealTimeQuote":
        """从缓存字典恢复为对象。"""
        quote_data = data.copy()
        timestamp = quote_data.get("timestamp")
        if isinstance(timestamp, str):
            quote_data["timestamp"] = datetime.fromisoformat(timestamp)
        elif not isinstance(timestamp, datetime):
            quote_data["timestamp"] = datetime.now()
        return cls(**quote_data)


class RealTimeDataManager(BaseComponent):
    """统一的实时行情管理器。"""

    def __init__(self, update_interval: int = 5, max_history: int = 1000, max_global_history: int = 100_000):
        super().__init__({})
        self.update_interval = update_interval
        self.max_history = max_history
        self.max_global_history = max_global_history
        # 对实时工作台来说，几十秒内的旧报价仍可先展示并由 freshness 标签标记，
        # 这样能显著缩短重新进入页面时的首包等待。
        self.cache_ttl = max(update_interval * 6, 30)
        self.provider_factory = get_data_factory()
        self.data_manager = DataManager()
        self.subscribed_symbols: Set[str] = set()
        self.subscribers: Dict[str, Set[Callable[[RealTimeQuote], None]]] = {}
        self.quote_history: Dict[str, List[RealTimeQuote]] = {}
        self.is_running = False
        self.update_executor = ThreadPoolExecutor(max_workers=4)
        self.fetch_executor = ThreadPoolExecutor(max_workers=20)
        self._lock = threading.RLock()
        self.bundle_cache_ttl = min(self.cache_ttl, 2)
        self._quotes_bundle_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Dict[str, Any]]]] = {}
        self.provider_health: Dict[str, Dict[str, Any]] = {}
        self.runtime_stats: Dict[str, Any] = {
            "bundle_cache_hits": 0,
            "bundle_cache_misses": 0,
            "bundle_cache_writes": 0,
            "bundle_prewarm_calls": 0,
            "last_fetch_stats": None,
            "last_bundle_cache_key": [],
        }

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    def _normalize_symbols(self, symbols: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: Set[str] = set()
        for symbol in symbols:
            if not isinstance(symbol, str):
                continue
            canonical = self._normalize_symbol(symbol)
            if canonical and canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
        return normalized

    @staticmethod
    def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        if value in (None, ""):
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_datetime(value: Any) -> datetime:
        def _normalize(dt: datetime) -> datetime:
            if dt.tzinfo is not None:
                return datetime.fromtimestamp(dt.timestamp())
            return dt

        if isinstance(value, datetime):
            return _normalize(value)
        if isinstance(value, str):
            try:
                return _normalize(datetime.fromisoformat(value))
            except ValueError:
                return datetime.now()
        return datetime.now()

    def _cache_key(self, symbol: str) -> str:
        return f"realtime_quote_{symbol}"

    def _deserialize_cached_quote(self, symbol: str) -> Optional[RealTimeQuote]:
        cached_data = cache_manager.get(self._cache_key(symbol))
        if not cached_data:
            return None
        try:
            quote = RealTimeQuote.from_dict(cached_data)
            quote.symbol = self._normalize_symbol(quote.symbol)
            return quote
        except Exception as exc:
            logger.warning("Failed to deserialize cached quote for %s: %s", symbol, exc)
            return None

    def _get_cached_quote(self, symbol: str) -> Optional[RealTimeQuote]:
        with self._lock:
            history = self.quote_history.get(symbol, [])
            if history:
                latest = history[-1]
                age = (datetime.now() - latest.timestamp).total_seconds()
                if age <= self.cache_ttl:
                    return latest
        return self._deserialize_cached_quote(symbol)

    def _store_quote(self, quote: RealTimeQuote) -> None:
        cache_manager.set(self._cache_key(quote.symbol), quote.to_dict(), ttl=self.cache_ttl)
        with self._lock:
            self._quotes_bundle_cache.clear()

    def _bundle_cache_key(self, symbols: List[str]) -> Tuple[str, ...]:
        return tuple(sorted(self._normalize_symbols(symbols)))

    def _get_cached_quote_bundle(self, symbols: List[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        if not symbols:
            return None

        cache_key = self._bundle_cache_key(symbols)
        if not cache_key:
            return None

        with self._lock:
            cached_entry = self._quotes_bundle_cache.get(cache_key)
            if not cached_entry:
                self.runtime_stats["bundle_cache_misses"] += 1
                return None

            cached_at, payload = cached_entry
            if (time.time() - cached_at) > self.bundle_cache_ttl:
                self._quotes_bundle_cache.pop(cache_key, None)
                self.runtime_stats["bundle_cache_misses"] += 1
                return None

            self.runtime_stats["bundle_cache_hits"] += 1
            return {symbol: quote.copy() for symbol, quote in payload.items()}

    def _store_cached_quote_bundle(self, symbols: List[str], payload: Dict[str, Dict[str, Any]]) -> None:
        cache_key = self._bundle_cache_key(symbols)
        if not cache_key or not payload:
            return

        with self._lock:
            self._quotes_bundle_cache[cache_key] = (
                time.time(),
                {symbol: quote.copy() for symbol, quote in payload.items()},
            )
            self.runtime_stats["bundle_cache_writes"] += 1
            self.runtime_stats["last_bundle_cache_key"] = list(cache_key)

    def prewarm_quote_bundle(
        self,
        symbols: List[str],
        payload: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            return {}

        resolved_payload = payload
        if resolved_payload is None:
            resolved_payload = {}
            for symbol in normalized_symbols:
                cached_quote = self._get_cached_quote(symbol)
                if cached_quote:
                    resolved_payload[symbol] = cached_quote.to_dict()

        if not resolved_payload:
            return {}

        with self._lock:
            self.runtime_stats["bundle_prewarm_calls"] += 1
        self._store_cached_quote_bundle(normalized_symbols, resolved_payload)
        return {symbol: quote.copy() for symbol, quote in resolved_payload.items()}

    def _build_quote(
        self,
        symbol: str,
        payload: Dict[str, Any],
        default_source: Optional[str] = None,
    ) -> Optional[RealTimeQuote]:
        if not payload or "error" in payload:
            return None

        price = self._to_float(payload.get("price"))
        change = self._to_float(payload.get("change"))
        previous_close = self._to_float(
            payload.get("previous_close", payload.get("prev_close", payload.get("previousClose")))
        )
        if previous_close is None and price is not None and change is not None:
            previous_close = price - change
        if price is None and previous_close is not None and change is not None:
            price = previous_close + change

        change_percent = self._to_float(
            payload.get("change_percent", payload.get("percent_change"))
        )
        if change_percent is None:
            change_percent = (change / previous_close * 100) if change is not None and previous_close not in (None, 0) else None

        return RealTimeQuote(
            symbol=symbol,
            price=price,
            change=change,
            change_percent=change_percent,
            volume=self._to_int(payload.get("volume")),
            timestamp=self._to_datetime(payload.get("timestamp")),
            high=self._to_float(payload.get("high")),
            low=self._to_float(payload.get("low")),
            open=self._to_float(payload.get("open")),
            previous_close=previous_close,
            bid=self._to_float(payload.get("bid")),
            ask=self._to_float(payload.get("ask")),
            source=str(payload.get("source") or default_source or "unknown"),
        )

    def _ensure_provider_health(self, provider_name: str) -> Dict[str, Any]:
        with self._lock:
            return self.provider_health.setdefault(provider_name, {
                "successes": 0,
                "failures": 0,
                "consecutive_failures": 0,
                "skipped": 0,
                "last_success_at": None,
                "last_failure_at": None,
                "circuit_open_until": 0.0,
            })

    def _mark_provider_success(self, provider_name: str) -> None:
        stats = self._ensure_provider_health(provider_name)
        with self._lock:
            stats["successes"] += 1
            stats["consecutive_failures"] = 0
            stats["last_success_at"] = datetime.now().isoformat()
            stats["circuit_open_until"] = 0.0

    def _mark_provider_failure(self, provider_name: str, reason: str = "") -> None:
        stats = self._ensure_provider_health(provider_name)
        with self._lock:
            stats["failures"] += 1
            stats["consecutive_failures"] += 1
            stats["last_failure_at"] = datetime.now().isoformat()
            if stats["consecutive_failures"] >= PROVIDER_FAILURE_THRESHOLD:
                stats["circuit_open_until"] = time.time() + PROVIDER_COOLDOWN_SECONDS
        if reason:
            logger.warning("Realtime provider failure recorded: provider=%s reason=%s", provider_name, reason)

    def _mark_provider_skipped(self, provider_name: str) -> None:
        stats = self._ensure_provider_health(provider_name)
        with self._lock:
            stats["skipped"] += 1

    def _get_provider_fetch_order(self) -> List[BaseDataProvider]:
        providers = self.provider_factory.get_sorted_providers()
        now = time.time()
        available: List[BaseDataProvider] = []
        cooling_down: List[BaseDataProvider] = []

        for provider in providers:
            stats = self._ensure_provider_health(provider.name)
            if stats["circuit_open_until"] and stats["circuit_open_until"] > now:
                self._mark_provider_skipped(provider.name)
                cooling_down.append(provider)
            else:
                available.append(provider)

        ranked_available = sorted(
            available,
            key=lambda provider: (
                self._ensure_provider_health(provider.name)["consecutive_failures"],
                provider.priority,
                provider.name,
            ),
        )

        return ranked_available + cooling_down

    def _get_preferred_provider_names_for_symbol(self, symbol: str) -> List[str]:
        normalized = self._normalize_symbol(symbol)
        if normalized.endswith("=F"):
            preferred = self.provider_factory.get_cross_market_provider_order("COMMODITY_FUTURES")
        elif normalized in ETF_LIKE_SYMBOLS:
            preferred = self.provider_factory.get_cross_market_provider_order("ETF")
        elif normalized.endswith(".SS") or normalized.endswith(".SZ") or normalized.startswith("^") or normalized.endswith("-USD"):
            preferred = [
                name
                for name in ("yahoo", "alphavantage", "twelvedata")
                if name in self.provider_factory.providers
            ]
        else:
            preferred = self.provider_factory.get_cross_market_provider_order("US_STOCK")

        if preferred:
            return preferred

        return [provider.name for provider in self._get_provider_fetch_order()]

    def _infer_asset_class_for_symbol(self, symbol: str) -> str:
        normalized = self._normalize_symbol(symbol)
        if normalized.endswith("=F"):
            return "COMMODITY_FUTURES"
        if normalized in ETF_LIKE_SYMBOLS:
            return "ETF"
        if normalized.endswith("-USD"):
            return "CRYPTO"
        if normalized.endswith(".SS") or normalized.endswith(".SZ") or normalized.startswith("^"):
            return "INDEX"
        return "US_STOCK"

    def _build_quote_from_history_payload(
        self,
        symbol: str,
        rows: List[Dict[str, Any]],
        source: str,
    ) -> Optional[RealTimeQuote]:
        if not rows:
            return None

        latest_row = rows[-1] or {}
        previous_row = rows[-2] if len(rows) > 1 else None
        latest_close = self._to_float(latest_row.get("close"))
        previous_close = self._to_float(previous_row.get("close")) if previous_row else None
        if latest_close is None:
            return None

        change = None
        change_percent = None
        if previous_close not in (None, 0):
            change = latest_close - previous_close
            change_percent = (change / previous_close) * 100

        timestamp = latest_row.get("date")
        if timestamp in (None, ""):
            timestamp = datetime.now().isoformat()

        return self._build_quote(
            symbol,
            {
                "symbol": symbol,
                "price": latest_close,
                "change": change,
                "change_percent": change_percent,
                "volume": latest_row.get("volume"),
                "high": latest_row.get("high"),
                "low": latest_row.get("low"),
                "open": latest_row.get("open"),
                "previous_close": previous_close,
                "timestamp": timestamp,
                "source": source,
            },
            default_source=source,
        )

    def _fetch_historical_fallback_quotes(self, symbols: List[str]) -> Dict[str, RealTimeQuote]:
        fallback_quotes: Dict[str, RealTimeQuote] = {}
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            return fallback_quotes

        def fetch_single_symbol(symbol: str) -> Tuple[str, Optional[RealTimeQuote]]:
            asset_class = self._infer_asset_class_for_symbol(symbol)
            try:
                historical = self.data_manager.get_cross_market_historical_data(
                    symbol=symbol,
                    asset_class=asset_class,
                    start_date=datetime.now() - timedelta(days=10),
                    end_date=datetime.now(),
                    interval="1d",
                )
                data = historical.get("data")
                if data is None or getattr(data, "empty", True):
                    return symbol, None
                rows = data.tail(2).reset_index().to_dict("records")
                provider = historical.get("provider") or "historical"
                quote = self._build_quote_from_history_payload(
                    symbol,
                    rows,
                    source=f"history_fallback:{provider}",
                )
                return symbol, quote
            except Exception as exc:
                logger.warning("Historical fallback failed for %s: %s", symbol, exc)
                return symbol, None

        max_workers = min(len(normalized_symbols), 6)
        futures = {
            self.fetch_executor.submit(fetch_single_symbol, symbol): symbol
            for symbol in normalized_symbols
        }
        done, not_done = wait(futures, timeout=max(PROVIDER_FETCH_TIMEOUT_SECONDS, 3))

        for future in done:
            symbol, quote = future.result()
            if quote:
                fallback_quotes[symbol] = quote

        for future in not_done:
            future.cancel()
            symbol = futures[future]
            logger.warning("Historical fallback timed out for %s", symbol)

        if fallback_quotes:
            logger.info(
                "Historical fallback provided quotes: requested=%s resolved=%s",
                len(normalized_symbols),
                len(fallback_quotes),
            )

        return fallback_quotes

    def subscribe_symbol(self, symbol: str, callback: Optional[Callable[[RealTimeQuote], None]] = None) -> bool:
        """订阅股票实时数据。"""
        canonical = self._normalize_symbol(symbol)
        with self._lock:
            newly_added = canonical not in self.subscribed_symbols
            self.subscribed_symbols.add(canonical)
            if callback:
                self.subscribers.setdefault(canonical, set()).add(callback)
            self.quote_history.setdefault(canonical, [])

        self.logger.info(
            "订阅实时数据: symbol=%s total_symbols=%s callbacks=%s",
            canonical,
            len(self.subscribed_symbols),
            len(self.subscribers.get(canonical, set())),
        )
        return newly_added

    def unsubscribe_symbol(
        self,
        symbol: str,
        callback: Optional[Callable[[RealTimeQuote], None]] = None,
    ) -> bool:
        """取消订阅。"""
        canonical = self._normalize_symbol(symbol)
        removed = False
        with self._lock:
            if callback and canonical in self.subscribers:
                self.subscribers[canonical].discard(callback)
                if not self.subscribers[canonical]:
                    del self.subscribers[canonical]
            elif callback is None and canonical in self.subscribers:
                del self.subscribers[canonical]

            if callback is None or canonical not in self.subscribers:
                removed = canonical in self.subscribed_symbols
                self.subscribed_symbols.discard(canonical)

        self.logger.info(
            "取消订阅: symbol=%s removed=%s remaining_symbols=%s",
            canonical,
            removed,
            len(self.subscribed_symbols),
        )
        return removed

    def get_latest_quote(self, symbol: str) -> Optional[RealTimeQuote]:
        """获取最新报价对象。"""
        canonical = self._normalize_symbol(symbol)
        with self._lock:
            history = self.quote_history.get(canonical, [])
            if history:
                return history[-1]

        quotes, _ = self._fetch_real_time_data([canonical], use_cache=True)
        return quotes.get(canonical)

    def get_quote_dict(self, symbol: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取单个股票的统一报价字典。"""
        canonical = self._normalize_symbol(symbol)
        quotes, _ = self._fetch_real_time_data([canonical], use_cache=use_cache)
        quote = quotes.get(canonical)
        return quote.to_dict() if quote else None

    def get_cached_quotes_dict(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """仅返回当前缓存中已有的报价，不触发新的数据抓取。"""
        cached_payload: Dict[str, Dict[str, Any]] = {}
        for symbol in self._normalize_symbols(symbols):
            cached_quote = self._get_cached_quote(symbol)
            if cached_quote:
                cached_payload[symbol] = cached_quote.to_dict()
        return cached_payload

    def get_quotes_dict(self, symbols: List[str], use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """批量获取统一报价字典。"""
        if use_cache:
            cached_bundle = self._get_cached_quote_bundle(symbols)
            if cached_bundle is not None:
                return cached_bundle

        quotes, _ = self._fetch_real_time_data(symbols, use_cache=use_cache)
        payload = {symbol: quote.to_dict() for symbol, quote in quotes.items()}
        if use_cache:
            self._store_cached_quote_bundle(symbols, payload)
        return payload

    def get_quote_history(self, symbol: str, limit: int = 100) -> List[RealTimeQuote]:
        """获取历史报价。"""
        canonical = self._normalize_symbol(symbol)
        with self._lock:
            history = self.quote_history.get(canonical, [])
            return history[-limit:] if history else []

    def _fetch_with_provider(
        self, provider: BaseDataProvider, symbols: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        uses_batch_api = type(provider).get_multiple_quotes is not BaseDataProvider.get_multiple_quotes
        if uses_batch_api:
            future = self.fetch_executor.submit(provider.get_multiple_quotes, symbols)
            try:
                return future.result(timeout=PROVIDER_FETCH_TIMEOUT_SECONDS)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Provider {provider.name} batch quote fetch timed out after {PROVIDER_FETCH_TIMEOUT_SECONDS}s"
                ) from exc

        results: Dict[str, Dict[str, Any]] = {}
        futures = {
            self.fetch_executor.submit(provider.get_latest_quote, symbol): symbol for symbol in symbols
        }
        done, not_done = wait(futures, timeout=PROVIDER_FETCH_TIMEOUT_SECONDS)

        for future in done:
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:
                logger.warning("Provider %s failed for %s: %s", provider.name, symbol, exc)
                results[symbol] = {"symbol": symbol, "error": str(exc), "source": provider.name}

        for future in not_done:
            symbol = futures[future]
            future.cancel()
            logger.warning(
                "Provider %s timed out for %s after %ss",
                provider.name,
                symbol,
                PROVIDER_FETCH_TIMEOUT_SECONDS,
            )
            results[symbol] = {
                "symbol": symbol,
                "error": f"timeout after {PROVIDER_FETCH_TIMEOUT_SECONDS}s",
                "source": provider.name,
            }
        return results

    def _fetch_provider_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        pending = self._normalize_symbols(symbols)
        resolved: Dict[str, Dict[str, Any]] = {}
        now = time.time()
        preferred_providers = {
            symbol: self._get_preferred_provider_names_for_symbol(symbol)
            for symbol in pending
        }

        for provider in self._get_provider_fetch_order():
            if not pending:
                break

            health = self._ensure_provider_health(provider.name)
            if health["circuit_open_until"] and health["circuit_open_until"] > now:
                logger.info(
                    "Skipping realtime provider due to open circuit: provider=%s cooldown_remaining_ms=%s",
                    provider.name,
                    round((health["circuit_open_until"] - now) * 1000, 2),
                )
                continue

            eligible_symbols = [
                symbol
                for symbol in pending
                if provider.name in preferred_providers.get(symbol, [])
            ]
            if not eligible_symbols:
                continue

            try:
                provider_results = self._fetch_with_provider(provider, eligible_symbols)
            except Exception as exc:
                self._mark_provider_failure(provider.name, str(exc))
                logger.warning("Provider %s batch fetch failed: %s", provider.name, exc)
                continue

            normalized_results = {
                self._normalize_symbol(result_symbol): payload
                for result_symbol, payload in provider_results.items()
            }
            next_pending: List[str] = []
            for symbol in pending:
                if symbol not in eligible_symbols:
                    next_pending.append(symbol)
                    continue
                payload = normalized_results.get(symbol)
                if payload and "error" not in payload:
                    resolved[symbol] = payload
                else:
                    next_pending.append(symbol)

            resolved_count = len(pending) - len(next_pending)
            if resolved_count > 0:
                self._mark_provider_success(provider.name)
            else:
                self._mark_provider_failure(provider.name, "provider returned no usable quotes")

            logger.info(
                "Realtime provider fetch: provider=%s requested=%s resolved=%s remaining=%s consecutive_failures=%s",
                provider.name,
                len(pending),
                resolved_count,
                len(next_pending),
                self._ensure_provider_health(provider.name)["consecutive_failures"],
            )
            pending = next_pending

        if pending:
            logger.warning("Realtime quote fetch exhausted providers: symbols=%s", pending)

        return resolved

    def _fetch_real_time_data(
        self, symbols: List[str], use_cache: bool = True
    ) -> Tuple[Dict[str, RealTimeQuote], Dict[str, Any]]:
        requested_symbols = self._normalize_symbols(symbols)
        if not requested_symbols:
            return {}, {"requested": 0, "cache_hits": 0, "fetched": 0, "misses": 0, "duration_ms": 0}

        started_at = time.time()
        quotes: Dict[str, RealTimeQuote] = {}
        symbols_to_fetch: List[str] = []
        cache_hits = 0

        for symbol in requested_symbols:
            if use_cache:
                cached_quote = self._get_cached_quote(symbol)
                if cached_quote:
                    quotes[symbol] = cached_quote
                    cache_hits += 1
                    continue
            symbols_to_fetch.append(symbol)

        fetched = 0
        if symbols_to_fetch:
            provider_payloads = self._fetch_provider_quotes(symbols_to_fetch)
            for symbol in symbols_to_fetch:
                payload = provider_payloads.get(symbol)
                quote = self._build_quote(symbol, payload, default_source=payload.get("source") if payload else None)
                if quote:
                    quotes[symbol] = quote
                    self._store_quote(quote)
                    fetched += 1

            unresolved_symbols = [symbol for symbol in symbols_to_fetch if symbol not in quotes]
            if unresolved_symbols:
                fallback_quotes = self._fetch_historical_fallback_quotes(unresolved_symbols)
                for symbol, quote in fallback_quotes.items():
                    quotes[symbol] = quote
                    self._store_quote(quote)
                    fetched += 1

        misses = len(requested_symbols) - len(quotes)
        stats = {
            "requested": len(requested_symbols),
            "cache_hits": cache_hits,
            "fetched": fetched,
            "misses": misses,
            "duration_ms": round((time.time() - started_at) * 1000, 2),
        }
        logger.info(
            "Realtime fetch summary: requested=%s cache_hits=%s fetched=%s misses=%s duration_ms=%s",
            stats["requested"],
            stats["cache_hits"],
            stats["fetched"],
            stats["misses"],
            stats["duration_ms"],
        )
        with self._lock:
            self.runtime_stats["last_fetch_stats"] = stats.copy()
        return quotes, stats

    def _update_quotes(self) -> None:
        """更新当前所有订阅标的的报价。"""
        if not self.subscribed_symbols:
            return

        symbols = list(self.subscribed_symbols)
        quotes, stats = self._fetch_real_time_data(symbols, use_cache=True)
        callbacks_to_notify: List[Tuple[Callable[[RealTimeQuote], None], RealTimeQuote]] = []

        with self._lock:
            for symbol, quote in quotes.items():
                history = self.quote_history.setdefault(symbol, [])
                history.append(quote)
                if len(history) > self.max_history:
                    self.quote_history[symbol] = history[-self.max_history :]

                for callback in self.subscribers.get(symbol, set()):
                    callbacks_to_notify.append((callback, quote))

            # Enforce global memory cap by trimming the longest histories first
            total = sum(len(h) for h in self.quote_history.values())
            if total > self.max_global_history:
                by_length = sorted(
                    self.quote_history.items(),
                    key=lambda item: len(item[1]),
                    reverse=True,
                )
                excess = total - self.max_global_history
                for sym, hist in by_length:
                    if excess <= 0:
                        break
                    trim = min(len(hist) - 1, excess)
                    if trim > 0:
                        self.quote_history[sym] = hist[trim:]
                        excess -= trim

        self.prewarm_quote_bundle(
            symbols,
            payload={symbol: quote.to_dict() for symbol, quote in quotes.items()},
        )

        for callback, quote in callbacks_to_notify:
            try:
                callback(quote)
            except Exception as exc:
                self.logger.error("回调函数执行失败: %s", exc)

        self.logger.info(
            "Realtime update cycle: symbols=%s callbacks=%s cache_hits=%s fetched=%s misses=%s",
            len(symbols),
            len(callbacks_to_notify),
            stats["cache_hits"],
            stats["fetched"],
            stats["misses"],
        )

    def initialize(self) -> None:
        """初始化组件。"""
        self.logger.info("实时数据管理器初始化完成")

    def cleanup(self) -> None:
        """清理资源。"""
        self.stop_real_time_updates()
        self.update_executor.shutdown(wait=True)
        self.fetch_executor.shutdown(wait=True)
        self.logger.info("实时数据管理器清理完成")

    async def start_real_time_updates(self) -> None:
        """开始实时数据更新。"""
        self.is_running = True
        self.logger.info("开始实时数据更新")

        while self.is_running:
            try:
                start_time = time.time()
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(self.update_executor, self._update_quotes)
                update_time = time.time() - start_time
                self.logger.debug("Realtime update duration_ms=%s", round(update_time * 1000, 2))
                await asyncio.sleep(self.update_interval)
            except Exception as exc:
                self.logger.error("实时数据更新错误: %s", exc)
                await asyncio.sleep(self.update_interval)

    def stop_real_time_updates(self) -> None:
        """停止实时数据更新。"""
        self.is_running = False
        self.logger.info("停止实时数据更新")

    def get_market_summary(self) -> Dict[str, Any]:
        """获取市场概览。"""
        with self._lock:
            latest_quotes: List[RealTimeQuote] = []
            tracked_symbols = sorted(set(self.subscribed_symbols) | set(self.quote_history.keys()))
            total_quotes = sum(len(history) for history in self.quote_history.values())
            summary = {
                "subscribed_symbols": len(self.subscribed_symbols),
                "total_quotes": total_quotes,
                "max_global_history": self.max_global_history,
                "global_history_usage": round(total_quotes / self.max_global_history, 3) if self.max_global_history else 0,
                "active_symbols": [],
                "market_status": "open",
                "last_update": datetime.now().isoformat(),
                "cache": {
                    "quote_cache_ttl_seconds": self.cache_ttl,
                    "bundle_cache_ttl_seconds": self.bundle_cache_ttl,
                    "bundle_cache_entries": len(self._quotes_bundle_cache),
                    "bundle_cache_hits": self.runtime_stats["bundle_cache_hits"],
                    "bundle_cache_misses": self.runtime_stats["bundle_cache_misses"],
                    "bundle_cache_writes": self.runtime_stats["bundle_cache_writes"],
                    "bundle_prewarm_calls": self.runtime_stats["bundle_prewarm_calls"],
                    "last_bundle_cache_key": self.runtime_stats["last_bundle_cache_key"],
                    "last_fetch_stats": self.runtime_stats["last_fetch_stats"],
                },
                "provider_health": {
                    name: stats.copy()
                    for name, stats in self.provider_health.items()
                },
            }

            for symbol in tracked_symbols:
                latest = self._get_cached_quote(symbol)
                if not latest:
                    continue

                latest_quotes.append(latest)
                summary["active_symbols"].append(
                    {
                        "symbol": symbol,
                        "price": latest.price,
                        "change_percent": latest.change_percent,
                        "volume": latest.volume,
                        "source": latest.source,
                    }
                )

            total_active = len(latest_quotes)
            field_coverage = []
            missing_by_symbol = []
            for field_name in QUOTE_QUALITY_FIELDS:
                present_count = sum(
                    1
                    for quote in latest_quotes
                    if getattr(quote, field_name, None) is not None
                )
                field_coverage.append(
                    {
                        "field": field_name,
                        "present": present_count,
                        "missing": max(0, total_active - present_count),
                        "coverage_ratio": round((present_count / total_active), 4) if total_active else 0.0,
                    }
                )

            for quote in latest_quotes:
                missing_fields = [
                    field_name for field_name in QUOTE_QUALITY_FIELDS
                    if getattr(quote, field_name, None) is None
                ]
                missing_by_symbol.append(
                    {
                        "symbol": quote.symbol,
                        "source": quote.source,
                        "missing_fields": missing_fields,
                        "missing_count": len(missing_fields),
                    }
                )

            summary["quality"] = {
                "active_quote_count": total_active,
                "field_coverage": field_coverage,
                "most_incomplete_symbols": sorted(
                    missing_by_symbol,
                    key=lambda item: (-item["missing_count"], item["symbol"]),
                )[:5],
            }

            return summary


realtime_manager = RealTimeDataManager()
