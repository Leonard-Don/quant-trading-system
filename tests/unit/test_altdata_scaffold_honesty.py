"""
Tests that scaffold/placeholder alt-data providers advertise their synthetic nature.

Each provider that returns fabricated/placeholder signals must emit
``is_scaffold=True`` so downstream consumers can distinguish placeholder
output from real data.
"""
from __future__ import annotations

import pytest

from src.data.alternative.macro_hf.customs_data import TRACKED_CATEGORIES, CustomsDataProvider
from src.data.alternative.macro_hf.port_congestion import PortCongestionProvider
from src.data.alternative.people.executive_profile import (
    EXECUTIVE_PROFILE_CATALOG,
    ExecutiveProfileProvider,
)
from src.data.alternative.people.insider_flow import (
    INSIDER_FLOW_CATALOG,
    InsiderFlowProvider,
)

# ---------------------------------------------------------------------------
# CustomsDataProvider
# ---------------------------------------------------------------------------


class TestCustomsDataScaffold:
    def test_trade_balance_signal_has_is_scaffold_true(self):
        provider = CustomsDataProvider()
        cat = next(iter(TRACKED_CATEGORIES))
        result = provider.get_trade_balance_signal(cat)
        assert result.get("is_scaffold") is True

    def test_trade_balance_signal_error_path_has_is_scaffold_true(self):
        provider = CustomsDataProvider()
        result = provider.get_trade_balance_signal("nonexistent_category_xyz")
        # error path → is_scaffold must still be present
        assert result.get("is_scaffold") is True

    def test_all_categories_have_is_scaffold_true(self):
        provider = CustomsDataProvider()
        summary = provider.get_all_categories_summary()
        for cat_id, signal in summary.items():
            assert signal.get("is_scaffold") is True, (
                f"Category {cat_id} missing is_scaffold"
            )

    def test_trade_balance_signal_confidence_is_low(self):
        """Scaffold confidence must be <= 0.3 (cannot exceed threshold for live data)."""
        provider = CustomsDataProvider()
        for cat_id in TRACKED_CATEGORIES:
            result = provider.get_trade_balance_signal(cat_id)
            assert result["confidence"] <= 0.3, (
                f"Category {cat_id}: confidence={result['confidence']} too high for scaffold"
            )


# ---------------------------------------------------------------------------
# PortCongestionProvider
# ---------------------------------------------------------------------------


class TestPortCongestionScaffold:
    def test_global_congestion_index_has_is_scaffold_true(self):
        provider = PortCongestionProvider()
        result = provider.get_global_congestion_index()
        assert result.get("is_scaffold") is True

    def test_global_congestion_index_has_zero_confidence(self):
        provider = PortCongestionProvider()
        result = provider.get_global_congestion_index()
        assert result.get("confidence") == 0.0

    def test_global_congestion_index_signal_is_zero(self):
        """Hardcoded scaffold signal must be 0 (neutral placeholder)."""
        provider = PortCongestionProvider()
        result = provider.get_global_congestion_index()
        assert result["signal"] == 0

    def test_global_congestion_index_is_50(self):
        """Hardcoded scaffold index must remain 50 (neutral baseline)."""
        provider = PortCongestionProvider()
        result = provider.get_global_congestion_index()
        assert result["global_index"] == 50.0


# ---------------------------------------------------------------------------
# ExecutiveProfileProvider
# ---------------------------------------------------------------------------


class TestExecutiveProfileScaffold:
    def test_known_symbol_has_is_scaffold_true(self):
        provider = ExecutiveProfileProvider()
        result = provider.get_profile("NVDA")
        assert result.get("is_scaffold") is True

    def test_known_symbol_has_catalog_coverage_true(self):
        provider = ExecutiveProfileProvider()
        result = provider.get_profile("AAPL")
        assert result.get("catalog_coverage") is True

    def test_unknown_symbol_has_is_scaffold_true(self):
        provider = ExecutiveProfileProvider()
        result = provider.get_profile("UNKNOWN_XYZ_9999")
        assert result.get("is_scaffold") is True

    def test_unknown_symbol_has_catalog_coverage_false(self):
        provider = ExecutiveProfileProvider()
        result = provider.get_profile("UNKNOWN_XYZ_9999")
        assert result.get("catalog_coverage") is False

    def test_unknown_symbol_has_low_confidence(self):
        """Fallback heuristic profile must signal low confidence."""
        provider = ExecutiveProfileProvider()
        result = provider.get_profile("UNKNOWN_XYZ_9999")
        assert result["confidence"] <= 0.35

    def test_all_catalog_symbols_have_is_scaffold_true(self):
        provider = ExecutiveProfileProvider()
        for symbol in EXECUTIVE_PROFILE_CATALOG:
            result = provider.get_profile(symbol)
            assert result.get("is_scaffold") is True, (
                f"{symbol} missing is_scaffold"
            )


# ---------------------------------------------------------------------------
# InsiderFlowProvider
# ---------------------------------------------------------------------------


class TestInsiderFlowScaffold:
    def test_known_symbol_has_is_scaffold_true(self):
        provider = InsiderFlowProvider()
        result = provider.get_signal("NVDA")
        assert result.get("is_scaffold") is True

    def test_known_symbol_has_catalog_coverage_true(self):
        provider = InsiderFlowProvider()
        result = provider.get_signal("TSLA")
        assert result.get("catalog_coverage") is True

    def test_unknown_symbol_has_is_scaffold_true(self):
        provider = InsiderFlowProvider()
        result = provider.get_signal("UNKNOWN_XYZ_9999")
        assert result.get("is_scaffold") is True

    def test_unknown_symbol_has_catalog_coverage_false(self):
        provider = InsiderFlowProvider()
        result = provider.get_signal("UNKNOWN_XYZ_9999")
        assert result.get("catalog_coverage") is False

    def test_unknown_symbol_returns_neutral_default(self):
        """Symbols outside catalog must fall back to neutral (net_action=neutral)."""
        provider = InsiderFlowProvider()
        result = provider.get_signal("UNKNOWN_XYZ_9999")
        assert result["net_action"] == "neutral"

    def test_all_catalog_symbols_have_is_scaffold_true(self):
        provider = InsiderFlowProvider()
        for symbol in INSIDER_FLOW_CATALOG:
            result = provider.get_signal(symbol)
            assert result.get("is_scaffold") is True, (
                f"{symbol} missing is_scaffold"
            )
