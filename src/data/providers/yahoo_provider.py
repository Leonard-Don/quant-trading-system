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
            info = ticker.info
            
            return {
                "symbol": symbol,
                "price": info.get("regularMarketPrice", 0),
                "change": info.get("regularMarketChange", 0),
                "change_percent": info.get("regularMarketChangePercent", 0),
                "volume": info.get("regularMarketVolume", 0),
                "high": info.get("dayHigh", 0),
                "low": info.get("dayLow", 0),
                "open": info.get("regularMarketOpen", 0),
                "previous_close": info.get("previousClose", 0),
                "market_cap": info.get("marketCap", 0),
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
                        info = ticker.info
                        fast_info = getattr(ticker, "fast_info", {}) or {}

                        def pick_number(*values, default=0):
                            for value in values:
                                if value not in (None, ""):
                                    return value
                            return default

                        results[symbol] = {
                            "symbol": symbol,
                            "price": pick_number(
                                info.get("regularMarketPrice"),
                                fast_info.get("lastPrice"),
                            ),
                            "change": pick_number(
                                info.get("regularMarketChange"),
                                fast_info.get("regularMarketChange"),
                            ),
                            "change_percent": pick_number(
                                info.get("regularMarketChangePercent"),
                                fast_info.get("regularMarketChangePercent"),
                            ),
                            "volume": pick_number(
                                info.get("regularMarketVolume"),
                                fast_info.get("lastVolume"),
                            ),
                            "high": pick_number(
                                info.get("dayHigh"),
                                fast_info.get("dayHigh"),
                                default=None,
                            ),
                            "low": pick_number(
                                info.get("dayLow"),
                                fast_info.get("dayLow"),
                                default=None,
                            ),
                            "open": pick_number(
                                info.get("regularMarketOpen"),
                                fast_info.get("open"),
                                default=None,
                            ),
                            "previous_close": pick_number(
                                info.get("previousClose"),
                                fast_info.get("previousClose"),
                                default=None,
                            ),
                            "bid": pick_number(
                                info.get("bid"),
                                default=None,
                            ),
                            "ask": pick_number(
                                info.get("ask"),
                                default=None,
                            ),
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
