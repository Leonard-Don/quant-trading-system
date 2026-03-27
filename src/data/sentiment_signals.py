"""
情绪信号生成模块

将新闻情绪分析结果转换为可用于交易的信号
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from .news_fetcher import NewsFetcher, FinBERTAnalyzer, news_fetcher, finbert_analyzer

logger = logging.getLogger(__name__)


class SentimentSignalGenerator:
    """
    情绪信号生成器
    
    将新闻情绪分析转换为交易信号
    
    特点:
    - 基于 FinBERT 情绪分析
    - 时间加权衰减
    - 多维度情绪评分
    - 可配置阈值
    """
    
    def __init__(
        self,
        news_fetcher: Optional[NewsFetcher] = None,
        sentiment_analyzer: Optional[FinBERTAnalyzer] = None,
        bullish_threshold: float = 0.3,
        bearish_threshold: float = -0.3,
        decay_hours: float = 24.0
    ):
        """
        初始化情绪信号生成器
        
        Args:
            news_fetcher: 新闻获取器实例
            sentiment_analyzer: 情绪分析器实例
            bullish_threshold: 看涨阈值
            bearish_threshold: 看跌阈值
            decay_hours: 情绪衰减时间（小时）
        """
        self.news_fetcher = news_fetcher or globals()['news_fetcher']
        self.sentiment_analyzer = sentiment_analyzer or globals()['finbert_analyzer']
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold
        self.decay_hours = decay_hours
        
        # 情绪历史
        self.sentiment_history: Dict[str, List[Dict]] = {}
    
    def fetch_and_analyze(
        self,
        symbol: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        获取新闻并分析情绪
        
        Args:
            symbol: 股票代码
            limit: 新闻数量
            
        Returns:
            带情绪分析的新闻列表
        """
        try:
            # 获取新闻
            news_list = self.news_fetcher.get_news(symbol=symbol, limit=limit)
            
            if not news_list:
                logger.warning(f"未获取到 {symbol} 的新闻")
                return []
            
            # 分析每条新闻
            analyzed_news = []
            for news in news_list:
                # 分析标题和摘要
                title = news.get('title', '')
                summary = news.get('summary', '')
                text = f"{title}. {summary}" if summary else title
                
                sentiment_result = self.sentiment_analyzer.analyze(text)
                
                analyzed_item = {
                    **news,
                    'sentiment_score': sentiment_result['score'],
                    'sentiment_label': sentiment_result['label'],
                    'confidence': sentiment_result.get('confidence', 0.5)
                }
                analyzed_news.append(analyzed_item)
            
            # 保存到历史
            if symbol not in self.sentiment_history:
                self.sentiment_history[symbol] = []
            self.sentiment_history[symbol].extend(analyzed_news)
            
            # 保留最近 100 条
            self.sentiment_history[symbol] = self.sentiment_history[symbol][-100:]
            
            return analyzed_news
            
        except Exception as e:
            logger.error(f"新闻分析失败 {symbol}: {e}")
            return []
    
    def calculate_sentiment_score(
        self,
        symbol: str,
        use_decay: bool = True
    ) -> Dict:
        """
        计算综合情绪得分
        
        Args:
            symbol: 股票代码
            use_decay: 是否使用时间衰减
            
        Returns:
            情绪得分详情
        """
        history = self.sentiment_history.get(symbol, [])
        
        if not history:
            # 尝试获取新的新闻
            history = self.fetch_and_analyze(symbol)
        
        if not history:
            return {
                'symbol': symbol,
                'score': 0,
                'label': 'neutral',
                'signal': 0,
                'news_count': 0,
                'confidence': 0
            }
        
        now = datetime.now()
        weighted_scores = []
        total_weight = 0
        
        for item in history:
            score = item.get('sentiment_score', 0)
            confidence = item.get('confidence', 0.5)
            
            # 时间权重
            if use_decay:
                pub_time = item.get('published_time')
                if pub_time:
                    if isinstance(pub_time, str):
                        try:
                            pub_time = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                        except:
                            pub_time = now
                    
                    hours_ago = (now - pub_time.replace(tzinfo=None)).total_seconds() / 3600
                    time_weight = np.exp(-hours_ago / self.decay_hours)
                else:
                    time_weight = 0.5
            else:
                time_weight = 1.0
            
            weight = time_weight * confidence
            weighted_scores.append(score * weight)
            total_weight += weight
        
        # 计算加权平均
        if total_weight > 0:
            avg_score = sum(weighted_scores) / total_weight
        else:
            avg_score = 0
        
        # 生成信号
        if avg_score > self.bullish_threshold:
            signal = 1  # 买入信号
            label = 'positive'
        elif avg_score < self.bearish_threshold:
            signal = -1  # 卖出信号
            label = 'negative'
        else:
            signal = 0  # 持有
            label = 'neutral'
        
        return {
            'symbol': symbol,
            'score': round(avg_score, 4),
            'label': label,
            'signal': signal,
            'news_count': len(history),
            'confidence': round(min(1.0, len(history) / 10), 2),
            'timestamp': now.isoformat()
        }
    
    def generate_signals(
        self,
        symbols: List[str]
    ) -> pd.DataFrame:
        """
        批量生成情绪信号
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            情绪信号 DataFrame
        """
        results = []
        
        for symbol in symbols:
            # 先获取新闻
            self.fetch_and_analyze(symbol, limit=15)
            # 计算情绪
            sentiment = self.calculate_sentiment_score(symbol)
            results.append(sentiment)
        
        df = pd.DataFrame(results)
        df = df.sort_values('score', ascending=False)
        
        return df
    
    def get_trading_recommendation(
        self,
        symbol: str
    ) -> Dict:
        """
        获取交易建议
        
        Args:
            symbol: 股票代码
            
        Returns:
            交易建议
        """
        sentiment = self.calculate_sentiment_score(symbol)
        
        score = sentiment['score']
        signal = sentiment['signal']
        
        # 计算信号强度
        if signal == 1:
            strength = min(1.0, (score - self.bullish_threshold) / (1 - self.bullish_threshold))
            action = 'BUY'
            reason = '新闻情绪积极'
        elif signal == -1:
            strength = min(1.0, (self.bearish_threshold - score) / (1 + self.bearish_threshold))
            action = 'SELL'
            reason = '新闻情绪消极'
        else:
            strength = 0
            action = 'HOLD'
            reason = '新闻情绪中性'
        
        return {
            'symbol': symbol,
            'action': action,
            'strength': round(strength, 2),
            'reason': reason,
            'sentiment_score': sentiment['score'],
            'sentiment_label': sentiment['label'],
            'news_count': sentiment['news_count'],
            'confidence': sentiment['confidence'],
            'generated_at': datetime.now().isoformat()
        }
    
    def combine_with_technical(
        self,
        symbol: str,
        technical_signal: int,
        technical_weight: float = 0.6
    ) -> Dict:
        """
        结合技术分析信号
        
        Args:
            symbol: 股票代码
            technical_signal: 技术信号 (1=买, -1=卖, 0=持有)
            technical_weight: 技术分析权重
            
        Returns:
            综合信号
        """
        sentiment = self.calculate_sentiment_score(symbol)
        sentiment_weight = 1 - technical_weight
        
        # 加权综合
        combined_score = (
            technical_signal * technical_weight +
            sentiment['signal'] * sentiment_weight
        )
        
        # 确定最终信号
        if combined_score > 0.3:
            final_signal = 1
            action = 'BUY'
        elif combined_score < -0.3:
            final_signal = -1
            action = 'SELL'
        else:
            final_signal = 0
            action = 'HOLD'
        
        # 确定信号是否一致
        agreement = 'AGREE' if (
            (technical_signal > 0 and sentiment['signal'] > 0) or
            (technical_signal < 0 and sentiment['signal'] < 0) or
            (technical_signal == 0 and sentiment['signal'] == 0)
        ) else 'DISAGREE'
        
        return {
            'symbol': symbol,
            'combined_signal': final_signal,
            'combined_score': round(combined_score, 3),
            'action': action,
            'technical_signal': technical_signal,
            'sentiment_signal': sentiment['signal'],
            'agreement': agreement,
            'confidence': 'HIGH' if agreement == 'AGREE' else 'MEDIUM'
        }


