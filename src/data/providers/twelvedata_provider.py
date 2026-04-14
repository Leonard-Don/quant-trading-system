"""
Twelve Data 数据提供器
使用 Twelve Data API 获取股票数据
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import time

from .base_provider import BaseDataProvider, DataProviderError

logger = logging.getLogger(__name__)


class TwelveDataProvider(BaseDataProvider):
    """
    Twelve Data 数据提供器
    
    Twelve Data 提供全球股票市场数据
    
    限制:
    - 免费 API: 800 次/天，8 次/分钟
    - 支持全球 50+ 交易所
    
    特点:
    - 实时和历史数据
    - 技术指标 API
    - 外汇和加密货币
    """
    
    name = "twelvedata"
    priority = 3
    rate_limit = 8  # 每分钟 8 次
    requires_api_key = True
    
    BASE_URL = "https://api.twelvedata.com"
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        super().__init__(api_key, config)
        
        if not self.api_key:
            logger.warning("[TwelveData] No API key provided. Get free key at: https://twelvedata.com/")
        
        self._last_request = 0
        self._min_interval = 8  # 秒，确保不超过 8次/分钟
    
    def _rate_limit_wait(self):
        """等待以遵守频率限制"""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()
    
    def _make_request(self, endpoint: str, params: Dict[str, str]) -> Dict:
        """发起 API 请求"""
        if not self.api_key:
            raise DataProviderError("Twelve Data API key is required")
        
        params["apikey"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"
        
        self._rate_limit_wait()
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # 检查 API 错误
            if data.get("status") == "error":
                raise DataProviderError(f"API Error: {data.get('message', 'Unknown error')}")
            
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
        
        Twelve Data interval 支持:
        1min, 5min, 15min, 30min, 45min, 1h, 2h, 4h, 1day, 1week, 1month
        """
        try:
            # 映射 interval
            interval_mapping = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "1h": "1h",
                "1d": "1day",
                "1wk": "1week",
                "1mo": "1month"
            }
            td_interval = interval_mapping.get(interval, "1day")
            
            params = {
                "symbol": symbol,
                "interval": td_interval,
                "outputsize": "5000"
            }
            
            if start_date:
                params["start_date"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["end_date"] = end_date.strftime("%Y-%m-%d")
            
            data = self._make_request("time_series", params)
            
            if "values" not in data:
                logger.warning(f"[TwelveData] No data found for {symbol}")
                return pd.DataFrame()
            
            # 转换为 DataFrame
            df = pd.DataFrame(data["values"])
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime")
            df = df.sort_index()
            
            # 重命名和转换类型
            df = df.rename(columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume"
            })
            
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
            
            # 标准化
            df = self._standardize_dataframe(df)
            df.index.name = "date"
            
            logger.debug(f"[TwelveData] Fetched {len(df)} rows for {symbol}")
            return df
            
        except DataProviderError:
            raise
        except Exception as e:
            logger.error(f"[TwelveData] Error fetching {symbol}: {e}")
            raise DataProviderError(f"Failed to fetch data: {e}")
    
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """获取最新报价"""
        try:
            params = {"symbol": symbol}
            data = self._make_request("quote", params)
            
            if "symbol" not in data:
                return {"symbol": symbol, "error": "No quote data", "source": self.name}
            
            return {
                "symbol": symbol,
                "price": float(data.get("close", 0)),
                "change": float(data.get("change", 0)),
                "change_percent": float(data.get("percent_change", 0)),
                "volume": int(data.get("volume", 0)),
                "high": float(data.get("high", 0)),
                "low": float(data.get("low", 0)),
                "open": float(data.get("open", 0)),
                "previous_close": float(data.get("previous_close", 0)),
                "bid": float(data.get("bid", 0) or 0),
                "ask": float(data.get("ask", 0) or 0),
                "timestamp": datetime.now(),
                "source": self.name
            }
            
        except DataProviderError:
            raise
        except Exception as e:
            logger.error(f"[TwelveData] Error getting quote for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "source": self.name}
    
    def is_available(self) -> bool:
        """检查 Twelve Data 是否可用"""
        if not self.api_key:
            return False
        
        try:
            params = {"symbol": "AAPL"}
            data = self._make_request("quote", params)
            return "symbol" in data
        except Exception:
            return False
