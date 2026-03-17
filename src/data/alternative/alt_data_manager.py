"""
另类数据统一管理器

串联三条另类数据主线：
- 政经语义雷达
- 产业链信号
- 全球宏观高频信号
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Iterable, List, Optional

from .base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from .macro_hf import MacroHFSignalProvider
from .policy_radar import PolicySignalProvider
from .supply_chain import SupplyChainSignalProvider

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = {
    "policy_radar": {
        "sources": ["ndrc", "nea"],
        "limit": 5,
        "days_back": 14,
    },
    "supply_chain": {
        "industries": ["ai_compute", "grid", "nuclear"],
        "days_back": 30,
    },
    "macro_hf": {
        "metals": ["copper", "aluminium"],
        "categories": ["semiconductors", "copper_ore", "ev_battery"],
    },
}


class AltDataManager:
    """统一调度和查询另类数据提供器。"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        providers: Optional[Dict[str, BaseAltDataProvider]] = None,
    ):
        self.config = config or {}
        self.providers = providers or self._build_default_providers()
        self.latest_signals: Dict[str, Dict[str, Any]] = {}
        self.last_refresh: Optional[datetime] = None

    def _build_default_providers(self) -> Dict[str, BaseAltDataProvider]:
        provider_config = self.config.get("providers", {})
        return {
            "policy_radar": PolicySignalProvider(
                provider_config.get("policy_radar", self.config)
            ),
            "supply_chain": SupplyChainSignalProvider(
                provider_config.get("supply_chain", self.config)
            ),
            "macro_hf": MacroHFSignalProvider(
                provider_config.get("macro_hf", self.config)
            ),
        }

    def register_provider(self, name: str, provider: BaseAltDataProvider) -> None:
        self.providers[name] = provider

    def get_provider(self, name: str) -> BaseAltDataProvider:
        if name not in self.providers:
            raise KeyError(f"Unknown alternative data provider: {name}")
        return self.providers[name]

    def refresh_provider(
        self,
        name: str,
        force: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        provider = self.get_provider(name)
        if not force and not provider.needs_update() and name in self.latest_signals:
            return self.latest_signals[name]

        run_kwargs = self._merge_provider_kwargs(name, kwargs)
        signal = provider.run_pipeline(**run_kwargs)
        signal["provider"] = name
        self.latest_signals[name] = signal
        self.last_refresh = datetime.now()
        return signal

    def refresh_all(
        self,
        force: bool = False,
        provider_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        provider_params = provider_params or {}
        signals: Dict[str, Dict[str, Any]] = {}
        for name in self.providers:
            try:
                signals[name] = self.refresh_provider(
                    name, force=force, **provider_params.get(name, {})
                )
            except Exception as exc:
                logger.error("Failed to refresh provider %s: %s", name, exc, exc_info=True)
                signals[name] = {
                    "provider": name,
                    "source": name,
                    "signal": 0,
                    "strength": 0.0,
                    "confidence": 0.0,
                    "error": str(exc),
                    "timestamp": datetime.now().isoformat(),
                }
        return signals

    def get_alt_signals(
        self,
        category: Optional[str] = None,
        timeframe: str = "7d",
        refresh_if_empty: bool = False,
    ) -> Dict[str, Any]:
        if refresh_if_empty and not self.latest_signals:
            self.refresh_all()

        category_value = category.lower() if category else None
        signals = []
        for name, signal in self.latest_signals.items():
            provider = self.providers.get(name)
            provider_category = provider.category.value if provider else None
            if category_value and provider_category != category_value:
                continue
            signals.append(signal)

        records = self.get_records(category=category_value, timeframe=timeframe)
        return {
            "signals": signals,
            "records": [record.to_dict() for record in records],
            "timeframe": timeframe,
            "category": category,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
        }

    def get_records(
        self,
        category: Optional[str] = None,
        timeframe: str = "7d",
        limit: int = 200,
    ) -> List[AltDataRecord]:
        start = datetime.now() - self._parse_timeframe(timeframe)
        category_value = category.lower() if category else None
        records: List[AltDataRecord] = []
        for provider in self.providers.values():
            provider_records = provider.get_history(start=start, limit=limit)
            records.extend(provider_records)

        filtered = []
        for record in records:
            if category_value and record.category.value != category_value:
                continue
            filtered.append(record)

        filtered.sort(key=lambda record: record.timestamp, reverse=True)
        return filtered[:limit]

    def get_dashboard_snapshot(self, refresh: bool = False) -> Dict[str, Any]:
        signals = self.refresh_all(force=refresh) if refresh or not self.latest_signals else self.latest_signals
        records = self.get_records(timeframe="30d", limit=120)
        provider_status = {
            name: provider.get_provider_info()
            for name, provider in self.providers.items()
        }

        category_buckets: Dict[str, List[float]] = {}
        for record in records:
            category_buckets.setdefault(record.category.value, []).append(record.normalized_score)

        category_summary = {
            category_name: {
                "count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            }
            for category_name, scores in category_buckets.items()
        }

        return {
            "providers": provider_status,
            "signals": signals,
            "category_summary": category_summary,
            "recent_records": [record.to_dict() for record in records[:20]],
            "timestamp": datetime.now().isoformat(),
        }

    def _merge_provider_kwargs(self, name: str, runtime_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(DEFAULT_PROVIDER_CONFIG.get(name, {}))
        merged.update(self.config.get("defaults", {}).get(name, {}))
        merged.update(runtime_kwargs)
        return merged

    @staticmethod
    def _parse_timeframe(timeframe: str) -> timedelta:
        value = (timeframe or "7d").strip().lower()
        if value.endswith("h"):
            return timedelta(hours=max(1, int(value[:-1] or 1)))
        if value.endswith("w"):
            return timedelta(weeks=max(1, int(value[:-1] or 1)))
        if value.endswith("d"):
            return timedelta(days=max(1, int(value[:-1] or 1)))
        return timedelta(days=7)
