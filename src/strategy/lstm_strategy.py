"""
LSTM 神经网络策略模块

使用 LSTM 循环神经网络进行时序价格预测
支持 TensorFlow/Keras 或降级到 sklearn MLP
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Tuple
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.neural_network import MLPClassifier
import logging
import warnings

from .strategies import BaseStrategy

logger = logging.getLogger(__name__)

# 尝试导入 TensorFlow/Keras
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
    from tensorflow.keras.callbacks import EarlyStopping
    from tensorflow.keras.optimizers import Adam
    HAS_TENSORFLOW = True
    logger.info("TensorFlow 可用，将使用 LSTM 模型")
except ImportError:
    HAS_TENSORFLOW = False
    logger.info("TensorFlow 不可用，将降级使用 sklearn MLPClassifier")


class LSTMStrategy(BaseStrategy):
    """
    LSTM 神经网络策略
    
    使用长短期记忆网络进行价格方向预测
    
    特点：
    - 自动特征工程（技术指标 + 价格模式）
    - 序列数据处理
    - 支持 TensorFlow LSTM 或 sklearn MLP 降级
    """

    def __init__(
        self,
        sequence_length: int = 20,
        lstm_units: int = 50,
        dropout_rate: float = 0.2,
        epochs: int = 50,
        batch_size: int = 32,
        prediction_threshold: float = 0.5,
        use_tensorflow: bool = True,
        name: str = "LSTM",
        **kwargs,
    ):
        """
        初始化 LSTM 策略
        
        Args:
            sequence_length: LSTM 输入序列长度
            lstm_units: LSTM 隐藏单元数
            dropout_rate: Dropout 比率
            epochs: 训练轮数
            batch_size: 批次大小
            prediction_threshold: 预测阈值
            use_tensorflow: 是否使用 TensorFlow（可用时）
            name: 策略名称
        """
        super().__init__(name=name, parameters={
            'sequence_length': sequence_length,
            'lstm_units': lstm_units,
            'dropout_rate': dropout_rate,
            'epochs': epochs,
            'batch_size': batch_size
        })
        self.sequence_length = sequence_length
        self.lstm_units = lstm_units
        self.dropout_rate = dropout_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.prediction_threshold = prediction_threshold
        self.use_tensorflow = use_tensorflow and HAS_TENSORFLOW
        
        self.model = None
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.is_trained = False
        self.feature_names: List[str] = []
        
    def _prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """准备 LSTM 特征"""
        features = pd.DataFrame(index=data.index)
        
        close = data['close'] if 'close' in data.columns else data['Close']
        high = data['high'] if 'high' in data.columns else data['High']
        low = data['low'] if 'low' in data.columns else data['Low']
        volume = data['volume'] if 'volume' in data.columns else data.get('Volume', pd.Series(0, index=data.index))
        
        # 价格特征
        features['returns'] = close.pct_change()
        features['log_returns'] = np.log(close / close.shift(1))
        features['volatility_5'] = features['returns'].rolling(5).std()
        features['volatility_10'] = features['returns'].rolling(10).std()
        features['volatility_20'] = features['returns'].rolling(20).std()
        
        # 价格位置
        features['price_position'] = (close - low.rolling(20).min()) / (
            high.rolling(20).max() - low.rolling(20).min() + 1e-9
        )
        
        # 移动平均
        for period in [5, 10, 20, 50]:
            ma = close.rolling(period).mean()
            features[f'ma_{period}_ratio'] = close / (ma + 1e-9)
            features[f'ma_{period}_slope'] = ma.pct_change(5)
        
        # RSI
        features['rsi_14'] = self._calculate_rsi(close, 14)
        features['rsi_7'] = self._calculate_rsi(close, 7)
        
        # MACD
        exp12 = close.ewm(span=12).mean()
        exp26 = close.ewm(span=26).mean()
        features['macd'] = exp12 - exp26
        features['macd_signal'] = features['macd'].ewm(span=9).mean()
        features['macd_hist'] = features['macd'] - features['macd_signal']
        
        # 布林带
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        features['bb_upper'] = (ma20 + 2 * std20 - close) / (close + 1e-9)
        features['bb_lower'] = (close - ma20 + 2 * std20) / (close + 1e-9)
        features['bb_width'] = (4 * std20) / (ma20 + 1e-9)
        
        # 成交量特征（如果有）
        if volume.sum() > 0:
            volume_ma = volume.rolling(20).mean()
            features['volume_ratio'] = volume / (volume_ma + 1e-9)
            features['volume_change'] = volume.pct_change()
        
        # 动量特征
        for period in [1, 3, 5, 10]:
            features[f'momentum_{period}'] = close.pct_change(period)
        
        # 滞后收益率
        for lag in [1, 2, 3, 5]:
            features[f'returns_lag_{lag}'] = features['returns'].shift(lag)
        
        self.feature_names = features.columns.tolist()
        
        return features.fillna(method='ffill').fillna(0)
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算 RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))
    
    def _prepare_labels(self, data: pd.DataFrame, horizon: int = 1) -> pd.Series:
        """准备标签（未来价格方向）"""
        close = data['close'] if 'close' in data.columns else data['Close']
        future_returns = close.pct_change(horizon).shift(-horizon)
        labels = (future_returns > 0).astype(int)
        return labels
    
    def _create_sequences(
        self, 
        features: np.ndarray, 
        labels: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """创建 LSTM 序列数据"""
        X, y = [], []
        
        for i in range(len(features) - self.sequence_length):
            X.append(features[i:i + self.sequence_length])
            y.append(labels[i + self.sequence_length])
        
        return np.array(X), np.array(y)
    
    def _build_lstm_model(self, input_shape: Tuple[int, int]) -> None:
        """构建 TensorFlow LSTM 模型"""
        if not HAS_TENSORFLOW:
            raise RuntimeError("TensorFlow 不可用")
        
        # 抑制 TensorFlow 警告
        tf.get_logger().setLevel('ERROR')
        
        model = Sequential([
            LSTM(self.lstm_units, return_sequences=True, input_shape=input_shape),
            Dropout(self.dropout_rate),
            BatchNormalization(),
            
            LSTM(self.lstm_units // 2, return_sequences=False),
            Dropout(self.dropout_rate),
            BatchNormalization(),
            
            Dense(32, activation='relu'),
            Dropout(self.dropout_rate / 2),
            
            Dense(1, activation='sigmoid')
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='binary_crossentropy',
            metrics=['accuracy']
        )
        
        self.model = model
    
    def _build_mlp_model(self, n_features: int) -> None:
        """构建 sklearn MLP 备选模型"""
        self.model = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            alpha=0.001,
            batch_size=min(self.batch_size, 200),
            max_iter=self.epochs * 10,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=10,
            random_state=42,
            verbose=False
        )
    
    def train(self, data: pd.DataFrame) -> bool:
        """
        训练 LSTM 模型
        
        Args:
            data: 包含 OHLCV 数据的 DataFrame
            
        Returns:
            训练是否成功
        """
        try:
            min_samples = self.sequence_length * 5
            if len(data) < min_samples:
                logger.warning(f"训练数据不足: {len(data)} < {min_samples}")
                return False
            
            # 准备特征和标签
            features = self._prepare_features(data)
            labels = self._prepare_labels(data)
            
            # 移除 NaN
            valid_mask = ~(features.isna().any(axis=1) | labels.isna())
            features = features[valid_mask]
            labels = labels[valid_mask]
            
            if len(features) < min_samples:
                logger.warning("清理后数据不足")
                return False
            
            # 标准化
            features_scaled = self.scaler.fit_transform(features)
            labels_array = labels.values
            
            if self.use_tensorflow:
                return self._train_lstm(features_scaled, labels_array)
            else:
                return self._train_mlp(features_scaled, labels_array)
                
        except Exception as e:
            logger.error(f"LSTM 训练失败: {e}")
            return False
    
    def _train_lstm(self, features: np.ndarray, labels: np.ndarray) -> bool:
        """使用 TensorFlow LSTM 训练"""
        try:
            # 创建序列
            X, y = self._create_sequences(features, labels)
            
            if len(X) < 50:
                logger.warning("序列数据不足")
                return False
            
            # 分割数据
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            # 构建模型
            input_shape = (self.sequence_length, features.shape[1])
            self._build_lstm_model(input_shape)
            
            # 回调
            early_stop = EarlyStopping(
                monitor='val_loss',
                patience=5,
                restore_best_weights=True,
                verbose=0
            )
            
            # 训练
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                history = self.model.fit(
                    X_train, y_train,
                    epochs=self.epochs,
                    batch_size=self.batch_size,
                    validation_data=(X_val, y_val),
                    callbacks=[early_stop],
                    verbose=0
                )
            
            # 评估
            train_loss, train_acc = self.model.evaluate(X_train, y_train, verbose=0)
            val_loss, val_acc = self.model.evaluate(X_val, y_val, verbose=0)
            
            logger.info(f"LSTM 训练完成 - 训练准确率: {train_acc:.3f}, 验证准确率: {val_acc:.3f}")
            
            self.is_trained = True
            return True
            
        except Exception as e:
            logger.error(f"LSTM 训练失败: {e}")
            return False
    
    def _train_mlp(self, features: np.ndarray, labels: np.ndarray) -> bool:
        """使用 sklearn MLP 训练（降级方案）"""
        try:
            # 展平序列特征
            X_flat = []
            y_flat = []
            
            for i in range(len(features) - self.sequence_length):
                X_flat.append(features[i:i + self.sequence_length].flatten())
                y_flat.append(labels[i + self.sequence_length])
            
            X = np.array(X_flat)
            y = np.array(y_flat)
            
            if len(X) < 50:
                logger.warning("数据不足")
                return False
            
            # 构建模型
            self._build_mlp_model(X.shape[1])
            
            # 训练
            self.model.fit(X, y)
            
            train_score = self.model.score(X, y)
            logger.info(f"MLP 训练完成（LSTM降级）- 训练准确率: {train_score:.3f}")
            
            self.is_trained = True
            return True
            
        except Exception as e:
            logger.error(f"MLP 训练失败: {e}")
            return False
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        
        Args:
            data: OHLCV 数据
            
        Returns:
            交易信号序列: 1=买入, -1=卖出, 0=持有
        """
        if not self.is_trained or self.model is None:
            logger.warning("模型未训练")
            return pd.Series(0, index=data.index)
        
        try:
            features = self._prepare_features(data)
            features_scaled = self.scaler.transform(features)
            
            if self.use_tensorflow:
                return self._predict_lstm(data, features_scaled)
            else:
                return self._predict_mlp(data, features_scaled)
                
        except Exception as e:
            logger.error(f"信号生成失败: {e}")
            return pd.Series(0, index=data.index)
    
    def _predict_lstm(self, data: pd.DataFrame, features: np.ndarray) -> pd.Series:
        """使用 LSTM 预测"""
        signals = pd.Series(0, index=data.index)
        
        for i in range(self.sequence_length, len(features)):
            sequence = features[i - self.sequence_length:i].reshape(1, self.sequence_length, -1)
            prob = self.model.predict(sequence, verbose=0)[0, 0]
            
            if prob > self.prediction_threshold + 0.1:
                signals.iloc[i] = 1  # 买入
            elif prob < self.prediction_threshold - 0.1:
                signals.iloc[i] = -1  # 卖出
        
        return signals
    
    def _predict_mlp(self, data: pd.DataFrame, features: np.ndarray) -> pd.Series:
        """使用 MLP 预测"""
        signals = pd.Series(0, index=data.index)
        
        for i in range(self.sequence_length, len(features)):
            sequence = features[i - self.sequence_length:i].flatten().reshape(1, -1)
            prob = self.model.predict_proba(sequence)[0, 1]
            
            if prob > self.prediction_threshold + 0.1:
                signals.iloc[i] = 1
            elif prob < self.prediction_threshold - 0.1:
                signals.iloc[i] = -1
        
        return signals
    
    def get_model_summary(self) -> Dict:
        """获取模型摘要"""
        summary = {
            'strategy_type': 'LSTM' if self.use_tensorflow else 'MLP',
            'is_trained': self.is_trained,
            'sequence_length': self.sequence_length,
            'feature_count': len(self.feature_names),
            'features': self.feature_names[:10] if self.feature_names else [],
            'has_tensorflow': HAS_TENSORFLOW
        }
        
        if self.use_tensorflow and self.is_trained and self.model:
            summary['model_params'] = self.model.count_params()
        
        return summary