class MarketSentimentIndex:
    """
    市场情绪指数
    
    聚合多只股票的情绪生成市场整体情绪指数
    """
    
    def __init__(self, signal_generator: Optional[SentimentSignalGenerator] = None):
        self.signal_generator = signal_generator or SentimentSignalGenerator()
        self.index_history: List[Dict] = []
    
    def calculate_index(
        self,
        symbols: List[str],
        weights: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        计算市场情绪指数
        
        Args:
            symbols: 股票代码列表
            weights: 权重字典（可选）
            
        Returns:
            市场情绪指数
        """
        signals = self.signal_generator.generate_signals(symbols)
        
        if weights is None:
            # 等权
            weights = {s: 1.0 / len(symbols) for s in symbols}
        
        # 计算加权情绪
        weighted_score = 0
        total_weight = 0
        
        for _, row in signals.iterrows():
            symbol = row['symbol']
            weight = weights.get(symbol, 0)
            weighted_score += row['score'] * weight
            total_weight += weight
        
        if total_weight > 0:
            index_score = weighted_score / total_weight
        else:
            index_score = 0
        
        # 标准化到 0-100
        index_value = (index_score + 1) * 50
        
        # 判断市场情绪状态
        if index_value > 65:
            status = 'VERY_BULLISH'
            description = '市场情绪极度乐观'
        elif index_value > 55:
            status = 'BULLISH'
            description = '市场情绪偏乐观'
        elif index_value > 45:
            status = 'NEUTRAL'
            description = '市场情绪中性'
        elif index_value > 35:
            status = 'BEARISH'
            description = '市场情绪偏悲观'
        else:
            status = 'VERY_BEARISH'
            description = '市场情绪极度悲观'
        
        result = {
            'index_value': round(index_value, 2),
            'raw_score': round(index_score, 4),
            'status': status,
            'description': description,
            'sample_size': len(signals),
            'bullish_count': len(signals[signals['signal'] == 1]),
            'bearish_count': len(signals[signals['signal'] == -1]),
            'neutral_count': len(signals[signals['signal'] == 0]),
            'timestamp': datetime.now().isoformat()
        }
        
        self.index_history.append(result)
        
        return result
    
    def get_trend(self, periods: int = 5) -> str:
        """获取情绪趋势"""
        if len(self.index_history) < 2:
            return 'INSUFFICIENT_DATA'
        
        recent = self.index_history[-periods:]
        values = [r['index_value'] for r in recent]
        
        if len(values) < 2:
            return 'INSUFFICIENT_DATA'
        
        trend = values[-1] - values[0]
        
        if trend > 5:
            return 'IMPROVING'
        elif trend < -5:
            return 'DETERIORATING'
        else:
            return 'STABLE'


# 全局实例
sentiment_signal_generator = SentimentSignalGenerator()
market_sentiment_index = MarketSentimentIndex()
