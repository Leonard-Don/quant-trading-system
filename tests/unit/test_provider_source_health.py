from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd

from src.data.providers.base_provider import BaseDataProvider
from src.data.providers.provider_factory import DataProviderFactory


class _ReadyProvider(BaseDataProvider):
    name = "ready"
    priority = 1
    requires_api_key = False

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        return pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1))

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "price": 1.0}


class _EmptyProvider(_ReadyProvider):
    name = "empty"
    priority = 1

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        return pd.DataFrame()


class _KeyProvider(_ReadyProvider):
    name = "needs_key"
    requires_api_key = True


class _ErrorProvider(_ReadyProvider):
    name = "error"
    priority = 1

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raise RuntimeError(
            "Request failed: https://example.invalid/query?apikey=SECRET123&symbol=TEST"
        )


def test_source_health_report_explains_ready_and_skipped_sources(monkeypatch):
    monkeypatch.setattr(
        DataProviderFactory,
        "PROVIDER_CLASSES",
        {"ready": _ReadyProvider, "needs_key": _KeyProvider},
    )

    factory = DataProviderFactory(
        {
            "default": "ready",
            "providers": ["ready", "needs_key"],
            "api_keys": {"needs_key": None},
            "fallback_enabled": True,
        }
    )

    report = factory.get_source_health_report()
    by_id = {source["id"]: source for source in report["sources"]}

    assert report["fallback_enabled"] is True
    assert by_id["ready"]["ok"] is True
    assert by_id["ready"]["status"] == "ready"
    assert by_id["needs_key"]["ok"] is False
    assert by_id["needs_key"]["status"] == "skipped"
    assert by_id["needs_key"]["reason"] == "missing_api_key"
    assert by_id["needs_key"]["fallback"] is True


def test_last_fetch_health_records_fallback_chain():
    factory = DataProviderFactory(
        {
            "default": "empty",
            "providers": [],
            "api_keys": {},
            "fallback_enabled": True,
        }
    )
    factory.providers = {
        "empty": _EmptyProvider(),
        "ready": _ReadyProvider(),
    }

    data = factory.get_historical_data("TEST")
    report = factory.get_last_fetch_source_health()

    assert data.attrs["source_health"] == report
    assert not data.empty
    assert report["status"] == "success"
    assert report["selected_source"] == "ready"
    assert report["fallback_used"] is True
    assert [attempt["id"] for attempt in report["attempts"]] == ["empty", "ready"]
    assert report["attempts"][0]["status"] == "empty"
    assert report["attempts"][1]["status"] == "success"



def test_last_fetch_health_redacts_provider_error_details():
    factory = DataProviderFactory(
        {
            "default": "error",
            "providers": [],
            "api_keys": {},
            "fallback_enabled": True,
        }
    )
    factory.providers = {"error": _ErrorProvider()}

    data = factory.get_historical_data("TEST")
    report = data.attrs["source_health"]

    assert data.empty
    assert report["status"] == "failed"
    assert "SECRET123" not in str(report)
    assert "apikey=[REDACTED]" in report["attempts"][0]["reason"]


def test_data_manager_historical_data_uses_provider_factory_source_health(monkeypatch):
    import src.data.data_manager as data_manager_module

    class _AltDataManagerStub:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(data_manager_module, "AltDataManager", _AltDataManagerStub)
    monkeypatch.setattr(
        DataProviderFactory,
        "PROVIDER_CLASSES",
        {"ready": _ReadyProvider},
    )
    manager = data_manager_module.DataManager(
        data_source_config={
            "default": "ready",
            "providers": ["ready"],
            "api_keys": {},
            "fallback_enabled": True,
        }
    )

    data = manager.get_historical_data("TEST")
    report = data.attrs.get("source_health")

    assert not data.empty
    assert report["symbol"] == "TEST"
    assert report["selected_source"] == "ready"
    assert report["status"] == "success"


def test_empty_provider_does_not_fallback_when_fallback_disabled():
    factory = DataProviderFactory(
        {
            "default": "empty",
            "providers": [],
            "api_keys": {},
            "fallback_enabled": False,
        }
    )
    factory.providers = {
        "empty": _EmptyProvider(),
        "ready": _ReadyProvider(),
    }

    data = factory.get_historical_data("TEST")
    report = data.attrs["source_health"]

    assert data.empty
    assert report["status"] == "empty"
    assert report["selected_source"] is None
    assert report["fallback_used"] is False
    assert [attempt["id"] for attempt in report["attempts"]] == ["empty"]


def test_data_manager_does_not_use_legacy_yahoo_when_provider_fallback_disabled(monkeypatch):
    import src.data.data_manager as data_manager_module

    class _AltDataManagerStub:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(data_manager_module, "AltDataManager", _AltDataManagerStub)
    monkeypatch.setattr(
        DataProviderFactory,
        "PROVIDER_CLASSES",
        {"empty": _EmptyProvider},
    )
    manager = data_manager_module.DataManager(
        data_source_config={
            "default": "empty",
            "providers": ["empty"],
            "api_keys": {},
            "fallback_enabled": False,
        }
    )

    def fail_legacy_fetch(*args, **kwargs):  # pragma: no cover - failure path is the assertion
        raise AssertionError("legacy yahoo fallback should not run when provider fallback is disabled")

    monkeypatch.setattr(manager, "_fetch_yahoo_historical_data", fail_legacy_fetch)

    data = manager.get_historical_data("TEST")
    report = data.attrs.get("source_health")

    assert data.empty
    assert report["status"] == "empty"
    assert report["fallback_used"] is False
    assert [attempt["id"] for attempt in report["attempts"]] == ["empty"]


def test_data_manager_does_not_use_legacy_yahoo_when_fallback_disabled_and_period_unresolved(monkeypatch):
    import src.data.data_manager as data_manager_module

    class _AltDataManagerStub:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(data_manager_module, "AltDataManager", _AltDataManagerStub)
    manager = data_manager_module.DataManager(
        data_source_config={
            "default": "empty",
            "providers": [],
            "api_keys": {},
            "fallback_enabled": False,
        }
    )

    def fail_legacy_fetch(*args, **kwargs):  # pragma: no cover - failure path is the assertion
        raise AssertionError("legacy yahoo fallback should not run when provider fallback is disabled")

    monkeypatch.setattr(manager, "_fetch_yahoo_historical_data", fail_legacy_fetch)

    data = manager.get_historical_data("TEST", period="max")
    report = data.attrs.get("source_health")

    assert data.empty
    assert report["status"] == "unavailable"
    assert report["selected_source"] is None
    assert report["attempts"][0]["reason"] == "period_not_supported_by_provider_path"