class DeepLearningEnsemble(BaseStrategy):
    """
    深度学习集成策略
    
    结合 LSTM 和传统 ML 模型的集成预测
    """
    
    def __init__(
        self,
        lstm_weight: float = 0.5,
        include_lstm: bool = True,
        include_rf: bool = True,
        include_lr: bool = True,
        name: str = "DeepLearningEnsemble",
        **kwargs
    ):
        super().__init__(name=name, parameters={'lstm_weight': lstm_weight})
        self.lstm_weight = lstm_weight
        self.models = []
        self.weights = []
        
        if include_lstm:
            self.models.append(LSTMStrategy(name="LSTM_Ensemble"))
            self.weights.append(lstm_weight)
        
        if include_rf:
            from .ml_strategies import RandomForestStrategy
            self.models.append(RandomForestStrategy())
            self.weights.append((1 - lstm_weight) / 2)
        
        if include_lr:
            from .ml_strategies import LogisticRegressionStrategy
            self.models.append(LogisticRegressionStrategy())
            self.weights.append((1 - lstm_weight) / 2)
        
        # 标准化权重
        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]
        
        self.is_trained = False
    
    def train(self, data: pd.DataFrame) -> bool:
        """训练所有模型"""
        success_count = 0
        
        for model in self.models:
            try:
                if model.train(data):
                    success_count += 1
            except Exception as e:
                logger.warning(f"模型训练失败: {model.__class__.__name__}: {e}")
        
        self.is_trained = success_count > 0
        logger.info(f"集成训练完成: {success_count}/{len(self.models)} 模型成功")
        return self.is_trained
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成集成信号"""
        if not self.is_trained:
            return pd.Series(0, index=data.index)
        
        ensemble_signals = pd.Series(0.0, index=data.index)
        valid_weight_sum = 0
        
        for model, weight in zip(self.models, self.weights):
            if model.is_trained:
                signals = model.generate_signals(data)
                ensemble_signals += signals * weight
                valid_weight_sum += weight
        
        if valid_weight_sum > 0:
            ensemble_signals /= valid_weight_sum
        
        # 转换为离散信号
        return pd.Series(
            np.where(ensemble_signals > 0.3, 1, 
                     np.where(ensemble_signals < -0.3, -1, 0)),
            index=data.index
        )
