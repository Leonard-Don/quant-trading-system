"""
Alpha Vantage 数据提供器
使用 Alpha Vantage API 获取股票数据
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import time

from .base_provider import BaseDataProvider, DataProviderError

logger = logging.getLogger(__name__)


class AlphaVantageProvider(BaseDataProvider):
    """
    Alpha Vantage 数据提供器
    
    Alpha Vantage 提供免费的股票数据 API
    
    限制:
    - 免费 API: 25 次/天，5 次/分钟
    - 付费 API: 更高的调用限制
    
    特点:
    - 支持股票、ETF、外汇、加密货币
    - 数据质量高
    - 需要 API 密钥
    """
    
    name = "alphavantage"
    priority = 2
    rate_limit = 5  # 每分钟 5 次
    requires_api_key = True
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        super().__init__(api_key, config)
        
        if not self.api_key:
            logger.warning("[AlphaVantage] No API key provided. Get free key at: https://www.alphavantage.co/support/#api-key")
        
        self._last_request = 0
        self._min_interval = 12  # 秒，确保不超过 5次/分钟
    
    def _rate_limit_wait(self):
        """等待以遵守频率限制"""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()
    
    def _make_request(self, params: Dict[str, str]) -> Dict:
        """发起 API 请求"""
        if not self.api_key:
            raise DataProviderError("Alpha Vantage API key is required")
        
        params["apikey"] = self.api_key
        
        self._rate_limit_wait()
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # 检查 API 错误
            if "Error Message" in data:
                raise DataProviderError(f"API Error: {data['Error Message']}")
            if "Note" in data:
                raise DataProviderError(f"API Limit: {data['Note']}")
            
            return data
            
        except requests.RequestException as e:
            raise DataProviderError(f"Request failed: {e}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Alpha Vantage interval 映射:
        - 1m, 5m, 15m, 30m, 60m -> TIME_SERIES_INTRADAY
        - 1d -> TIME_SERIES_DAILY
        - 1wk -> TIME_SERIES_WEEKLY
        - 1mo -> TIME_SERIES_MONTHLY
        """
        try:
            # 确定函数类型
            if interval in ["1m", "5m", "15m", "30m", "60m"]:
                function = "TIME_SERIES_INTRADAY"
                av_interval = interval.replace("m", "min").replace("60min", "1hour")
                params = {
                    "function": function,
                    "symbol": symbol,
                    "interval": av_interval,
                    "outputsize": "full"
                }
                time_key = f"Time Series ({av_interval})"
            elif interval == "1wk":
                function = "TIME_SERIES_WEEKLY"
                params = {"function": function, "symbol": symbol}
                time_key = "Weekly Time Series"
            elif interval == "1mo":
                function = "TIME_SERIES_MONTHLY"
                params = {"function": function, "symbol": symbol}
                time_key = "Monthly Time Series"
            else:  # 默认日线
                function = "TIME_SERIES_DAILY"
                params = {
                    "function": function,
                    "symbol": symbol,
                    "outputsize": "full"
                }
                time_key = "Time Series (Daily)"
            
            data = self._make_request(params)
            
            if time_key not in data:
                logger.warning(f"[AlphaVantage] No data found for {symbol}")
                return pd.DataFrame()
            
            # 转换为 DataFrame
            df = pd.DataFrame.from_dict(data[time_key], orient="index")
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            
            # 重命名列
            column_mapping = {
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume"
            }
            df = df.rename(columns=column_mapping)
            
            # 转换数据类型
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype(int)
            
            # 过滤日期范围
            if start_date:
                df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]
            
            # 标准化
            df = self._standardize_dataframe(df)
            df.index.name = "date"
            
            logger.debug(f"[AlphaVantage] Fetched {len(df)} rows for {symbol}")
            return df
            
        except DataProviderError:
            raise
        except Exception as e:
            logger.error(f"[AlphaVantage] Error fetching {symbol}: {e}")
            raise DataProviderError(f"Failed to fetch data: {e}")
    
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """获取最新报价"""
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol
            }
            
            data = self._make_request(params)
            quote = data.get("Global Quote", {})
            
            if not quote:
                return {"symbol": symbol, "error": "No quote data", "source": self.name}
            
            return {
                "symbol": symbol,
                "price": float(quote.get("05. price", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": float(quote.get("10. change percent", "0%").replace("%", "")),
                "volume": int(quote.get("06. volume", 0)),
                "high": float(quote.get("03. high", 0)),
                "low": float(quote.get("04. low", 0)),
                "open": float(quote.get("02. open", 0)),
                "previous_close": float(quote.get("08. previous close", 0)),
                "bid": float(quote.get("11. bid", 0) or 0),
                "ask": float(quote.get("12. ask", 0) or 0),
                "timestamp": datetime.now(),
                "source": self.name
            }
            
        except DataProviderError:
            raise
        except Exception as e:
            logger.error(f"[AlphaVantage] Error getting quote for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "source": self.name}
    
    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """获取基本面数据"""
        try:
            params = {
                "function": "OVERVIEW",
                "symbol": symbol
            }
            
            data = self._make_request(params)
            
            if not data or "Symbol" not in data:
                return {"symbol": symbol, "error": "No fundamental data", "source": self.name}
            
            return {
                "symbol": symbol,
                "company_name": data.get("Name", ""),
                "sector": data.get("Sector", ""),
                "industry": data.get("Industry", ""),
                "market_cap": int(data.get("MarketCapitalization", 0)),
                "pe_ratio": float(data.get("TrailingPE", 0) or 0),
                "forward_pe": float(data.get("ForwardPE", 0) or 0),
                "peg_ratio": float(data.get("PEGRatio", 0) or 0),
                "price_to_book": float(data.get("PriceToBookRatio", 0) or 0),
                "dividend_yield": float(data.get("DividendYield", 0) or 0),
                "profit_margin": float(data.get("ProfitMargin", 0) or 0),
                "roe": float(data.get("ReturnOnEquityTTM", 0) or 0),
                "roa": float(data.get("ReturnOnAssetsTTM", 0) or 0),
                "revenue_growth": float(data.get("QuarterlyRevenueGrowthYOY", 0) or 0),
                "beta": float(data.get("Beta", 0) or 0),
                "52w_high": float(data.get("52WeekHigh", 0) or 0),
                "52w_low": float(data.get("52WeekLow", 0) or 0),
                "analyst_rating": data.get("AnalystTargetPrice", ""),
                "source": self.name
            }
            
        except DataProviderError:
            raise
        except Exception as e:
            logger.error(f"[AlphaVantage] Error getting fundamental data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "source": self.name}
    
    def is_available(self) -> bool:
        """检查 Alpha Vantage 是否可用"""
        if not self.api_key:
            return False
        
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": "IBM"
            }
            data = self._make_request(params)
            return "Global Quote" in data
        except Exception:
            return False
