"""
Yahoo Finance 数据提供器
基于 yfinance 库实现
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import pandas as pd
import yfinance as yf
from typing import Any, Dict, Iterator, List, Optional, Set

from .base_provider import BaseDataProvider, DataProviderError

logger = logging.getLogger(__name__)
YFINANCE_LOGGER_NAMES = (
    "yfinance",
    "yfinance.base",
    "yfinance.scrapers.history",
    "yfinance.scrapers.quote",
)
EXPECTED_YFINANCE_GAP_PATTERNS = (
    "possibly delisted",
    "no price data found",
    "no timezone found",
    "symbol may be delisted",
)


class _ExpectedYahooGapFilter(logging.Filter):
    def __init__(self, symbols: Set[str]):
        super().__init__()
        self.symbols = {str(symbol or "").strip().upper() for symbol in symbols if symbol}

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        normalized_message = message.lower()
        if not any(pattern in normalized_message for pattern in EXPECTED_YFINANCE_GAP_PATTERNS):
            return True

        upper_message = message.upper()
        return not any(symbol in upper_message or f"${symbol}" in upper_message for symbol in self.symbols)


class YahooFinanceProvider(BaseDataProvider):
    """
    Yahoo Finance 数据提供器
    
    使用 yfinance 库获取免费的股票数据
    无需 API 密钥，但有一定的请求频率限制
    
    特点:
    - 免费无限制使用
    - 支持全球主要市场
    - 数据延迟约 15-20 分钟
    - 支持历史数据、基本面数据
    """
    
    name = "yahoo"
    priority = 1  # 默认首选
    rate_limit = 2000  # yfinance 没有严格限制
    requires_api_key = False
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        super().__init__(api_key, config)
        self._ticker_cache: Dict[str, yf.Ticker] = {}

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return str(symbol or "").strip().upper()

    def _is_crypto_symbol(self, symbol: str) -> bool:
        return self._normalize_symbol(symbol).endswith("-USD")

    @staticmethod
    def _is_expected_gap_error(message: Any) -> bool:
        normalized = str(message or "").lower()
        return any(pattern in normalized for pattern in EXPECTED_YFINANCE_GAP_PATTERNS)

    @contextmanager
    def _suppress_expected_yfinance_noise(self, symbols: List[str]) -> Iterator[None]:
        normalized_symbols = {
            self._normalize_symbol(symbol)
            for symbol in symbols
            if self._is_crypto_symbol(symbol)
        }
        if not normalized_symbols:
            yield
            return

        log_filter = _ExpectedYahooGapFilter(normalized_symbols)
        target_loggers = [logging.getLogger(name) for name in YFINANCE_LOGGER_NAMES]
        for target_logger in target_loggers:
            target_logger.addFilter(log_filter)

        try:
            yield
        finally:
            for target_logger in target_loggers:
                target_logger.removeFilter(log_filter)

    def _build_error_payload(self, symbol: str, error: Any) -> Dict[str, Any]:
        return {
            "symbol": self._normalize_symbol(symbol),
            "error": str(error),
            "source": self.name,
        }

    def _build_quote_payload(
        self,
        symbol: str,
        ticker: Any,
        *,
        include_bid_ask: bool,
        include_market_cap: bool,
    ) -> Dict[str, Any]:
        normalized_symbol = self._normalize_symbol(symbol)
        is_crypto = self._is_crypto_symbol(normalized_symbol)
        fast_info = getattr(ticker, "fast_info", {}) or {}
        info = None

        def pick_number(*values, default=0):
            for value in values:
                if value not in (None, ""):
                    return value
            return default

        def pick_number_lazy(*suppliers, default=0):
            for supplier in suppliers:
                value = supplier()
                if value not in (None, ""):
                    return value
            return default

        def info_value(key):
            nonlocal info
            if is_crypto:
                return None
            if info is None:
                info = ticker.info
            return info.get(key)

        def cached_info_value(key):
            if info is None:
                return None
            return info.get(key)

        price = pick_number(
            fast_info.get("lastPrice"),
            default=None,
        )
        if price is None and not is_crypto:
            price = pick_number(info_value("regularMarketPrice"), default=0)

        if price in (None, "") and is_crypto:
            return self._build_error_payload(normalized_symbol, "Yahoo crypto fast quote unavailable")

        payload = {
            "symbol": normalized_symbol,
            "price": price,
            "change": pick_number_lazy(
                lambda: fast_info.get("regularMarketChange"),
                lambda: info_value("regularMarketChange"),
                default=None,
            ),
            "change_percent": pick_number_lazy(
                lambda: fast_info.get("regularMarketChangePercent"),
                lambda: info_value("regularMarketChangePercent"),
                default=None,
            ),
            "volume": pick_number_lazy(
                lambda: fast_info.get("lastVolume"),
                lambda: info_value("regularMarketVolume"),
                default=None,
            ),
            "high": pick_number_lazy(
                lambda: fast_info.get("dayHigh"),
                lambda: info_value("dayHigh"),
                default=None,
            ),
            "low": pick_number_lazy(
                lambda: fast_info.get("dayLow"),
                lambda: info_value("dayLow"),
                default=None,
            ),
            "open": pick_number_lazy(
                lambda: fast_info.get("open"),
                lambda: info_value("regularMarketOpen"),
                default=None,
            ),
            "previous_close": pick_number_lazy(
                lambda: fast_info.get("previousClose"),
                lambda: info_value("previousClose"),
                default=None,
            ),
            "bid": pick_number_lazy(
                lambda: fast_info.get("bid"),
                lambda: cached_info_value("bid"),
                default=None,
            ) if include_bid_ask else None,
            "ask": pick_number_lazy(
                lambda: fast_info.get("ask"),
                lambda: cached_info_value("ask"),
                default=None,
            ) if include_bid_ask else None,
            "timestamp": datetime.now(),
            "source": self.name,
        }
        if include_market_cap:
            payload["market_cap"] = pick_number(cached_info_value("marketCap"), default=0)
        return payload
    
    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """获取或创建 Ticker 对象（带缓存）"""
        normalized_symbol = self._normalize_symbol(symbol)
        if normalized_symbol not in self._ticker_cache:
            self._ticker_cache[normalized_symbol] = yf.Ticker(normalized_symbol)
        return self._ticker_cache[normalized_symbol]
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        支持的 interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        if end_date is None:
            end_date = datetime.now()
            
        try:
            ticker = self._get_ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )
            
            if data.empty:
                logger.warning(f"[Yahoo] No data found for {symbol}")
                return pd.DataFrame()
            
            # 标准化数据
            data = self._standardize_dataframe(data)
            data.index.name = "date"
            
            logger.debug(f"[Yahoo] Fetched {len(data)} rows for {symbol}")
            return data
            
        except Exception as e:
            logger.error(f"[Yahoo] Error fetching {symbol}: {e}")
            raise DataProviderError(f"Failed to fetch data from Yahoo: {e}")
    
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """获取最新报价"""
        normalized_symbol = self._normalize_symbol(symbol)
        try:
            with self._suppress_expected_yfinance_noise([normalized_symbol]):
                ticker = self._get_ticker(normalized_symbol)
                return self._build_quote_payload(
                    normalized_symbol,
                    ticker,
                    include_bid_ask=True,
                    include_market_cap=True,
                )
        except Exception as e:
            if self._is_crypto_symbol(normalized_symbol) and self._is_expected_gap_error(e):
                logger.info("[Yahoo] Expected crypto quote gap for %s: %s", normalized_symbol, e)
            else:
                logger.error(f"[Yahoo] Error getting quote for {normalized_symbol}: {e}")
            return self._build_error_payload(normalized_symbol, e)
    
    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """获取基本面数据"""
        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info
            
            return {
                "symbol": symbol,
                "company_name": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "forward_pe": info.get("forwardPE", 0),
                "peg_ratio": info.get("pegRatio", 0),
                "price_to_book": info.get("priceToBook", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "profit_margin": info.get("profitMargins", 0),
                "operating_margin": info.get("operatingMargins", 0),
                "roe": info.get("returnOnEquity", 0),
                "roa": info.get("returnOnAssets", 0),
                "revenue_growth": info.get("revenueGrowth", 0),
                "earnings_growth": info.get("earningsGrowth", 0),
                "debt_to_equity": info.get("debtToEquity", 0),
                "current_ratio": info.get("currentRatio", 0),
                "beta": info.get("beta", 0),
                "52w_high": info.get("fiftyTwoWeekHigh", 0),
                "52w_low": info.get("fiftyTwoWeekLow", 0),
                "analyst_rating": info.get("recommendationKey", ""),
                "target_price": info.get("targetMeanPrice", 0),
                "source": self.name
            }
            
        except Exception as e:
            logger.error(f"[Yahoo] Error getting fundamental data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "source": self.name}
    
    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取报价（优化版）"""
        results = {}
        normalized_symbols = [self._normalize_symbol(symbol) for symbol in symbols]
        
        try:
            # yfinance 支持批量下载
            with self._suppress_expected_yfinance_noise(normalized_symbols):
                tickers = yf.Tickers(" ".join(normalized_symbols))

                for symbol in normalized_symbols:
                    try:
                        ticker = tickers.tickers.get(symbol)
                        if ticker:
                            results[symbol] = self._build_quote_payload(
                                symbol,
                                ticker,
                                include_bid_ask=False,
                                include_market_cap=False,
                            )
                        else:
                            results[symbol] = self._build_error_payload(symbol, "Ticker not found")
                    except Exception as e:
                        if self._is_crypto_symbol(symbol) and self._is_expected_gap_error(e):
                            logger.info("[Yahoo] Expected crypto batch quote gap for %s: %s", symbol, e)
                        results[symbol] = self._build_error_payload(symbol, e)
        except Exception as e:
            # 降级到逐个获取
            logger.warning(f"[Yahoo] Batch fetch failed, falling back to individual: {e}")
            return super().get_multiple_quotes(normalized_symbols)
            
        return results
    
    def is_available(self) -> bool:
        """检查 Yahoo Finance 是否可用"""
        try:
            ticker = yf.Ticker("AAPL")
            data = ticker.history(period="1d")
            return not data.empty
        except Exception:
            return False
