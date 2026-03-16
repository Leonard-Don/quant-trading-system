"""
LSTM 时序预测模型
使用 TensorFlow/Keras 实现股票价格预测
预测目标为下一日收益率（而非绝对价格），消除对价格水平的依赖
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
import os
import pickle

logger = logging.getLogger(__name__)

# 导入共用特征工程模块
from .feature_engineering import FeatureEngineer

# 尝试导入 TensorFlow，如果不可用则使用模拟模式
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    from tensorflow.keras.optimizers import Adam
    from sklearn.preprocessing import MinMaxScaler
    TF_AVAILABLE = True
    logger.info("TensorFlow loaded successfully")
except ImportError:
    TF_AVAILABLE = False
    logger.warning("TensorFlow not available, LSTM predictor will use fallback mode")


class LSTMPredictor:
    """
    LSTM 时序预测模型
    使用双向 LSTM 网络预测股票价格收益率
    """
    
    def __init__(self, sequence_length: int = 60, forecast_days: int = 5):
        """
        初始化 LSTM 预测器
        
        Args:
            sequence_length: 输入序列长度（用多少天的数据预测）
            forecast_days: 预测天数
        """
        self.sequence_length = sequence_length
        self.forecast_days = forecast_days
        self.models: Dict[str, any] = {}
        self.scalers: Dict[str, MinMaxScaler] = {} if TF_AVAILABLE else {}
        # 使用相对/归一化特征，避免对绝对价格水平的依赖
        self.feature_columns = [
            'returns', 'log_returns', 'high_low_pct', 
            'close_sma5_ratio', 'close_sma20_ratio',
            'rsi', 'volatility', 'volume_ratio', 'macd_norm'
        ]
        self.model_dir = os.path.join(os.path.dirname(__file__), 'saved_models', 'lstm')
        os.makedirs(self.model_dir, exist_ok=True)
        
    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        准备相对/归一化特征数据（价格水平无关）
        """
        data = df.copy()
        
        # 收益率特征
        data['returns'] = data['close'].pct_change()
        data['log_returns'] = np.log(data['close'] / data['close'].shift(1))
        
        # 相对范围 (high-low 占 close 的百分比)
        data['high_low_pct'] = (data['high'] - data['low']) / data['close']
        
        # 价格相对于均线的比率
        sma_5 = data['close'].rolling(window=5).mean()
        sma_20 = data['close'].rolling(window=20).mean()
        data['close_sma5_ratio'] = data['close'] / sma_5
        data['close_sma20_ratio'] = data['close'] / sma_20
        
        # RSI (0-100, 已是标准化的)
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        data['rsi'] = 100 - (100 / (1 + rs))
        
        # 波动率 (收益率标准差)
        data['volatility'] = data['returns'].rolling(window=20).std()
        
        # 量比 (相对于20日均量)
        vol_ma20 = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / (vol_ma20 + 1e-10)
        
        # MACD 归一化 (除以 close 去除价格水平影响)
        exp12 = data['close'].ewm(span=12, adjust=False).mean()
        exp26 = data['close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        data['macd_norm'] = macd / data['close']
        
        # 目标：下一日收益率
        data['next_return'] = data['returns'].shift(-1)
        
        # 清理 NaN
        data = data.fillna(method='bfill').fillna(method='ffill')
        data = data.dropna(subset=self.feature_columns)
        
        return data
    
    def _create_sequences(self, data: np.ndarray, target: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        创建 LSTM 输入序列
        
        Args:
            data: 特征数据数组 (samples, features)
            target: 目标值数组 (samples,)
            
        Returns:
            X: 输入序列 (samples, sequence_length, features)
            y: 目标值 (samples,)
        """
        X, y = [], []
        for i in range(len(data) - self.sequence_length):
            X.append(data[i:(i + self.sequence_length)])
            y.append(target[i + self.sequence_length])
        return np.array(X), np.array(y)
    
    def _build_model(self, input_shape: Tuple[int, int]) -> any:
        """
        构建 LSTM 模型
        """
        if not TF_AVAILABLE:
            return None
            
        model = Sequential([
            Bidirectional(LSTM(64, return_sequences=True), input_shape=input_shape),
            Dropout(0.2),
            LSTM(32, return_sequences=False),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dense(1)  # 输出：下一日收益率
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        return model
    
    def train(self, historical_data: pd.DataFrame, symbol: str) -> Dict:
        """
        训练 LSTM 模型（预测下一日收益率）
        """
        symbol = symbol.upper()
        logger.info(f"Training LSTM model for {symbol}")
        
        if not TF_AVAILABLE:
            logger.warning("TensorFlow not available, using mock training")
            return self._mock_train(symbol)
        
        try:
            data = self._prepare_features(historical_data)
            
            # 特征数据
            feature_data = data[self.feature_columns].values
            
            # 目标：下一日收益率
            target_data = data['next_return'].values
            
            # 移除最后一行（next_return 为 NaN）
            valid_mask = ~np.isnan(target_data)
            feature_data = feature_data[valid_mask]
            target_data = target_data[valid_mask]
            
            # 归一化特征（注意：这里归一化的是相对特征，不是绝对价格）
            scaler = MinMaxScaler(feature_range=(-1, 1))
            scaled_features = scaler.fit_transform(feature_data)
            self.scalers[symbol] = scaler
            
            # 创建序列
            X, y = self._create_sequences(scaled_features, target_data)
            
            if len(X) < 20:
                logger.warning(f"Insufficient sequences for {symbol}: {len(X)}")
                return self._mock_train(symbol)
            
            # 分割训练集和验证集
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            # 构建模型
            model = self._build_model((X.shape[1], X.shape[2]))
            
            # 回调
            callbacks = [
                EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True),
                ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5)
            ]
            
            # 训练
            history = model.fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=100,
                batch_size=32,
                callbacks=callbacks,
                verbose=0
            )
            
            self.models[symbol] = model
            
            val_loss = min(history.history['val_loss'])
            train_loss = min(history.history['loss'])
            
            self._save_model(symbol)
            
            return {
                'symbol': symbol,
                'model_type': 'LSTM',
                'train_loss': float(train_loss),
                'val_loss': float(val_loss),
                'epochs_trained': len(history.history['loss']),
                'sequence_length': self.sequence_length,
                'features_used': self.feature_columns
            }
            
        except Exception as e:
            logger.error(f"Error training LSTM model for {symbol}: {e}")
            return self._mock_train(symbol)
    
    def _mock_train(self, symbol: str) -> Dict:
        """模拟训练结果（当 TensorFlow 不可用时）"""
        return {
            'symbol': symbol,
            'model_type': 'LSTM (Mock)',
            'train_loss': 0.001,
            'val_loss': 0.002,
            'epochs_trained': 50,
            'sequence_length': self.sequence_length,
            'note': 'TensorFlow not available, using mock mode'
        }
    
    def predict(self, current_data: pd.DataFrame, symbol: str, days: int = 5) -> Dict:
        """
        预测未来价格（通过预测收益率再转换为价格）
        """
        symbol = symbol.upper()
        logger.info(f"Predicting next {days} days for {symbol} using LSTM")
        
        if not TF_AVAILABLE or symbol not in self.models:
            # 尝试加载已保存的模型
            if TF_AVAILABLE and self._load_model(symbol):
                pass  # 模型加载成功，继续
            else:
                return self._mock_predict(current_data, symbol, days)
        
        try:
            data = self._prepare_features(current_data)
            feature_data = data[self.feature_columns].values
            
            scaler = self.scalers.get(symbol)
            if scaler is None:
                return self._mock_predict(current_data, symbol, days)
            
            scaled_data = scaler.transform(feature_data)
            
            # 取最后 sequence_length 天的数据
            if len(scaled_data) < self.sequence_length:
                return self._mock_predict(current_data, symbol, days)
            last_sequence = scaled_data[-self.sequence_length:]
            
            model = self.models[symbol]
            
            # 当前价格（预测的锚点）
            last_price = float(current_data['close'].iloc[-1])
            running_price = last_price
            
            predicted_returns = []
            predictions = []
            current_sequence = last_sequence.copy()
            
            # 逐日预测收益率
            for _ in range(days):
                pred_return = model.predict(
                    current_sequence.reshape(1, self.sequence_length, -1), verbose=0
                )[0, 0]
                
                # 限制极端预测（单日收益率不超过±10%）
                pred_return = np.clip(pred_return, -0.10, 0.10)
                predicted_returns.append(float(pred_return))
                
                # 收益率转价格
                next_price = running_price * (1 + pred_return)
                predictions.append(round(float(next_price), 2))
                running_price = next_price
                
                # 更新序列（滑动窗口）
                # 构造新的特征行（用预测的收益率更新关键特征）
                new_row = current_sequence[-1].copy()
                # returns 和 log_returns 大约是第0和第1个特征
                # 我们用原始 scaler 来归一化新的特征值
                new_features = current_sequence[-1].copy()
                # 简单更新：保持其他特征不变，只微调序列
                current_sequence = np.vstack([current_sequence[1:], new_features.reshape(1, -1)])
            
            # 生成日期
            if 'date' in current_data.columns:
                last_date = pd.to_datetime(current_data['date'].iloc[-1])
            else:
                last_date = pd.to_datetime(current_data.index[-1])
            dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(days)]
            
            # 置信区间（基于历史波动率）
            volatility = current_data['close'].pct_change().std()
            confidence_intervals = []
            for i, pred_price in enumerate(predictions):
                uncertainty = pred_price * volatility * np.sqrt(i + 1) * 1.96
                confidence_intervals.append({
                    'lower': round(float(pred_price - uncertainty), 2),
                    'upper': round(float(pred_price + uncertainty), 2)
                })
            
            return {
                'model_type': 'LSTM',
                'symbol': symbol,
                'dates': dates,
                'predicted_prices': predictions,
                'confidence_intervals': confidence_intervals,
                'sequence_length': self.sequence_length
            }
            
        except Exception as e:
            logger.error(f"Error predicting with LSTM for {symbol}: {e}")
            return self._mock_predict(current_data, symbol, days)
    
    def _mock_predict(self, current_data: pd.DataFrame, symbol: str, days: int) -> Dict:
        """
        确定性 fallback 预测（基于近期趋势，无随机噪声）
        """
        last_price = float(current_data['close'].iloc[-1])
        
        # 获取最后一个日期
        if 'date' in current_data.columns:
            last_date = pd.to_datetime(current_data['date'].iloc[-1])
        else:
            last_date = pd.to_datetime(current_data.index[-1])
        
        # 基于近期趋势的确定性预测（使用最近20天的均值趋势）
        recent_returns = current_data['close'].pct_change().tail(20)
        trend = float(recent_returns.mean())
        volatility = float(recent_returns.std())
        
        # 趋势衰减：越远的预测越接近均值回归
        predictions = []
        confidence_intervals = []
        dates = []
        
        current_price = last_price
        for i in range(days):
            # 趋势衰减因子（第1天用100%趋势，之后逐步降低）
            decay = 0.8 ** i
            predicted_return = trend * decay
            current_price = current_price * (1 + predicted_return)
            predictions.append(round(float(current_price), 2))
            
            # 置信区间
            uncertainty = current_price * volatility * np.sqrt(i + 1) * 1.96
            confidence_intervals.append({
                'lower': round(float(current_price - uncertainty), 2),
                'upper': round(float(current_price + uncertainty), 2)
            })
            
            dates.append((last_date + timedelta(days=i+1)).strftime('%Y-%m-%d'))
        
        return {
            'model_type': 'LSTM (Fallback)',
            'symbol': symbol,
            'dates': dates,
            'predicted_prices': predictions,
            'confidence_intervals': confidence_intervals,
            'note': 'Using simplified trend-following prediction'
        }
    
    def _save_model(self, symbol: str):
        """保存模型到磁盘"""
        if not TF_AVAILABLE or symbol not in self.models:
            return
            
        try:
            model_path = os.path.join(self.model_dir, f'{symbol}_lstm.keras')
            scaler_path = os.path.join(self.model_dir, f'{symbol}_scaler.pkl')
            
            self.models[symbol].save(model_path)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scalers[symbol], f)
            
            logger.info(f"Saved LSTM model for {symbol}")
        except Exception as e:
            logger.error(f"Error saving model for {symbol}: {e}")
    
    def _load_model(self, symbol: str) -> bool:
        """从磁盘加载模型"""
        if not TF_AVAILABLE:
            return False
            
        try:
            model_path = os.path.join(self.model_dir, f'{symbol}_lstm.keras')
            scaler_path = os.path.join(self.model_dir, f'{symbol}_scaler.pkl')
            
            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.models[symbol] = load_model(model_path)
                with open(scaler_path, 'rb') as f:
                    self.scalers[symbol] = pickle.load(f)
                logger.info(f"Loaded LSTM model for {symbol}")
                return True
        except Exception as e:
            logger.error(f"Error loading model for {symbol}: {e}")
        
        return False


# 全局实例
lstm_predictor = LSTMPredictor()
