"""Integration tests for ``DataProviderFactory`` failover.

Covers the cross-provider behavior that no single unit test exercises:
priority-ordered iteration, exception → next provider, empty-frame → next
provider, ``fallback_enabled=False`` early-raise, and exhausted-providers
empty return.

All providers used here are pure in-process subclasses of
``BaseDataProvider`` — no network or third-party SDKs are touched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.data.providers.base_provider import BaseDataProvider
from src.data.providers.provider_factory import DataProviderFactory


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


def _ohlcv(start: str = "2024-01-01", periods: int = 5, base: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="B")
    return pd.DataFrame(
        {
            "open": [base + i for i in range(periods)],
            "high": [base + i + 1 for i in range(periods)],
            "low": [base + i - 1 for i in range(periods)],
            "close": [base + i + 0.5 for i in range(periods)],
            "volume": [1_000_000 + i * 1000 for i in range(periods)],
        },
        index=dates,
    )


class _MockProvider(BaseDataProvider):
    """Configurable in-memory provider for failover tests."""

    requires_api_key = False

    def __init__(
        self,
        name: str,
        priority: int,
        *,
        behavior: str = "ok",
        marker: float = 100.0,
    ) -> None:
        super().__init__(api_key=None)
        self.name = name
        self.priority = priority
        self.behavior = behavior
        self.marker = marker
        self.calls = 0

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        self.calls += 1
        if self.behavior == "raise":
            raise RuntimeError(f"{self.name}: simulated upstream timeout")
        if self.behavior == "empty":
            return pd.DataFrame()
        if self.behavior == "ok":
            return _ohlcv(base=self.marker)
        raise AssertionError(f"unknown behavior: {self.behavior}")

    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:  # pragma: no cover
        return {"symbol": symbol, "price": self.marker}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def factory_with_mocks():
    """Build a factory and inject three mock providers, bypassing the class registry."""

    def _build(
        behavior_a: str = "raise",
        behavior_b: str = "empty",
        behavior_c: str = "ok",
        fallback_enabled: bool = True,
    ):
        factory = DataProviderFactory(
            config={
                "default": "mock_a",
                "providers": [],  # don't auto-init anything
                "api_keys": {},
                "fallback_enabled": fallback_enabled,
            }
        )
        provider_a = _MockProvider("mock_a", priority=1, behavior=behavior_a, marker=100.0)
        provider_b = _MockProvider("mock_b", priority=2, behavior=behavior_b, marker=200.0)
        provider_c = _MockProvider("mock_c", priority=3, behavior=behavior_c, marker=300.0)
        factory.providers = {
            "mock_a": provider_a,
            "mock_b": provider_b,
            "mock_c": provider_c,
        }
        return factory, provider_a, provider_b, provider_c

    return _build


# ---------------------------------------------------------------------------
# Tests — failover semantics
# ---------------------------------------------------------------------------


def test_failover_walks_through_providers_until_one_succeeds(factory_with_mocks):
    factory, a, b, c = factory_with_mocks(
        behavior_a="raise", behavior_b="empty", behavior_c="ok"
    )

    df = factory.get_historical_data("TEST")

    assert not df.empty
    # Provider C uses marker=300.0, so its first close should be 300.5
    assert df["close"].iloc[0] == pytest.approx(300.5)
    # Each provider in priority order was attempted exactly once
    assert (a.calls, b.calls, c.calls) == (1, 1, 1)


def test_failover_returns_first_non_empty_response(factory_with_mocks):
    factory, a, b, c = factory_with_mocks(
        behavior_a="empty", behavior_b="ok", behavior_c="ok"
    )

    df = factory.get_historical_data("TEST")

    assert df["close"].iloc[0] == pytest.approx(200.5)  # provider B's marker
    # C should not be reached once B succeeds
    assert (a.calls, b.calls, c.calls) == (1, 1, 0)


def test_fallback_disabled_propagates_first_failure(factory_with_mocks):
    factory, a, b, c = factory_with_mocks(
        behavior_a="raise",
        behavior_b="ok",
        behavior_c="ok",
        fallback_enabled=False,
    )

    with pytest.raises(RuntimeError, match="simulated upstream timeout"):
        factory.get_historical_data("TEST")

    # B and C must not be called when fallback is off
    assert (a.calls, b.calls, c.calls) == (1, 0, 0)


def test_all_providers_failing_returns_empty_frame(factory_with_mocks):
    factory, a, b, c = factory_with_mocks(
        behavior_a="raise", behavior_b="raise", behavior_c="empty"
    )

    df = factory.get_historical_data("TEST")

    assert df.empty
    assert (a.calls, b.calls, c.calls) == (1, 1, 1)


def test_explicit_provider_skips_failover(factory_with_mocks):
    """Passing ``provider="mock_b"`` must use B directly, ignoring priority."""
    factory, a, b, c = factory_with_mocks(
        behavior_a="ok", behavior_b="ok", behavior_c="ok"
    )

    df = factory.get_historical_data("TEST", provider="mock_b")

    assert df["close"].iloc[0] == pytest.approx(200.5)
    assert (a.calls, b.calls, c.calls) == (0, 1, 0)
