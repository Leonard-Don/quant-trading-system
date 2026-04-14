"""
数据提供器抽象基类
定义统一的数据获取接口
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataProviderError(Exception):
    """数据提供器异常"""
    pass


class BaseDataProvider(ABC):
    """
    数据提供器抽象基类
    
    所有数据源提供器必须继承此类并实现抽象方法
    
    Attributes:
        name: 数据源名称
        priority: 优先级（数值越小优先级越高）
        rate_limit: API调用频率限制（每分钟）
        requires_api_key: 是否需要API密钥
    """
    
    name: str = "base"
    priority: int = 100
    rate_limit: int = 60
    requires_api_key: bool = False
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        """
        初始化数据提供器
        
        Args:
            api_key: API密钥（部分数据源需要）
            config: 额外配置参数
        """
        self.api_key = api_key
        self.config = config or {}
        self._last_request_time = None
        self._request_count = 0
        
    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 数据间隔 (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)
            
        Returns:
            包含 OHLCV 数据的 DataFrame
            列名: open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """
        获取最新报价
        
        Args:
            symbol: 股票代码
            
        Returns:
            包含最新报价信息的字典:
            {
                "symbol": str,
                "price": float,
                "change": float,
                "change_percent": float,
                "volume": int,
                "timestamp": datetime
            }
        """
        pass
    
    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取基本面数据（可选实现）
        
        Args:
            symbol: 股票代码
            
        Returns:
            基本面数据字典
        """
        return {"symbol": symbol, "error": "Not implemented"}

    def get_order_book(self, symbol: str, levels: int = 10) -> Dict[str, Any]:
        """
        获取订单簿深度（可选实现）。

        默认返回空结果，具体 provider 可以覆盖为真实 Level 2 接口。
        """
        return {}

    def supports_capability(self, capability: str) -> bool:
        """
        返回 provider 是否声明支持某项扩展能力。
        """
        normalized = str(capability or "").strip().lower()
        if normalized in {"order_book", "orderbook", "level2", "market_depth"}:
            method = getattr(self, "get_order_book", None)
            base_method = BaseDataProvider.get_order_book
            if not callable(method):
                return False
            bound_func = getattr(method, "__func__", method)
            return bound_func is not base_method
        return False
    
    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量获取报价
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            股票代码到报价数据的映射
        """
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.get_latest_quote(symbol)
            except Exception as e:
                logger.error(f"Error fetching quote for {symbol}: {e}")
                results[symbol] = {"symbol": symbol, "error": str(e)}
        return results
    
    def is_available(self) -> bool:
        """
        检查数据源是否可用
        
        Returns:
            True 如果数据源可用
        """
        try:
            # 尝试获取一个常见股票的数据来测试
            result = self.get_latest_quote("AAPL")
            return "error" not in result
        except Exception:
            return False
    
    def get_provider_info(self) -> Dict[str, Any]:
        """
        获取提供器信息
        
        Returns:
            提供器元数据
        """
        return {
            "name": self.name,
            "priority": self.priority,
            "rate_limit": self.rate_limit,
            "requires_api_key": self.requires_api_key,
            "is_available": self.is_available(),
            "capabilities": {
                "historical_data": True,
                "latest_quote": True,
                "fundamental_data": callable(getattr(self, "get_fundamental_data", None)),
                "order_book": self.supports_capability("order_book"),
            },
        }
    
    def _check_rate_limit(self) -> bool:
        """
        检查是否超出API调用频率限制
        
        Returns:
            True 如果可以继续调用
        """
        # 简单的频率限制检查（实际使用中可以更精确）
        return True
    
    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化DataFrame格式
        
        确保列名统一为小写: open, high, low, close, volume
        
        Args:
            df: 原始DataFrame
            
        Returns:
            标准化后的DataFrame
        """
        if df.empty:
            return df
            
        # 统一列名为小写
        df.columns = df.columns.str.lower()
        
        # 确保必要的列存在
        required_columns = ["open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = 0
                
        # 添加收益率列
        if "returns" not in df.columns:
            df["returns"] = df["close"].pct_change()
            
        return df
