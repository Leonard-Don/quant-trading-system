"""
Yahoo Finance 数据提供器
基于 yfinance 库实现
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging

from .base_provider import BaseDataProvider, DataProviderError

logger = logging.getLogger(__name__)


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
    
    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """获取或创建 Ticker 对象（带缓存）"""
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol)
        return self._ticker_cache[symbol]
    
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
        try:
            ticker = self._get_ticker(symbol)
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
                if info is None:
                    info = ticker.info
                return info.get(key)

            # 先走 fast_info，只有关键信息缺失时才访问更慢的 info。
            price = pick_number(
                fast_info.get("lastPrice"),
                default=None,
            )
            if price is None:
                price = pick_number(info_value("regularMarketPrice"), default=0)

            return {
                "symbol": symbol,
                "price": price,
                "change": pick_number_lazy(
                    lambda: fast_info.get("regularMarketChange"),
                    lambda: info_value("regularMarketChange"),
                ),
                "change_percent": pick_number_lazy(
                    lambda: fast_info.get("regularMarketChangePercent"),
                    lambda: info_value("regularMarketChangePercent"),
                ),
                "volume": pick_number_lazy(
                    lambda: fast_info.get("lastVolume"),
                    lambda: info_value("regularMarketVolume"),
                ),
                "high": pick_number_lazy(
                    lambda: fast_info.get("dayHigh"),
                    lambda: info_value("dayHigh"),
                ),
                "low": pick_number_lazy(
                    lambda: fast_info.get("dayLow"),
                    lambda: info_value("dayLow"),
                ),
                "open": pick_number_lazy(
                    lambda: fast_info.get("open"),
                    lambda: info_value("regularMarketOpen"),
                ),
                "previous_close": pick_number_lazy(
                    lambda: fast_info.get("previousClose"),
                    lambda: info_value("previousClose"),
                ),
                "bid": pick_number_lazy(
                    lambda: fast_info.get("bid"),
                    lambda: info_value("bid"),
                    default=None,
                ),
                "ask": pick_number_lazy(
                    lambda: fast_info.get("ask"),
                    lambda: info_value("ask"),
                    default=None,
                ),
                "market_cap": pick_number(info.get("marketCap"), default=0) if info is not None else 0,
                "timestamp": datetime.now(),
                "source": self.name
            }
            
        except Exception as e:
            logger.error(f"[Yahoo] Error getting quote for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "source": self.name}
    
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
        
        try:
            # yfinance 支持批量下载
            tickers = yf.Tickers(" ".join(symbols))
            
            for symbol in symbols:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker:
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
                            if info is None:
                                info = ticker.info
                            return info.get(key)

                        price = pick_number(
                            fast_info.get("lastPrice"),
                            default=None,
                        )
                        if price is None:
                            price = pick_number(
                                info_value("regularMarketPrice"),
                                default=0,
                            )

                        results[symbol] = {
                            "symbol": symbol,
                            "price": price,
                            "change": pick_number_lazy(
                                lambda: fast_info.get("regularMarketChange"),
                                lambda: info_value("regularMarketChange"),
                            ),
                            "change_percent": pick_number_lazy(
                                lambda: fast_info.get("regularMarketChangePercent"),
                                lambda: info_value("regularMarketChangePercent"),
                            ),
                            "volume": pick_number_lazy(
                                lambda: fast_info.get("lastVolume"),
                                lambda: info_value("regularMarketVolume"),
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
                            # 批量报价优先追求速度，盘口数据留给详情按需补充。
                            "bid": None,
                            "ask": None,
                            "timestamp": datetime.now(),
                            "source": self.name
                        }
                    else:
                        results[symbol] = {"symbol": symbol, "error": "Ticker not found"}
                except Exception as e:
                    results[symbol] = {"symbol": symbol, "error": str(e)}
                    
        except Exception as e:
            # 降级到逐个获取
            logger.warning(f"[Yahoo] Batch fetch failed, falling back to individual: {e}")
            return super().get_multiple_quotes(symbols)
            
        return results
    
    def is_available(self) -> bool:
        """检查 Yahoo Finance 是否可用"""
        try:
            ticker = yf.Ticker("AAPL")
            data = ticker.history(period="1d")
            return not data.empty
        except Exception:
            return False
