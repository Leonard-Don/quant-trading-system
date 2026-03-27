"""
Commodity futures provider built on top of Yahoo Finance.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .yahoo_provider import YahooFinanceProvider


class CommodityProvider(YahooFinanceProvider):
    """Commodity-futures aware wrapper with lightweight ticker alias support."""

    name = "commodity"
    priority = 1

    ALIAS_MAP = {
        "COPPER": "HG=F",
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "WTI": "CL=F",
        "BRENT": "BZ=F",
        "NATGAS": "NG=F",
    }

    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] | None = None):
        super().__init__(api_key=api_key, config=config)

    def _normalize_symbol(self, symbol: str) -> str:
        return self.ALIAS_MAP.get(str(symbol or "").strip().upper(), str(symbol or "").strip().upper())

    def get_historical_data(self, symbol, start_date=None, end_date=None, interval="1d"):
        return super().get_historical_data(
            self._normalize_symbol(symbol),
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )

    def get_latest_quote(self, symbol: str):
        return super().get_latest_quote(self._normalize_symbol(symbol))

    def get_fundamental_data(self, symbol: str):
        return super().get_fundamental_data(self._normalize_symbol(symbol))

