"""
共用特征工程模块
提供统一的技术指标计算和特征准备功能，供多个预测器共用
"""
import pandas as pd
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """统一的特征工程类"""
    
    @staticmethod
    def prepare_features(
        df: pd.DataFrame, 
        include_volume: bool = True,
        feature_periods: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        准备机器学习特征
        
        Args:
            df: 包含 OHLCV 数据的 DataFrame (需要 'close', 'high', 'low', 'volume' 列)
            include_volume: 是否包含成交量特征
            feature_periods: 计算移动均线的周期列表，默认 [5, 10, 20, 50]
            
        Returns:
            带有技术指标特征的 DataFrame
        """
        if feature_periods is None:
            feature_periods = [5, 10, 20, 50]
            
        features = df.copy()
        
        # 确保列名为小写
        features.columns = features.columns.str.lower()
        
        # 基础价格特征
        features['returns'] = features['close'].pct_change()
        features['log_returns'] = np.log(features['close'] / features['close'].shift(1))
        
        # 价格变动
        features['price_change'] = features['close'].diff()
        features['high_low_range'] = features['high'] - features['low']
        features['close_open_range'] = features['close'] - features['open'] if 'open' in features.columns else 0
        
        # 移动均线
        for period in feature_periods:
            features[f'sma_{period}'] = features['close'].rolling(period).mean()
            features[f'ema_{period}'] = features['close'].ewm(span=period, adjust=False).mean()
            
            # 价格相对于均线的位置
            features[f'price_sma_{period}_ratio'] = features['close'] / features[f'sma_{period}']
        
        # RSI
        features['rsi_14'] = FeatureEngineer._calculate_rsi(features['close'], 14)
        features['rsi_7'] = FeatureEngineer._calculate_rsi(features['close'], 7)
        
        # MACD
        exp12 = features['close'].ewm(span=12, adjust=False).mean()
        exp26 = features['close'].ewm(span=26, adjust=False).mean()
        features['macd'] = exp12 - exp26
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_histogram'] = features['macd'] - features['macd_signal']
        
        # 布林带
        features['bb_middle'] = features['close'].rolling(20).mean()
        bb_std = features['close'].rolling(20).std()
        features['bb_upper'] = features['bb_middle'] + (bb_std * 2)
        features['bb_lower'] = features['bb_middle'] - (bb_std * 2)
        features['bb_width'] = (features['bb_upper'] - features['bb_lower']) / features['bb_middle']
        features['bb_position'] = (features['close'] - features['bb_lower']) / (features['bb_upper'] - features['bb_lower'])
        
        # 波动率
        features['volatility_20'] = features['returns'].rolling(20).std()
        features['volatility_10'] = features['returns'].rolling(10).std()
        
        # ATR (Average True Range)
        features['atr_14'] = FeatureEngineer._calculate_atr(features, 14)
        
        # 动量指标
        features['momentum_5'] = features['close'].pct_change(5)
        features['momentum_10'] = features['close'].pct_change(10)
        features['momentum_20'] = features['close'].pct_change(20)
        
        # 成交量特征
        if include_volume and 'volume' in features.columns:
            features['volume_ma_20'] = features['volume'].rolling(20).mean()
            features['volume_ma_5'] = features['volume'].rolling(5).mean()
            features['volume_ratio'] = features['volume'] / features['volume_ma_20']
            features['volume_change'] = features['volume'].pct_change()
            
            # OBV (On-Balance Volume)
            features['obv'] = FeatureEngineer._calculate_obv(features)
        
        # 删除 NaN 值
        features = features.dropna()
        
        logger.debug(f"Prepared {len(features.columns)} features for {len(features)} samples")
        
        return features
    
    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """计算 RSI 指标"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # 防止除零
        loss = loss.replace(0, 1e-10)
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算 ATR 指标"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def _calculate_obv(df: pd.DataFrame) -> pd.Series:
        """计算 OBV 指标"""
        obv = pd.Series(index=df.index, dtype=float)
        obv.iloc[0] = df['volume'].iloc[0]
        
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
            elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        return obv
    
    @staticmethod
    def get_feature_names(include_volume: bool = True) -> List[str]:
        """获取特征名称列表"""
        base_features = [
            'returns', 'log_returns', 'price_change', 'high_low_range', 'close_open_range',
            'sma_5', 'sma_10', 'sma_20', 'sma_50',
            'ema_5', 'ema_10', 'ema_20', 'ema_50',
            'price_sma_5_ratio', 'price_sma_10_ratio', 'price_sma_20_ratio', 'price_sma_50_ratio',
            'rsi_14', 'rsi_7',
            'macd', 'macd_signal', 'macd_histogram',
            'bb_middle', 'bb_upper', 'bb_lower', 'bb_width', 'bb_position',
            'volatility_20', 'volatility_10',
            'atr_14',
            'momentum_5', 'momentum_10', 'momentum_20'
        ]
        
        if include_volume:
            base_features.extend([
                'volume_ma_20', 'volume_ma_5', 'volume_ratio', 'volume_change', 'obv'
            ])
        
        return base_features


# 便捷函数
def prepare_ml_features(df: pd.DataFrame, include_volume: bool = True) -> pd.DataFrame:
    """准备机器学习特征的便捷函数"""
    return FeatureEngineer.prepare_features(df, include_volume)
