"""
数据提供器工厂
负责创建、管理和切换数据提供器
"""

import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Type
import logging
import os
import re

from .base_provider import BaseDataProvider, DataProviderError
from .commodity_provider import CommodityProvider
from .yahoo_provider import YahooFinanceProvider
from .alphavantage_provider import AlphaVantageProvider
from .twelvedata_provider import TwelveDataProvider
from .akshare_provider import AKShareProvider
from .us_stock_provider import USStockProvider
from ..market_depth import resolve_market_depth

logger = logging.getLogger(__name__)


class DataProviderFactory:
    """
    数据提供器工厂

    功能:
    - 管理多个数据提供器
    - 根据优先级选择数据源
    - 实现故障转移（自动切换到备用数据源）
    - 支持配置化的数据源管理

    使用示例:
        factory = DataProviderFactory()
        data = factory.get_historical_data("AAPL")
    """

    # 注册的提供器类
    PROVIDER_CLASSES: Dict[str, Type[BaseDataProvider]] = {
        "commodity": CommodityProvider,
        "yahoo": YahooFinanceProvider,
        "alphavantage": AlphaVantageProvider,
        "twelvedata": TwelveDataProvider,
        "akshare": AKShareProvider,
        "us_stock": USStockProvider,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据提供器工厂

        Args:
            config: 配置字典，包含:
                - default: 默认数据源名称
                - providers: 启用的数据源列表
                - api_keys: 各数据源的 API 密钥
                - fallback_enabled: 是否启用故障转移
        """
        self.config = config or self._get_default_config()
        self.providers: Dict[str, BaseDataProvider] = {}
        self.fallback_enabled = self.config.get("fallback_enabled", True)
        self.provider_events: List[Dict[str, Any]] = []
        self._last_fetch_source_health: Dict[str, Any] = {}

        # 初始化所有配置的提供器
        self._initialize_providers()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "default": "yahoo",
            "providers": ["us_stock", "commodity", "yahoo", "alphavantage", "twelvedata"],
            "api_keys": {
                "alphavantage": os.getenv("ALPHAVANTAGE_API_KEY"),
                "twelvedata": os.getenv("TWELVEDATA_API_KEY"),
            },
            "fallback_enabled": True,
        }

    def get_cross_market_provider_order(self, asset_class: str) -> List[str]:
        asset_class = str(asset_class or "").strip().upper()
        mapping = {
            "US_STOCK": ["us_stock", "yahoo", "alphavantage", "twelvedata"],
            "ETF": ["us_stock", "yahoo", "alphavantage", "twelvedata"],
            "COMMODITY_FUTURES": ["commodity", "yahoo"],
        }
        preferred = mapping.get(asset_class, [self.config.get("default", "yahoo"), "yahoo"])
        return [name for name in preferred if name in self.providers]

    def _utc_checked_at(self) -> str:
        """Return a stable UTC timestamp for source-health contracts."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _public_reason(self, reason: Any) -> Optional[str]:
        """Return a client-safe provider failure reason with credentials redacted."""
        if reason is None:
            return None
        text = str(reason)
        text = re.sub(
            r"(?i)(api[_-]?key|apikey|access[_-]?token|token|secret|authorization|bearer)=([^&\s]+)",
            r"\1=[REDACTED]",
            text,
        )
        text = re.sub(r"(?i)(authorization|bearer)\s+[^\s,;]+", r"\1 [REDACTED]", text)
        return text[:240] + "…" if len(text) > 240 else text

    def _provider_capabilities(self, provider: BaseDataProvider) -> Dict[str, bool]:
        """Describe declared provider capabilities without probing upstream APIs."""
        return {
            "historical_data": True,
            "latest_quote": True,
            "fundamental_data": callable(getattr(provider, "get_fundamental_data", None)),
            "order_book": provider.supports_capability("order_book"),
        }

    def _provider_health_entry(
        self,
        name: str,
        *,
        status: str,
        ok: bool,
        reason: Optional[str] = None,
        provider: Optional[BaseDataProvider] = None,
    ) -> Dict[str, Any]:
        provider_class = self.PROVIDER_CLASSES.get(name)
        requires_api_key = bool(
            getattr(provider or provider_class, "requires_api_key", False)
        )
        return {
            "id": name,
            "name": name,
            "label": getattr(provider or provider_class, "name", name),
            "ok": ok,
            "status": status,
            "reason": self._public_reason(reason),
            "required": name == self.config.get("default", "yahoo"),
            "fallback": (not ok) and self.fallback_enabled,
            "requires_api_key": requires_api_key,
            "priority": getattr(provider or provider_class, "priority", None),
            "rate_limit": getattr(provider or provider_class, "rate_limit", None),
            "capabilities": self._provider_capabilities(provider) if provider else {},
            "checked_at": self._utc_checked_at(),
        }

    def _record_provider_event(
        self, name: str, status: str, *, reason: Optional[str] = None
    ) -> None:
        self.provider_events.append({
            "provider": name,
            "status": status,
            "reason": self._public_reason(reason),
            "checked_at": self._utc_checked_at(),
        })

    def get_source_health_report(self) -> Dict[str, Any]:
        """Return a normalized, non-invasive source health/freshness report.

        The report is designed for dashboards and API responses: it explains which
        sources are configured, which were initialized, whether fallback is enabled,
        and the last fetch attempt chain. It deliberately avoids live API probing so
        health panels do not create rate-limit or latency side effects.
        """
        configured = list(self.config.get("providers", []))
        event_by_provider = {event["provider"]: event for event in self.provider_events}
        sources: List[Dict[str, Any]] = []

        for name in configured:
            provider = self.providers.get(name)
            if provider is not None:
                sources.append(self._provider_health_entry(name, status="ready", ok=True, provider=provider))
                continue
            event = event_by_provider.get(name, {})
            sources.append(
                self._provider_health_entry(
                    name,
                    status=str(event.get("status") or "unavailable"),
                    ok=False,
                    reason=event.get("reason"),
                )
            )

        for name, provider in self.providers.items():
            if name not in configured:
                sources.append(self._provider_health_entry(name, status="ready", ok=True, provider=provider))

        return {
            "checked_at": self._utc_checked_at(),
            "default_source": self.config.get("default", "yahoo"),
            "fallback_enabled": self.fallback_enabled,
            "configured_sources": configured,
            "active_provider_count": len(self.providers),
            "configured_provider_count": len(configured),
            "sources": sources,
            "last_fetch": self._last_fetch_source_health or None,
        }

    def get_last_fetch_source_health(self) -> Dict[str, Any]:
        """Return the most recent fetch attempt chain, if any."""
        return self._last_fetch_source_health.copy() if self._last_fetch_source_health else {}

    def _record_fetch_health(
        self,
        *,
        symbol: str,
        interval: str,
        status: str,
        attempts: List[Dict[str, Any]],
        selected_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_index = next(
            (
                index
                for index, attempt in enumerate(attempts)
                if attempt.get("id") == selected_source and attempt.get("ok")
            ),
            None,
        )
        fallback_used = bool(
            self.fallback_enabled
            and selected_index is not None
            and any(not attempt.get("ok") for attempt in attempts[:selected_index])
        )
        report = {
            "checked_at": self._utc_checked_at(),
            "symbol": symbol,
            "interval": interval,
            "status": status,
            "selected_source": selected_source,
            "fallback_used": fallback_used,
            "attempts": attempts,
        }
        self._last_fetch_source_health = report
        return report.copy()

    def _attach_source_health(
        self, data: pd.DataFrame, report: Dict[str, Any]
    ) -> pd.DataFrame:
        """Attach request-scoped source health to a returned DataFrame."""
        if isinstance(data, pd.DataFrame):
            data.attrs["source_health"] = report.copy()
        return data

    def _initialize_providers(self):
        """初始化所有配置的数据提供器"""
        enabled_providers = self.config.get("providers", ["yahoo"])
        api_keys = self.config.get("api_keys", {})

        for name in enabled_providers:
            if name in self.PROVIDER_CLASSES:
                try:
                    provider_class = self.PROVIDER_CLASSES[name]
                    api_key = api_keys.get(name)

                    # 跳过需要 API 密钥但未提供的提供器
                    if provider_class.requires_api_key and not api_key:
                        self._record_provider_event(name, "skipped", reason="missing_api_key")
                        logger.info(f"Skipping {name}: API key not provided")
                        continue

                    self.providers[name] = provider_class(api_key=api_key)
                    self._record_provider_event(name, "ready")
                    logger.info(f"Initialized provider: {name}")

                except Exception as e:
                    self._record_provider_event(name, "error", reason=str(e))
                    logger.error(f"Failed to initialize provider {name}: {e}")
            else:
                self._record_provider_event(name, "unknown", reason="unknown_provider")
                logger.warning(f"Unknown provider: {name}")

    def get_provider(self, name: Optional[str] = None) -> BaseDataProvider:
        """
        获取指定的数据提供器

        Args:
            name: 提供器名称，默认使用配置的默认提供器

        Returns:
            数据提供器实例
        """
        if name is None:
            name = self.config.get("default", "yahoo")

        if name not in self.providers:
            raise DataProviderError(f"Provider not available: {name}")

        return self.providers[name]

    def get_sorted_providers(self) -> List[BaseDataProvider]:
        """获取按优先级排序的提供器列表"""
        return sorted(self.providers.values(), key=lambda p: p.priority)

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
        provider: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取历史数据（带故障转移）

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 数据间隔
            provider: 指定数据源（可选）

        Returns:
            OHLCV 数据 DataFrame
        """
        if provider:
            data = self.get_provider(provider).get_historical_data(
                symbol, start_date, end_date, interval
            )
            ok = not data.empty
            attempts = [
                {
                    "id": provider,
                    "ok": ok,
                    "status": "success" if ok else "empty",
                    "reason": None if ok else "empty_frame",
                    "row_count": len(data) if hasattr(data, "__len__") else None,
                    "fallback": False,
                    "checked_at": self._utc_checked_at(),
                }
            ]
            report = self._record_fetch_health(
                symbol=symbol,
                interval=interval,
                status="success" if ok else "empty",
                selected_source=provider if ok else None,
                attempts=attempts,
            )
            return self._attach_source_health(data, report)

        errors = []
        attempts: List[Dict[str, Any]] = []
        for p in self.get_sorted_providers():
            try:
                logger.debug(f"Trying provider: {p.name}")
                data = p.get_historical_data(symbol, start_date, end_date, interval)
                row_count = len(data) if hasattr(data, "__len__") else None
                if not data.empty:
                    attempts.append({
                        "id": p.name,
                        "ok": True,
                        "status": "success",
                        "reason": None,
                        "row_count": row_count,
                        "fallback": False,
                        "checked_at": self._utc_checked_at(),
                    })
                    report = self._record_fetch_health(
                        symbol=symbol,
                        interval=interval,
                        status="success",
                        selected_source=p.name,
                        attempts=attempts,
                    )
                    return self._attach_source_health(data, report)
                attempts.append({
                    "id": p.name,
                    "ok": False,
                    "status": "empty",
                    "reason": "empty_frame",
                    "row_count": row_count,
                    "fallback": self.fallback_enabled,
                    "checked_at": self._utc_checked_at(),
                })
                if not self.fallback_enabled:
                    report = self._record_fetch_health(
                        symbol=symbol,
                        interval=interval,
                        status="empty",
                        attempts=attempts,
                    )
                    return self._attach_source_health(pd.DataFrame(), report)
            except Exception as e:
                errors.append(f"{p.name}: {self._public_reason(e)}")
                attempts.append({
                    "id": p.name,
                    "ok": False,
                    "status": "error",
                    "reason": self._public_reason(e),
                    "row_count": None,
                    "fallback": self.fallback_enabled,
                    "checked_at": self._utc_checked_at(),
                })
                if not self.fallback_enabled:
                    self._record_fetch_health(
                        symbol=symbol,
                        interval=interval,
                        status="error",
                        attempts=attempts,
                    )
                    raise
                logger.warning(f"Provider {p.name} failed: {e}")
                continue

        logger.error(f"All providers failed for {symbol}: {errors}")
        report = self._record_fetch_health(
            symbol=symbol,
            interval=interval,
            status="failed",
            attempts=attempts,
        )
        return self._attach_source_health(pd.DataFrame(), report)

    def get_cross_market_historical_data(
        self,
        symbol: str,
        asset_class: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> tuple[pd.DataFrame, str]:
        errors = []
        for provider_name in self.get_cross_market_provider_order(asset_class):
            try:
                provider = self.get_provider(provider_name)
                data = provider.get_historical_data(symbol, start_date, end_date, interval)
                if not data.empty:
                    return data, provider_name
            except Exception as e:
                errors.append(f"{provider_name}: {e}")
                if not self.fallback_enabled:
                    raise
                logger.warning(f"Cross-market provider {provider_name} failed for {symbol}: {e}")
                continue

        logger.error(f"All cross-market providers failed for {symbol} ({asset_class}): {errors}")
        return pd.DataFrame(), ""

    def get_latest_quote(self, symbol: str, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        获取最新报价（带故障转移）
        """
        if provider:
            return self.get_provider(provider).get_latest_quote(symbol)

        for p in self.get_sorted_providers():
            try:
                result = p.get_latest_quote(symbol)
                if "error" not in result:
                    return result
            except Exception as e:
                if not self.fallback_enabled:
                    raise
                logger.warning(f"Provider {p.name} failed: {e}")
                continue

        return {"symbol": symbol, "error": "All providers failed"}

    def get_fundamental_data(self, symbol: str, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        获取基本面数据（带故障转移）
        """
        if provider:
            return self.get_provider(provider).get_fundamental_data(symbol)

        for p in self.get_sorted_providers():
            try:
                result = p.get_fundamental_data(symbol)
                if "error" not in result:
                    return result
            except Exception as e:
                if not self.fallback_enabled:
                    raise
                logger.warning(f"Provider {p.name} failed: {e}")
                continue

        return {"symbol": symbol, "error": "All providers failed"}

    def get_order_book(self, symbol: str, levels: int = 10) -> Dict[str, Any]:
        """
        获取市场深度，优先真实 Level 2，再退回 quote-proxy / synthetic。
        """
        return resolve_market_depth(
            symbol,
            levels=levels,
            provider_factory=self,
            quote_loader=lambda probe_symbol: self.get_latest_quote(probe_symbol),
        )

    def get_market_depth_capabilities(self, symbol: str, levels: int = 10) -> Dict[str, Any]:
        """
        返回市场深度能力探测结果，供前端/诊断面板直接使用。
        """
        return self.get_order_book(symbol, levels=levels)

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """获取所有可用的提供器信息"""
        return [p.get_provider_info() for p in self.providers.values()]

    def get_provider_runtime_status(self) -> Dict[str, Any]:
        """Return non-invasive provider status and circuit-breaker snapshots."""
        status: Dict[str, Any] = {}
        for name, provider in self.providers.items():
            circuit_loader = getattr(provider, "get_circuit_status", None)
            status[name] = {
                "provider": provider.get_provider_info(),
                "circuit_breakers": circuit_loader() if callable(circuit_loader) else {},
            }
        return status

    def check_all_providers(self) -> Dict[str, bool]:
        """检查所有提供器的可用性"""
        return {name: p.is_available() for name, p in self.providers.items()}


# 全局工厂实例
_default_factory: Optional[DataProviderFactory] = None


def get_data_factory(config: Optional[Dict[str, Any]] = None) -> DataProviderFactory:
    """
    获取数据提供器工厂（单例模式）

    Args:
        config: 配置字典

    Returns:
        DataProviderFactory 实例
    """
    global _default_factory

    if _default_factory is None or config is not None:
        _default_factory = DataProviderFactory(config)

    return _default_factory
