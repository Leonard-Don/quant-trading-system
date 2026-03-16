"""
情绪驱动交易策略

基于新闻情绪信号进行交易决策
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from ..strategy.strategies import BaseStrategy
from ..utils.performance import timing_decorator

logger = logging.getLogger(__name__)


class SentimentStrategy(BaseStrategy):
    """
    情绪驱动交易策略
    
    基于新闻情绪分数生成交易信号
    """
    
    def __init__(
        self,
        sentiment_threshold: float = 0.2,
        holding_period: int = 5,
        use_momentum_filter: bool = True,
        **kwargs
    ):
        """
        初始化情绪策略
        
        Args:
            sentiment_threshold: 情绪阈值，超过此值生成信号
            holding_period: 持仓周期（天）
            use_momentum_filter: 是否使用动量过滤器
        """
        super().__init__(
            name="SentimentStrategy",
            parameters={
                "sentiment_threshold": sentiment_threshold,
                "holding_period": holding_period,
                "use_momentum_filter": use_momentum_filter
            }
        )
        self.sentiment_threshold = sentiment_threshold
        self.holding_period = holding_period
        self.use_momentum_filter = use_momentum_filter
    
    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        
        Args:
            data: 必须包含 'sentiment_score' 列
            
        Returns:
            信号序列: 1=买入, -1=卖出, 0=持有
        """
        if 'sentiment_score' not in data.columns:
            logger.warning("数据中没有sentiment_score列，使用模拟情绪数据")
            data = self._simulate_sentiment(data)
        
        signals = pd.Series(index=data.index, data=0)
        sentiment = data['sentiment_score']
        
        # 基本情绪信号
        signals[sentiment > self.sentiment_threshold] = 1  # 积极情绪买入
        signals[sentiment < -self.sentiment_threshold] = -1  # 消极情绪卖出
        
        # 动量过滤器
        if self.use_momentum_filter and 'close' in data.columns:
            momentum = data['close'].pct_change(5)
            
            # 只在动量方向与情绪一致时交易
            bullish_momentum = momentum > 0
            bearish_momentum = momentum < 0
            
            # 过滤掉矛盾信号
            signals[(signals == 1) & bearish_momentum] = 0
            signals[(signals == -1) & bullish_momentum] = 0
        
        self.signals = signals
        return signals
    
    def _simulate_sentiment(self, data: pd.DataFrame) -> pd.DataFrame:
        """模拟情绪数据（用于演示）"""
        df = data.copy()
        
        # 基于价格变化模拟情绪
        returns = df['close'].pct_change()
        
        # 使用滚动收益率作为情绪代理
        sentiment = returns.rolling(3).mean() * 10
        sentiment = sentiment.clip(-1, 1)
        
        # 添加一些噪声
        noise = np.random.normal(0, 0.1, len(sentiment))
        sentiment = sentiment + noise
        sentiment = sentiment.clip(-1, 1)
        
        df['sentiment_score'] = sentiment.fillna(0)
        return df
    
    def generate_signals_with_news(
        self,
        price_data: pd.DataFrame,
        sentiment_data: pd.DataFrame
    ) -> pd.Series:
        """
        使用真实新闻情绪数据生成信号
        
        Args:
            price_data: 价格数据 (OHLCV)
            sentiment_data: 情绪数据，包含 date 和 sentiment_score
            
        Returns:
            交易信号
        """
        # 合并数据
        merged = price_data.copy()
        
        if 'date' in sentiment_data.columns:
            sentiment_data = sentiment_data.set_index('date')
        
        merged['sentiment_score'] = sentiment_data['sentiment_score'].reindex(merged.index).fillna(0)
        
        return self.generate_signals(merged)


