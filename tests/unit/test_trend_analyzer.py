"""
TrendAnalyzer趋势分析器单元测试
"""

import pytest
import pandas as pd
import numpy as np
from src.analytics.trend_analyzer import TrendAnalyzer


@pytest.fixture
def sample_ohlcv_data():
    """创建测试用的OHLCV数据"""
    np.random.seed(42)
    n = 100
    
    # 生成模拟价格数据
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    base_price = 100
    returns = np.random.randn(n) * 0.02  # 日收益率约2%
    close = base_price * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        'Open': close * (1 + np.random.randn(n) * 0.005),
        'High': close * (1 + np.abs(np.random.randn(n) * 0.015)),
        'Low': close * (1 - np.abs(np.random.randn(n) * 0.015)),
        'Close': close,
        'Volume': np.random.randint(1000000, 10000000, n)
    }, index=dates)
    
    return df


class TestTrendAnalyzer:
    """TrendAnalyzer测试类"""

    def test_initialization(self):
        """测试分析器初始化"""
        analyzer = TrendAnalyzer()
        assert analyzer is not None
        assert hasattr(analyzer, 'indicators')

    def test_analyze_trend_with_data(self, sample_ohlcv_data):
        """测试趋势分析"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        # 检查返回结构
        assert "trend" in result
        assert "score" in result
        assert "support_levels" in result
        assert "resistance_levels" in result
        assert "indicators" in result
        assert "momentum" in result
        assert "volatility" in result

    def test_analyze_trend_empty_data(self):
        """测试空数据处理"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(pd.DataFrame())
        
        assert result["trend"] == "unknown"
        assert result["score"] == 0

    def test_analyze_trend_insufficient_data(self):
        """测试数据不足的情况"""
        analyzer = TrendAnalyzer()
        # 只有10行数据，不足以进行完整分析（需要50行）
        small_data = pd.DataFrame({
            'open': [100] * 10,
            'high': [105] * 10,
            'low': [95] * 10,
            'close': [102] * 10,
            'volume': [1000000] * 10
        })
        
        result = analyzer.analyze_trend(small_data)
        assert result["trend"] == "unknown"

    def test_trend_direction_values(self, sample_ohlcv_data):
        """测试趋势方向的有效值"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        valid_trends = ["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish", "unknown"]
        assert result["trend"] in valid_trends

    def test_score_range(self, sample_ohlcv_data):
        """测试技术评分范围"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        assert 0 <= result["score"] <= 100

    def test_indicators_content(self, sample_ohlcv_data):
        """测试指标内容"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        indicators = result["indicators"]
        
        # 检查新增的指标
        assert "rsi" in indicators
        assert "macd" in indicators
        assert "macd_signal" in indicators
        assert "cci" in indicators
        assert "adx" in indicators
        assert "stoch_k" in indicators
        assert "stoch_d" in indicators
        assert "williams_r" in indicators

    def test_rsi_range(self, sample_ohlcv_data):
        """测试RSI范围"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        rsi = result["indicators"]["rsi"]
        assert 0 <= rsi <= 100

    def test_williams_r_range(self, sample_ohlcv_data):
        """测试Williams %R范围"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        williams_r = result["indicators"]["williams_r"]
        assert -100 <= williams_r <= 0

    def test_stochastic_range(self, sample_ohlcv_data):
        """测试Stochastic范围"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        stoch_k = result["indicators"]["stoch_k"]
        stoch_d = result["indicators"]["stoch_d"]
        
        assert 0 <= stoch_k <= 100
        assert 0 <= stoch_d <= 100

    def test_momentum_analysis(self, sample_ohlcv_data):
        """测试动量分析"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        momentum = result["momentum"]
        
        assert "status" in momentum
        assert "roc_5d" in momentum
        assert "roc_10d" in momentum
        assert "roc_20d" in momentum
        assert "williams_r" in momentum
        
        valid_statuses = ["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"]
        assert momentum["status"] in valid_statuses

    def test_volatility_analysis(self, sample_ohlcv_data):
        """测试波动率分析"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        volatility = result["volatility"]
        
        assert "level" in volatility
        assert "historical_volatility" in volatility
        assert "atr" in volatility
        assert "bollinger_width" in volatility
        
        valid_levels = ["low", "medium", "high"]
        assert volatility["level"] in valid_levels

    def test_support_resistance_levels(self, sample_ohlcv_data):
        """测试支撑阻力位识别"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        support_levels = result["support_levels"]
        resistance_levels = result["resistance_levels"]
        
        assert isinstance(support_levels, list)
        assert isinstance(resistance_levels, list)
        
        # 支撑位应该低于当前价格
        current_price = sample_ohlcv_data["Close"].iloc[-1]
        for level in support_levels:
            assert level < current_price
        
        # 阻力位应该高于当前价格
        for level in resistance_levels:
            assert level > current_price

    def test_multi_timeframe_analysis(self, sample_ohlcv_data):
        """测试多时间周期分析"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        mtf = result["multi_timeframe"]
        
        assert "short" in mtf
        assert "medium" in mtf
        assert "long" in mtf
        
        for timeframe, data in mtf.items():
            assert "period" in data
            assert "trend" in data
            assert "change_percent" in data

    def test_signal_strength(self, sample_ohlcv_data):
        """测试信号强度计算"""
        analyzer = TrendAnalyzer()
        result = analyzer.analyze_trend(sample_ohlcv_data)
        
        signal_strength = result["signal_strength"]
        
        assert "signal" in signal_strength
        assert "buy_strength" in signal_strength
        assert "sell_strength" in signal_strength
        assert "buy_indicators" in signal_strength
        assert "sell_indicators" in signal_strength
        
        valid_signals = ["strong_buy", "buy", "neutral", "sell", "strong_sell"]
        assert signal_strength["signal"] in valid_signals
        
        assert 0 <= signal_strength["buy_strength"] <= 100
        assert 0 <= signal_strength["sell_strength"] <= 100
