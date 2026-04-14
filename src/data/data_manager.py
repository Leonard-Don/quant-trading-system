"""
Data module for fetching and managing market data
支持多数据源：Yahoo Finance、Alpha Vantage、Twelve Data
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import threading
from ..utils.performance import timing_decorator
from ..utils.cache import CacheManager

# 导入数据提供器
from .providers import DataProviderFactory, BaseDataProvider, DataProviderError
from .alternative.alt_data_manager import AltDataManager

logger = logging.getLogger(__name__)


class DataManager:
    """
    Enhanced data manager for fetching and processing market data
    
    支持多数据源（Yahoo Finance、Alpha Vantage、Twelve Data）和故障转移
    
    Args:
        cache_size: 缓存大小
        data_source_config: 数据源配置
        use_provider_factory: 是否使用多数据源工厂
    """

    def __init__(
        self, 
        cache_size: int = 100,
        data_source_config: Dict[str, Any] = None,
        use_provider_factory: bool = True
    ):
        # 使用统一的CacheManager，仅内存模式 (因为DataFrame不适合JSON序列化)
        self.cache = CacheManager(
            max_memory_items=cache_size,
            use_disk=False, 
            default_ttl=3600  # 1 hour default
        )
        self.cache_size = cache_size
        self.executor = ThreadPoolExecutor(max_workers=10)
        self._cache_key_template = "{symbol}_{start_date}_{end_date}_{interval}"
        self._inflight_requests: Dict[str, threading.Event] = {}
        self._inflight_lock = threading.RLock()
        
        # 多数据源支持
        self.use_provider_factory = use_provider_factory
        if use_provider_factory:
            self.provider_factory = DataProviderFactory(data_source_config)
            logger.info(f"DataManager initialized with providers: {list(self.provider_factory.providers.keys())}")
        else:
            self.provider_factory = None
        self.alt_data_manager = AltDataManager(data_source_config or {})
    
    def set_data_source(self, source: str) -> bool:
        """
        设置默认数据源
        
        Args:
            source: 数据源名称 ('yahoo', 'alphavantage', 'twelvedata')
            
        Returns:
            是否设置成功
        """
        if self.provider_factory and source in self.provider_factory.providers:
            self.provider_factory.config["default"] = source
            logger.info(f"Default data source set to: {source}")
            return True
        return False
    
    def get_available_sources(self) -> List[Dict[str, Any]]:
        """获取所有可用的数据源信息"""
        if self.provider_factory:
            return self.provider_factory.get_available_providers()
        return [{"name": "yahoo", "is_available": True}]
    
    def check_sources_status(self) -> Dict[str, bool]:
        """检查所有数据源的可用性"""
        if self.provider_factory:
            return self.provider_factory.check_all_providers()
        return {"yahoo": True}


    @timing_decorator
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
        period: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Fetch historical market data

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_date: Start date for data
            end_date: End date for data
            interval: Data interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)
            period: Data period (e.g., '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')

        Returns:
            DataFrame with OHLCV data
        """
        # If period is not provided, use existing fallback logic
        # 根据 interval 动态设置默认的数据获取时间范围
        if not period:
            if start_date is None:
                # 根据周期类型设置合适的历史数据范围
                if interval in ["1mo", "1M"]:
                    # 月线需要更长的历史数据 (5年)
                    start_date = datetime.now() - timedelta(days=365 * 5)
                elif interval in ["1wk", "1W"]:
                    # 周线需要更长的历史数据 (2年)
                    start_date = datetime.now() - timedelta(days=365 * 2)
                else:
                    # 日线及更短周期使用1年
                    start_date = datetime.now() - timedelta(days=365)
            if end_date is None:
                end_date = datetime.now()
        
        # Consistent cache key
        start_str = start_date.strftime("%Y-%m-%d") if start_date else "None"
        end_str = end_date.strftime("%Y-%m-%d") if end_date else "None"
        period_str = period if period else "None"
        
        cache_key = self._cache_key_template.format(
            symbol=symbol, start_date=start_str, end_date=end_str, interval=interval
        ) + f"_{period_str}"

        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"Returning cached data for {symbol}")
            return cached_data

        wait_event: Optional[threading.Event] = None
        owns_fetch = False
        with self._inflight_lock:
            wait_event = self._inflight_requests.get(cache_key)
            if wait_event is None:
                wait_event = threading.Event()
                self._inflight_requests[cache_key] = wait_event
                owns_fetch = True

        if not owns_fetch and wait_event is not None:
            wait_event.wait(timeout=15)
            cached_after_wait = self.cache.get(cache_key)
            if cached_after_wait is not None:
                logger.debug(f"Returning in-flight cached data for {symbol}")
                return cached_after_wait

        try:
            # Fetch from Yahoo Finance
            ticker = yf.Ticker(symbol)
            
            if period:
                data = ticker.history(period=period, interval=interval)
            else:
                data = ticker.history(start=start_date, end=end_date, interval=interval)

            if data.empty:
                logger.warning(f"No data found for {symbol}")
                return pd.DataFrame()

            # Clean and standardize column names
            data.columns = data.columns.str.lower()
            data.index.name = "date"

            # Add returns
            data["returns"] = data["close"].pct_change()

            # Cache the data
            self.cache.set(cache_key, data)

            logger.info(f"Fetched {len(data)} rows for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
            # Return empty DataFrame with proper structure
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        finally:
            if owns_fetch and wait_event is not None:
                with self._inflight_lock:
                    self._inflight_requests.pop(cache_key, None)
                wait_event.set()

    def get_cross_market_historical_data(
        self,
        symbol: str,
        asset_class: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """
        Fetch cross-market data with asset-class aware provider routing.

        Returns:
            {
                "data": DataFrame,
                "provider": str,
                "asset_class": str,
                "symbol": str
            }
        """
        normalized_asset_class = str(asset_class or "").strip().upper()
        cache_key = f"cross_market::{symbol}::{normalized_asset_class}::{start_date}::{end_date}::{interval}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        provider_name = ""
        data = pd.DataFrame()

        try:
            if self.provider_factory:
                data, provider_name = self.provider_factory.get_cross_market_historical_data(
                    symbol=symbol,
                    asset_class=normalized_asset_class,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                )

            if data.empty:
                data = self.get_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                )
                provider_name = provider_name or "yahoo_legacy"
        except Exception as exc:
            logger.warning(
                "Asset-class aware fetch failed for %s (%s), falling back to legacy path: %s",
                symbol,
                normalized_asset_class,
                exc,
            )
            data = self.get_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
            )
            provider_name = provider_name or "yahoo_legacy"

        result = {
            "data": data,
            "provider": provider_name or "unknown",
            "asset_class": normalized_asset_class,
            "symbol": symbol,
        }
        self.cache.set(cache_key, result)
        return result

    def get_multiple_stocks(
        self,
        symbols: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple stocks using concurrent execution

        Args:
            symbols: List of stock symbols
            start_date: Start date for data
            end_date: End date for data

        Returns:
            Dictionary with symbol as key and DataFrame as value
        """
        from concurrent.futures import as_completed
        
        data = {}
        
        # 限制并发数量，避免过多请求
        max_workers = min(len(symbols), 10)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_symbol = {
                executor.submit(
                    self.get_historical_data, symbol, start_date, end_date
                ): symbol
                for symbol in symbols
            }
            
            # 收集结果
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    df = future.result()
                    if not df.empty:
                        data[symbol] = df
                except Exception as e:
                    logger.error(f"Error fetching data for {symbol}: {e}")

        logger.info(f"Fetched data for {len(data)}/{len(symbols)} symbols concurrently")
        return data

    def get_latest_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest price information for a symbol

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with latest price info
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "price": info.get("regularMarketPrice", 0),
                "change": info.get("regularMarketChange", 0),
                "change_percent": info.get("regularMarketChangePercent", 0),
                "volume": info.get("regularMarketVolume", 0),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting latest price for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def get_latest_prices(self, symbols: List[str]) -> Dict[str, Any]:
        """
        批量获取最新价格（并发执行）

        Args:
            symbols: 股票代码列表

        Returns:
            Dictionary with symbol as key and price info as value
        """
        from concurrent.futures import as_completed

        results = {}
        # 限制并发数量
        max_workers = min(len(symbols), 20)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.get_latest_price, symbol): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    data = future.result()
                    if "error" not in data:
                        results[symbol] = data
                except Exception as e:
                    logger.error(f"Error fetching latest price for {symbol}: {e}")

        return results



    @timing_decorator
    def get_market_indicators(self) -> Dict[str, Any]:
        """
        获取市场指标（VIX、美元指数等）- 优化版
        支持缓存和并发获取

        Returns:
            市场指标字典
        """
        cache_key = "market_indicators_v1"
        cached_data = self.cache.get(cache_key)
        
        if cached_data:
            return cached_data

        indicators = {}
        
        # 定义获取单个指标的函数
        def fetch_single_indicator(name: str, symbol: str) -> tuple:
            try:
                ticker = yf.Ticker(symbol)
                # 获取最近2天数据以确保有数据 (有时当天数据未出)
                hist = ticker.history(period="5d") 
                if not hist.empty:
                    return name, hist["Close"].iloc[-1]
            except Exception as e:
                logger.warning(f"Failed to fetch {name} ({symbol}): {e}")
            return name, None

        # 需要获取的指标列表
        targets = [
            ("vix", "^VIX"),
            ("dxy", "DX-Y.NYB"),
            ("10y_yield", "^TNX"),
            ("gold", "GC=F"),
            ("oil", "CL=F"),
            ("sp500", "^GSPC")
        ]
        
        try:
            # 并发获取
            with ThreadPoolExecutor(max_workers=min(len(targets), 10)) as executor:
                futures = {
                    executor.submit(fetch_single_indicator, name, symbol): name 
                    for name, symbol in targets
                }
                
                from concurrent.futures import as_completed
                for future in as_completed(futures):
                    name, value = future.result()
                    if value is not None:
                        indicators[name] = round(float(value), 2)
            
            # 只有当成功获取大部分数据时才缓存 (避免缓存空值)
            if len(indicators) >= 3:
                self.cache.set(cache_key, indicators, ttl=3600)  # 缓存1小时
                
        except Exception as e:
            logger.error(f"Error fetching market indicators: {e}", exc_info=True)

        return indicators

    async def fetch_data_async(
        self, symbol: str, session: aiohttp.ClientSession
    ) -> pd.DataFrame:
        """
        异步获取数据

        Args:
            symbol: 股票代码
            session: aiohttp会话

        Returns:
            股票数据
        """
        try:
            ticker = yf.Ticker(symbol)
            data = await asyncio.get_event_loop().run_in_executor(
                self.executor, ticker.history, "1y"
            )
            data.columns = data.columns.str.lower()
            return data
        except Exception as e:
            logger.error(f"Error fetching async data for {symbol}: {e}")
            return pd.DataFrame()

    async def get_multiple_stocks_async(
        self, symbols: List[str]
    ) -> Dict[str, pd.DataFrame]:
        """
        异步获取多只股票数据

        Args:
            symbols: 股票代码列表

        Returns:
            股票数据字典
        """
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_data_async(symbol, session) for symbol in symbols]
            results = await asyncio.gather(*tasks)

        return {
            symbol: data for symbol, data in zip(symbols, results) if not data.empty
        }

    def get_sector_data(self, sector: str) -> pd.DataFrame:
        """
        获取板块数据

        Args:
            sector: 板块名称 (Technology, Healthcare, Finance等)

        Returns:
            板块内股票数据
        """
        sector_tickers = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC"],
            "Healthcare": ["JNJ", "PFE", "UNH", "CVS", "ABBV", "MRK", "TMO"],
            "Finance": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "MPC", "PSX", "VLO"],
            "Consumer": ["AMZN", "TSLA", "WMT", "HD", "NKE", "MCD", "SBUX"],
        }

        if sector not in sector_tickers:
            logger.warning(f"Unknown sector: {sector}")
            return pd.DataFrame()

        stocks_data = self.get_multiple_stocks(sector_tickers[sector])

        # 计算板块平均表现
        sector_df = pd.DataFrame()
        for symbol, data in stocks_data.items():
            if sector_df.empty:
                sector_df = data[["close"]].rename(columns={"close": symbol})
            else:
                sector_df[symbol] = data["close"]

        # 添加板块平均值
        sector_df["sector_avg"] = sector_df.mean(axis=1)
        sector_df["sector_returns"] = sector_df["sector_avg"].pct_change()

        return sector_df

    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取基本面数据

        Args:
            symbol: 股票代码

        Returns:
            基本面数据字典
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            fundamentals = {
                "symbol": symbol,
                "company_name": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap", 0),
                "enterprise_value": info.get("enterpriseValue", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "forward_pe": info.get("forwardPE", 0),
                "peg_ratio": info.get("pegRatio", 0),
                "price_to_book": info.get("priceToBook", 0),
                "price_to_sales": info.get("priceToSalesTrailing12Months", 0),
                "enterprise_to_ebitda": info.get("enterpriseToEbitda", 0),
                "enterprise_to_revenue": info.get("enterpriseToRevenue", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "profit_margin": info.get("profitMargins", 0),
                "operating_margin": info.get("operatingMargins", 0),
                "roe": info.get("returnOnEquity", 0),
                "roa": info.get("returnOnAssets", 0),
                "revenue_growth": info.get("revenueGrowth", 0),
                "earnings_growth": info.get("earningsGrowth", 0),
                "revenue": info.get("totalRevenue", 0),
                "ebitda": info.get("ebitda", 0),
                "free_cash_flow": info.get("freeCashflow", 0),
                "operating_cash_flow": info.get("operatingCashflow", 0),
                "capital_expenditure": info.get("capitalExpenditures", 0),
                "debt_to_equity": info.get("debtToEquity", 0),
                "total_debt": info.get("totalDebt", 0),
                "total_cash": info.get("totalCash", 0),
                "current_ratio": info.get("currentRatio", 0),
                "quick_ratio": info.get("quickRatio", 0),
                "current_assets": info.get("totalCurrentAssets", 0),
                "current_liabilities": info.get("totalCurrentLiabilities", 0),
                "shares_outstanding": info.get("sharesOutstanding", 0),
                "beta": info.get("beta", 0),
                "current_price": info.get("currentPrice", 0),
                "regular_market_price": info.get("regularMarketPrice", 0),
                "previous_close": info.get("previousClose", 0),
                "52w_high": info.get("fiftyTwoWeekHigh", 0),
                "52w_low": info.get("fiftyTwoWeekLow", 0),
                "analyst_rating": info.get("recommendationKey", ""),
                "target_price": info.get("targetMeanPrice", 0),
            }

            if not fundamentals.get("enterprise_to_revenue"):
                enterprise_value = float(fundamentals.get("enterprise_value") or 0)
                revenue = float(fundamentals.get("revenue") or 0)
                if enterprise_value > 0 and revenue > 0:
                    fundamentals["enterprise_to_revenue"] = enterprise_value / revenue

            if not fundamentals.get("free_cash_flow"):
                operating_cash_flow = float(fundamentals.get("operating_cash_flow") or 0)
                capital_expenditure = abs(float(fundamentals.get("capital_expenditure") or 0))
                if operating_cash_flow > 0 and capital_expenditure > 0:
                    fundamentals["free_cash_flow"] = operating_cash_flow - capital_expenditure

            return fundamentals

        except Exception as e:
            logger.error(f"Error fetching fundamental data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def screen_stocks(self, criteria: Dict[str, Any]) -> List[str]:
        """
        股票筛选

        Args:
            criteria: 筛选条件
                - min_market_cap: 最小市值
                - max_pe: 最大市盈率
                - min_volume: 最小成交量
                - sector: 板块

        Returns:
            符合条件的股票列表
        """
        # 这里使用示例股票列表，实际应用中可以连接到更完整的数据源
        candidates = [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "META",
            "TSLA",
            "NVDA",
            "JPM",
            "JNJ",
            "V",
            "PG",
            "UNH",
            "HD",
            "MA",
            "DIS",
        ]

        filtered_stocks = []

        for symbol in candidates:
            try:
                fundamentals = self.get_fundamental_data(symbol)

                # 应用筛选条件
                if (
                    criteria.get("min_market_cap")
                    and fundamentals.get("market_cap", 0) < criteria["min_market_cap"]
                ):
                    continue

                if (
                    criteria.get("max_pe")
                    and fundamentals.get("pe_ratio", float("inf")) > criteria["max_pe"]
                ):
                    continue

                if (
                    criteria.get("sector")
                    and fundamentals.get("sector") != criteria["sector"]
                ):
                    continue

                # 检查成交量
                if criteria.get("min_volume"):
                    data = self.get_historical_data(
                        symbol, datetime.now() - timedelta(days=5), datetime.now()
                    )
                    if (
                        not data.empty
                        and data["volume"].mean() < criteria["min_volume"]
                    ):
                        continue

                filtered_stocks.append(symbol)

            except Exception as e:
                logger.error(f"Error screening {symbol}: {e}")
                continue

        return filtered_stocks

    def get_stock_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Alias for get_historical_data for API consistency

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_date: Start date string (e.g., '2024-01-01')
            end_date: End date string (e.g., '2024-12-31')
            interval: Data interval

        Returns:
            DataFrame with OHLCV data
        """
        # Convert string dates to datetime objects if provided
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        return self.get_historical_data(symbol, start_dt, end_dt, interval)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return {
            "cache_size": len(self.cache.memory_cache),
            "max_cache_size": self.cache.max_memory_items,
            "cache_utilization": len(self.cache.memory_cache) / self.cache.max_memory_items * 100,
        }

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Cache cleared")

    def get_incremental_update(
        self,
        symbol: str,
        last_date: Optional[datetime] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        获取增量数据更新（只获取新数据）
        
        Args:
            symbol: 股票代码
            last_date: 上次更新的最后日期，如果为None则获取最近30天
            interval: 数据间隔
            
        Returns:
            新增的数据
        """
        if last_date is None:
            # 如果没有上次日期，默认获取最近30天
            start_date = datetime.now() - timedelta(days=30)
        else:
            # 从上次日期的下一天开始
            start_date = last_date + timedelta(days=1)
        
        end_date = datetime.now()
        
        # 如果开始日期已经是今天或之后，没有新数据
        if start_date.date() >= end_date.date():
            logger.debug(f"No new data needed for {symbol}")
            return pd.DataFrame()
        
        return self.get_historical_data(symbol, start_date, end_date, interval)

    def update_cached_data(
        self,
        symbol: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        智能更新缓存数据（只追加新数据）
        
        Args:
            symbol: 股票代码
            interval: 数据间隔
            
        Returns:
            更新后的完整数据
        """
        # 构建缓存键
        cache_key = f"{symbol}_incremental_{interval}"
        
        # 获取现有缓存数据
        existing_data = self.cache.get(cache_key)
        
        if existing_data is not None and not existing_data.empty:
            # 获取最后日期
            last_date = existing_data.index[-1]
            if isinstance(last_date, str):
                last_date = datetime.fromisoformat(last_date)
            elif hasattr(last_date, 'to_pydatetime'):
                last_date = last_date.to_pydatetime()
            
            # 获取增量数据
            new_data = self.get_incremental_update(symbol, last_date, interval)
            
            if not new_data.empty:
                # 合并数据
                updated_data = pd.concat([existing_data, new_data])
                # 去重（按日期）
                updated_data = updated_data[~updated_data.index.duplicated(keep='last')]
                updated_data = updated_data.sort_index()
                
                # 更新缓存
                self.cache.set(cache_key, updated_data)
                logger.info(f"Updated cache for {symbol}: added {len(new_data)} rows")
                return updated_data
            else:
                return existing_data
        else:
            # 没有缓存，获取完整数据
            full_data = self.get_historical_data(symbol)
            self.cache.set(cache_key, full_data)
            return full_data

    def calculate_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算常用技术指标
        
        Args:
            data: 包含 OHLCV 数据的 DataFrame (列名应为小写)
            
        Returns:
            包含技术指标的 DataFrame
        """
        if data.empty:
            return data
            
        df = data.copy()
        # 确保列名为小写以增加兼容性
        df.columns = df.columns.str.lower()
        
        # 提取收盘价
        if 'close' not in df.columns:
            logger.warning("Data must contain 'close' column to calculate indicators")
            return df
            
        close = df['close']
        
        # 1. 移动平均线 (SMA)
        df['sma_20'] = close.rolling(window=20).mean()
        df['sma_50'] = close.rolling(window=50).mean()
        
        # 2. 相对强弱指数 (RSI)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. 指数平滑异同移动平均线 (MACD)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 4. 布林带 (Bollinger Bands)
        sma = close.rolling(window=20).mean()
        std = close.rolling(window=20).std()
        df['bb_upper'] = sma + (std * 2)
        df['bb_lower'] = sma - (std * 2)
        df['bb_middle'] = sma
        
        return df

    def get_alt_signals(
        self,
        category: Optional[str] = None,
        timeframe: str = "7d",
        refresh_if_empty: bool = False,
    ) -> Dict[str, Any]:
        """获取另类数据与信号快照。"""
        return self.alt_data_manager.get_alt_signals(
            category=category,
            timeframe=timeframe,
            refresh_if_empty=refresh_if_empty,
        )

    def get_alt_dashboard_snapshot(self, refresh: bool = False) -> Dict[str, Any]:
        """获取另类数据作战看板快照。"""
        return self.alt_data_manager.get_dashboard_snapshot(refresh=refresh)
