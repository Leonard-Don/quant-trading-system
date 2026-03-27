"""
新闻数据获取模块

支持从多个新闻源获取财经新闻
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)


class NewsFetcher:
    """
    新闻数据获取器
    
    支持:
    - Alpha Vantage News API
    - Yahoo Finance News (免费)
    - 自定义新闻源
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_duration: int = 300  # 5分钟缓存
    ):
        """
        初始化新闻获取器
        
        Args:
            api_key: Alpha Vantage API密钥（可选）
            cache_duration: 缓存时长（秒）
        """
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        self.cache_duration = cache_duration
        self._cache = {}
        self._cache_time = {}
        
        # API端点
        self.alpha_vantage_url = "https://www.alphavantage.co/query"
    
    def get_news(
        self,
        symbol: Optional[str] = None,
        topics: Optional[List[str]] = None,
        limit: int = 50,
        sort: str = 'LATEST'  # LATEST, EARLIEST, RELEVANCE
    ) -> List[Dict[str, Any]]:
        """
        获取新闻
        
        Args:
            symbol: 股票代码（可选）
            topics: 主题列表（如 ['technology', 'earnings']）
            limit: 返回数量限制
            sort: 排序方式
            
        Returns:
            新闻列表
        """
        cache_key = f"news_{symbol}_{topics}_{limit}"
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # 尝试多个数据源
        news = []
        
        # 1. 使用Alpha Vantage（如果有API密钥）
        if self.api_key:
            news = self._fetch_alpha_vantage_news(symbol, topics, limit, sort)
        
        # 2. 如果没有结果，使用模拟数据
        if not news:
            news = self._generate_sample_news(symbol, limit)
        
        # 缓存结果
        self._cache[cache_key] = news
        self._cache_time[cache_key] = datetime.now()
        
        return news
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache or key not in self._cache_time:
            return False
        
        elapsed = (datetime.now() - self._cache_time[key]).total_seconds()
        return elapsed < self.cache_duration
    
    def _fetch_alpha_vantage_news(
        self,
        symbol: Optional[str],
        topics: Optional[List[str]],
        limit: int,
        sort: str
    ) -> List[Dict[str, Any]]:
        """从Alpha Vantage获取新闻"""
        try:
            params = {
                'function': 'NEWS_SENTIMENT',
                'apikey': self.api_key,
                'limit': limit,
                'sort': sort
            }
            
            if symbol:
                params['tickers'] = symbol
            
            if topics:
                params['topics'] = ','.join(topics)
            
            response = requests.get(self.alpha_vantage_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'feed' in data:
                    return [self._parse_alpha_vantage_article(article) for article in data['feed']]
                    
        except Exception as e:
            logger.error(f"获取Alpha Vantage新闻失败: {e}")
        
        return []
    
    def _parse_alpha_vantage_article(self, article: Dict) -> Dict[str, Any]:
        """解析Alpha Vantage新闻文章"""
        # 提取相关股票的情绪分数
        ticker_sentiment = {}
        for ts in article.get('ticker_sentiment', []):
            ticker_sentiment[ts['ticker']] = {
                'relevance': float(ts.get('relevance_score', 0)),
                'sentiment_score': float(ts.get('ticker_sentiment_score', 0)),
                'sentiment_label': ts.get('ticker_sentiment_label', 'Neutral')
            }
        
        return {
            'title': article.get('title', ''),
            'summary': article.get('summary', ''),
            'source': article.get('source', ''),
            'url': article.get('url', ''),
            'published_at': article.get('time_published', ''),
            'authors': article.get('authors', []),
            'overall_sentiment_score': float(article.get('overall_sentiment_score', 0)),
            'overall_sentiment_label': article.get('overall_sentiment_label', 'Neutral'),
            'ticker_sentiment': ticker_sentiment,
            'topics': [t.get('topic', '') for t in article.get('topics', [])]
        }
    
    def _generate_sample_news(
        self,
        symbol: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """生成示例新闻数据（用于演示）"""
        import random
        
        sample_titles = [
            f"{symbol or 'Market'} Sees Strong Q4 Earnings Beat",
            f"Analysts Upgrade {symbol or 'Tech Stocks'} on Growth Outlook",
            f"{symbol or 'Markets'} Rally on Fed Rate Decision",
            f"New Product Launch Boosts {symbol or 'Company'} Stock",
            f"{symbol or 'Index'} Hits All-Time High Amid Optimism",
            f"Volatility Returns as {symbol or 'Markets'} React to Data",
            f"{symbol or 'Sector'} Faces Headwinds from Rising Costs",
            f"Investors Eye {symbol or 'Stocks'} Ahead of Earnings",
        ]
        
        sentiments = ['Bullish', 'Somewhat-Bullish', 'Neutral', 'Somewhat-Bearish', 'Bearish']
        sentiment_scores = [0.35, 0.15, 0.0, -0.15, -0.35]
        
        news = []
        for i in range(min(limit, len(sample_titles))):
            idx = random.randint(0, len(sentiments) - 1)
            news.append({
                'title': sample_titles[i],
                'summary': f"This is a sample news summary for {symbol or 'the market'}.",
                'source': random.choice(['Reuters', 'Bloomberg', 'CNBC', 'MarketWatch']),
                'url': '#',
                'published_at': (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(),
                'authors': ['Sample Author'],
                'overall_sentiment_score': sentiment_scores[idx] + random.uniform(-0.1, 0.1),
                'overall_sentiment_label': sentiments[idx],
                'ticker_sentiment': {symbol: {'sentiment_score': sentiment_scores[idx]}} if symbol else {},
                'topics': ['finance', 'markets']
            })
        
        return news
    
    def get_market_sentiment_summary(
        self,
        symbols: List[str]
    ) -> Dict[str, Any]:
        """
        获取多只股票的市场情绪汇总
        """
        results = {}
        
        for symbol in symbols:
            news = self.get_news(symbol=symbol, limit=10)
            
            if news:
                scores = [n['overall_sentiment_score'] for n in news]
                avg_sentiment = sum(scores) / len(scores)
                
                results[symbol] = {
                    'news_count': len(news),
                    'average_sentiment': round(avg_sentiment, 4),
                    'sentiment_label': self._score_to_label(avg_sentiment),
                    'latest_headline': news[0]['title'] if news else None
                }
            else:
                results[symbol] = {
                    'news_count': 0,
                    'average_sentiment': 0,
                    'sentiment_label': 'Neutral',
                    'latest_headline': None
                }
        
        return results
    
    def _score_to_label(self, score: float) -> str:
        """将情绪分数转换为标签"""
        if score >= 0.25:
            return 'Bullish'
        elif score >= 0.1:
            return 'Somewhat-Bullish'
        elif score <= -0.25:
            return 'Bearish'
        elif score <= -0.1:
            return 'Somewhat-Bearish'
        else:
            return 'Neutral'


class FinBERTAnalyzer:
    """
    FinBERT情绪分析器
    
    使用预训练的FinBERT模型分析金融文本情绪
    """
    
    def __init__(self, model_name: str = "ProsusAI/finbert"):
        """
        初始化FinBERT分析器
        
        Args:
            model_name: Hugging Face模型名称
        """
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self._loaded = False
    
    def _load_model(self):
        """延迟加载模型"""
        if self._loaded:
            return
        
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch
            
            logger.info(f"加载FinBERT模型: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model.eval()
            self._loaded = True
            logger.info("FinBERT模型加载完成")
            
        except ImportError:
            logger.warning("transformers库未安装，情绪分析将使用回退方法")
        except Exception as e:
            logger.error(f"加载FinBERT模型失败: {e}")
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        分析文本情绪
        
        Args:
            text: 待分析文本
            
        Returns:
            情绪分析结果
        """
        self._load_model()
        
        if not self._loaded:
            # 回退到简单的关键词分析
            return self._fallback_analyze(text)
        
        try:
            import torch
            
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.softmax(outputs.logits, dim=-1)
            
            labels = ['positive', 'negative', 'neutral']
            scores = predictions[0].tolist()
            
            result = dict(zip(labels, scores))
            
            # 计算综合分数 (-1 到 1)
            sentiment_score = result['positive'] - result['negative']
            
            return {
                'text': text[:100] + '...' if len(text) > 100 else text,
                'scores': result,
                'sentiment_score': round(sentiment_score, 4),
                'sentiment_label': self._get_label(sentiment_score),
                'confidence': max(scores)
            }
            
        except Exception as e:
            logger.error(f"FinBERT分析失败: {e}")
            return self._fallback_analyze(text)
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """批量分析"""
        return [self.analyze(text) for text in texts]
    
    def _fallback_analyze(self, text: str) -> Dict[str, Any]:
        """回退分析方法（基于关键词）"""
        text_lower = text.lower()
        
        positive_words = ['up', 'rise', 'gain', 'beat', 'strong', 'growth', 'bullish', 'profit', 'upgrade', 'rally']
        negative_words = ['down', 'fall', 'drop', 'miss', 'weak', 'loss', 'bearish', 'decline', 'downgrade', 'crash']
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            sentiment_score = 0
        else:
            sentiment_score = (pos_count - neg_count) / total
        
        return {
            'text': text[:100] + '...' if len(text) > 100 else text,
            'scores': {
                'positive': max(0, sentiment_score),
                'negative': max(0, -sentiment_score),
                'neutral': 1 - abs(sentiment_score)
            },
            'sentiment_score': round(sentiment_score, 4),
            'sentiment_label': self._get_label(sentiment_score),
            'confidence': 0.5,
            'method': 'keyword_fallback'
        }
    
    def _get_label(self, score: float) -> str:
        """获取情绪标签"""
        if score > 0.3:
            return 'Bullish'
        elif score > 0.1:
            return 'Somewhat-Bullish'
        elif score < -0.3:
            return 'Bearish'
        elif score < -0.1:
            return 'Somewhat-Bearish'
        else:
            return 'Neutral'


# 全局实例
news_fetcher = NewsFetcher()
finbert_analyzer = FinBERTAnalyzer()