class SentimentMomentumStrategy(BaseStrategy):
    """
    情绪动量策略
    
    结合情绪趋势和价格动量
    """
    
    def __init__(
        self,
        sentiment_ma_period: int = 5,
        price_ma_period: int = 10,
        sentiment_threshold: float = 0.15,
        **kwargs
    ):
        super().__init__(
            name="SentimentMomentum",
            parameters={
                "sentiment_ma_period": sentiment_ma_period,
                "price_ma_period": price_ma_period,
                "sentiment_threshold": sentiment_threshold
            }
        )
        self.sentiment_ma_period = sentiment_ma_period
        self.price_ma_period = price_ma_period
        self.sentiment_threshold = sentiment_threshold
    
    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成信号"""
        df = data.copy()
        
        if 'sentiment_score' not in df.columns:
            # 模拟情绪
            returns = df['close'].pct_change()
            df['sentiment_score'] = returns.rolling(3).mean() * 10
            df['sentiment_score'] = df['sentiment_score'].clip(-1, 1).fillna(0)
        
        # 计算情绪移动平均
        sentiment_ma = df['sentiment_score'].rolling(self.sentiment_ma_period).mean()
        sentiment_trend = sentiment_ma.diff()
        
        # 计算价格动量
        price_ma = df['close'].rolling(self.price_ma_period).mean()
        price_trend = df['close'] > price_ma
        
        signals = pd.Series(index=df.index, data=0)
        
        # 情绪改善 + 价格上涨趋势 = 买入
        bullish = (sentiment_trend > 0) & (sentiment_ma > self.sentiment_threshold) & price_trend
        signals[bullish] = 1
        
        # 情绪恶化 + 价格下跌趋势 = 卖出
        bearish = (sentiment_trend < 0) & (sentiment_ma < -self.sentiment_threshold) & ~price_trend
        signals[bearish] = -1
        
        self.signals = signals
        return signals


class ContrarianSentimentStrategy(BaseStrategy):
    """
    情绪反转策略
    
    在极端情绪时采取反向操作（逆向思维）
    """
    
    def __init__(
        self,
        extreme_bullish_threshold: float = 0.7,
        extreme_bearish_threshold: float = -0.7,
        confirmation_period: int = 3,
        **kwargs
    ):
        super().__init__(
            name="ContrarianSentiment",
            parameters={
                "extreme_bullish_threshold": extreme_bullish_threshold,
                "extreme_bearish_threshold": extreme_bearish_threshold,
                "confirmation_period": confirmation_period
            }
        )
        self.extreme_bullish = extreme_bullish_threshold
        self.extreme_bearish = extreme_bearish_threshold
        self.confirmation_period = confirmation_period
    
    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成反转信号"""
        df = data.copy()
        
        if 'sentiment_score' not in df.columns:
            returns = df['close'].pct_change()
            df['sentiment_score'] = returns.rolling(5).mean() * 15
            df['sentiment_score'] = df['sentiment_score'].clip(-1, 1).fillna(0)
        
        sentiment = df['sentiment_score']
        
        # 使用滚动窗口检测极端情绪
        rolling_sentiment = sentiment.rolling(self.confirmation_period).mean()
        
        signals = pd.Series(index=df.index, data=0)
        
        # 极端乐观时做空（可能见顶）
        extreme_bullish = rolling_sentiment > self.extreme_bullish
        signals[extreme_bullish] = -1
        
        # 极端悲观时做多（可能见底）
        extreme_bearish = rolling_sentiment < self.extreme_bearish
        signals[extreme_bearish] = 1
        
        self.signals = signals
        return signals


class SentimentAnalysisIntegrator:
    """
    情绪分析集成器
    
    将情绪数据与交易策略集成
    """
    
    def __init__(self):
        self.strategies = {
            'sentiment': SentimentStrategy,
            'sentiment_momentum': SentimentMomentumStrategy,
            'contrarian': ContrarianSentimentStrategy
        }
    
    def create_sentiment_series(
        self,
        news_data: List[Dict],
        date_range: pd.DatetimeIndex
    ) -> pd.Series:
        """
        从新闻数据创建情绪时间序列
        
        Args:
            news_data: 新闻数据列表
            date_range: 日期范围
            
        Returns:
            情绪分数序列
        """
        sentiment_by_date = {}
        
        for news in news_data:
            try:
                date_str = news.get('published_at', '')
                if date_str:
                    date = pd.to_datetime(date_str).date()
                    score = news.get('overall_sentiment_score', 0)
                    
                    if date not in sentiment_by_date:
                        sentiment_by_date[date] = []
                    sentiment_by_date[date].append(score)
            except:
                continue
        
        # 计算每日平均情绪
        daily_sentiment = {}
        for date, scores in sentiment_by_date.items():
            daily_sentiment[date] = np.mean(scores)
        
        # 创建时间序列
        sentiment_series = pd.Series(index=date_range, data=0.0)
        
        for date, score in daily_sentiment.items():
            if date in sentiment_series.index:
                sentiment_series[date] = score
        
        # 前向填充缺失值
        sentiment_series = sentiment_series.fillna(method='ffill').fillna(0)
        
        return sentiment_series
    
    def backtest_with_sentiment(
        self,
        price_data: pd.DataFrame,
        news_data: List[Dict],
        strategy_name: str = 'sentiment'
    ) -> Dict[str, Any]:
        """
        使用情绪数据进行回测
        """
        if strategy_name not in self.strategies:
            raise ValueError(f"未知策略: {strategy_name}")
        
        # 创建情绪序列
        sentiment_series = self.create_sentiment_series(news_data, price_data.index)
        
        # 合并数据
        data = price_data.copy()
        data['sentiment_score'] = sentiment_series
        
        # 创建策略并生成信号
        strategy_class = self.strategies[strategy_name]
        strategy = strategy_class()
        signals = strategy.generate_signals(data)
        
        return {
            'strategy': strategy_name,
            'signals': signals,
            'data': data
        }


# 全局实例
sentiment_integrator = SentimentAnalysisIntegrator()
