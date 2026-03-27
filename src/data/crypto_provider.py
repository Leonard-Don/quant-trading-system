"""
加密货币数据提供器

支持从主流交易所获取加密货币行情数据
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


class CryptoDataProvider:
    """
    加密货币数据提供器
    
    支持:
    - Binance API (免费)
    - CoinGecko API (免费)
    - 历史K线数据
    - 实时价格
    """
    
    # 热门加密货币列表
    POPULAR_CRYPTOS = [
        'BTC', 'ETH', 'BNB', 'XRP', 'ADA',
        'DOGE', 'SOL', 'DOT', 'MATIC', 'LTC'
    ]
    
    # 交易对后缀
    QUOTE_CURRENCY = 'USDT'
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_testnet: bool = False
    ):
        """
        初始化加密货币数据提供器
        
        Args:
            api_key: Binance API密钥（可选，用于更高频率限制）
            api_secret: Binance API密钥
            use_testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Binance API端点
        if use_testnet:
            self.base_url = "https://testnet.binance.vision/api/v3"
        else:
            self.base_url = "https://api.binance.com/api/v3"
        
        # CoinGecko备用端点
        self.coingecko_url = "https://api.coingecko.com/api/v3"
        
        # 缓存
        self._symbol_info_cache = {}
    
    def get_available_symbols(self) -> List[str]:
        """获取可用的交易对列表"""
        import requests
        
        try:
            response = requests.get(f"{self.base_url}/exchangeInfo", timeout=10)
            if response.status_code == 200:
                data = response.json()
                symbols = [
                    s['symbol'] for s in data['symbols']
                    if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT'
                ]
                return symbols
        except Exception as e:
            logger.error(f"获取交易对列表失败: {e}")
        
        # 返回默认列表
        return [f"{c}{self.QUOTE_CURRENCY}" for c in self.POPULAR_CRYPTOS]
    
    def get_historical_data(
        self,
        symbol: str,
        interval: str = '1d',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易对 (如 'BTCUSDT' 或 'BTC')
            interval: K线周期 ('1m', '5m', '15m', '1h', '4h', '1d', '1w')
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大数据条数
            
        Returns:
            包含OHLCV数据的DataFrame
        """
        import requests
        
        # 标准化symbol
        if not symbol.endswith('USDT'):
            symbol = f"{symbol}USDT"
        
        try:
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'limit': limit
            }
            
            if start_date:
                params['startTime'] = int(start_date.timestamp() * 1000)
            if end_date:
                params['endTime'] = int(end_date.timestamp() * 1000)
            
            response = requests.get(
                f"{self.base_url}/klines",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if not data:
                    logger.warning(f"没有获取到 {symbol} 的数据")
                    return pd.DataFrame()
                
                df = pd.DataFrame(data, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 
                    'taker_buy_base', 'taker_buy_quote', 'ignore'
                ])
                
                # 转换数据类型
                df['date'] = pd.to_datetime(df['open_time'], unit='ms')
                df['open'] = pd.to_numeric(df['open'])
                df['high'] = pd.to_numeric(df['high'])
                df['low'] = pd.to_numeric(df['low'])
                df['close'] = pd.to_numeric(df['close'])
                df['volume'] = pd.to_numeric(df['volume'])
                
                df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
                df.set_index('date', inplace=True)
                
                return df
            else:
                logger.error(f"API请求失败: {response.status_code} {response.text}")
                
        except Exception as e:
            logger.error(f"获取 {symbol} 历史数据失败: {e}")
        
        return pd.DataFrame()
    
    def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新价格"""
        import requests
        
        if not symbol.endswith('USDT'):
            symbol = f"{symbol}USDT"
        
        try:
            response = requests.get(
                f"{self.base_url}/ticker/24hr",
                params={'symbol': symbol.upper()},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'symbol': symbol,
                    'price': float(data['lastPrice']),
                    'price_change': float(data['priceChange']),
                    'price_change_percent': float(data['priceChangePercent']),
                    'high_24h': float(data['highPrice']),
                    'low_24h': float(data['lowPrice']),
                    'volume_24h': float(data['volume']),
                    'quote_volume_24h': float(data['quoteVolume']),
                    'timestamp': datetime.now().isoformat()
                }
        except Exception as e:
            logger.error(f"获取 {symbol} 最新价格失败: {e}")
        
        return None
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取多个币种价格"""
        results = {}
        for symbol in symbols:
            price_data = self.get_latest_price(symbol)
            if price_data:
                results[symbol] = price_data
        return results
    
    async def get_realtime_stream(
        self,
        symbols: List[str],
        callback: callable
    ):
        """
        订阅实时价格推送 (WebSocket)
        
        Args:
            symbols: 交易对列表
            callback: 回调函数 (symbol, price, timestamp) -> None
        """
        # 标准化symbols
        streams = [f"{s.lower()}usdt@trade" for s in symbols if not s.endswith('usdt')]
        
        ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url) as ws:
                while True:
                    msg = await ws.recv()
                    import json
                    data = json.loads(msg)
                    
                    if 'data' in data:
                        trade = data['data']
                        symbol = trade['s']
                        price = float(trade['p'])
                        timestamp = trade['T']
                        
                        await callback(symbol, price, timestamp)
                        
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
    
    def calculate_crypto_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算加密货币特有的技术指标
        """
        df = data.copy()
        
        # 波动率（24小时）
        df['volatility_24h'] = df['close'].pct_change().rolling(24).std() * np.sqrt(24)
        
        # 成交量变化率
        df['volume_change'] = df['volume'].pct_change()
        
        # 价格动量
        df['momentum_12'] = df['close'] / df['close'].shift(12) - 1
        df['momentum_24'] = df['close'] / df['close'].shift(24) - 1
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        return df


class CryptoStrategy:
    """
    加密货币专用策略
    """
    
    def __init__(self, provider: CryptoDataProvider):
        self.provider = provider
    
    def momentum_strategy(
        self,
        data: pd.DataFrame,
        lookback: int = 24,
        threshold: float = 0.05
    ) -> pd.Series:
        """
        动量策略
        
        Args:
            data: OHLCV数据
            lookback: 回看周期
            threshold: 动量阈值
            
        Returns:
            信号序列
        """
        momentum = data['close'] / data['close'].shift(lookback) - 1
        
        signals = pd.Series(index=data.index, data=0)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1
        
        return signals
    
    def volume_breakout_strategy(
        self,
        data: pd.DataFrame,
        volume_multiplier: float = 2.0,
        price_change_threshold: float = 0.02
    ) -> pd.Series:
        """
        成交量突破策略
        """
        avg_volume = data['volume'].rolling(20).mean()
        price_change = data['close'].pct_change()
        
        signals = pd.Series(index=data.index, data=0)
        
        # 放量上涨
        bullish = (data['volume'] > avg_volume * volume_multiplier) & (price_change > price_change_threshold)
        signals[bullish] = 1
        
        # 放量下跌
        bearish = (data['volume'] > avg_volume * volume_multiplier) & (price_change < -price_change_threshold)
        signals[bearish] = -1
        
        return signals


# 全局实例
crypto_provider = CryptoDataProvider()
