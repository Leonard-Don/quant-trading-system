"""
US stock / ETF provider built on top of Yahoo Finance.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .yahoo_provider import YahooFinanceProvider


class USStockProvider(YahooFinanceProvider):
    """Asset-class aware wrapper for US stocks and ETFs."""

    name = "us_stock"
    priority = 1

    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] | None = None):
        super().__init__(api_key=api_key, config=config)

