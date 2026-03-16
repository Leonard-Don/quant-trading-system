"""
机器学习策略模块
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import logging

# from ..core.base import BaseComponent  # 暂时未使用
from .strategies import BaseStrategy

logger = logging.getLogger(__name__)


class MLStrategy(BaseStrategy):
    """机器学习基础策略"""

    def __init__(
        self,
        lookback_period: int = 20,
        prediction_horizon: int = 1,
        min_training_samples: int = 100,
        name: str = "MLStrategy",
        **kwargs,
    ):
        super().__init__(name=name, parameters={
            'lookback_period': lookback_period,
            'prediction_horizon': prediction_horizon,
            'min_training_samples': min_training_samples
        })
        self.lookback_period = lookback_period
        self.prediction_horizon = prediction_horizon
        self.min_training_samples = min_training_samples
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def _prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """准备机器学习特征"""
        features = pd.DataFrame(index=data.index)

        # 价格特征
        features["returns"] = data["Close"].pct_change()
        features["log_returns"] = np.log(data["Close"] / data["Close"].shift(1))
        features["volatility"] = features["returns"].rolling(10).std()

        # 技术指标特征
        features["rsi"] = self._calculate_rsi(data["Close"])
        features["macd"], features["macd_signal"] = self._calculate_macd(data["Close"])
        (
            features["bb_upper"],
            features["bb_middle"],
            features["bb_lower"],
        ) = self._calculate_bollinger_bands(data["Close"])

        # 移动平均特征
        for period in [5, 10, 20, 50]:
            features[f"ma_{period}"] = data["Close"].rolling(period).mean()
            features[f"ma_{period}_ratio"] = data["Close"] / features[f"ma_{period}"]

        # 成交量特征
        features["volume_ma"] = data["Volume"].rolling(20).mean()
        features["volume_ratio"] = data["Volume"] / features["volume_ma"]

        # 价格位置特征
        features["price_position"] = (data["Close"] - data["Low"].rolling(20).min()) / (
            data["High"].rolling(20).max() - data["Low"].rolling(20).min()
        )

        # 滞后特征
        for lag in [1, 2, 3, 5]:
            features[f"returns_lag_{lag}"] = features["returns"].shift(lag)
            features[f"rsi_lag_{lag}"] = features["rsi"].shift(lag)

        return features.fillna(method="ffill").fillna(0)

    def _prepare_labels(self, data: pd.DataFrame) -> pd.Series:
        """准备标签数据"""
        future_returns = (
            data["Close"]
            .pct_change(self.prediction_horizon)
            .shift(-self.prediction_horizon)
        )

        # 将连续的收益率转换为分类标签
        # 1: 上涨, 0: 下跌
        labels = (future_returns > 0).astype(int)

        return labels

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(
        self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ):
        """计算MACD"""
        exp1 = prices.ewm(span=fast).mean()
        exp2 = prices.ewm(span=slow).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line

    def _calculate_bollinger_bands(
        self, prices: pd.Series, period: int = 20, std_dev: int = 2
    ):
        """计算布林带"""
        ma = prices.rolling(period).mean()
        std = prices.rolling(period).std()
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        return upper, ma, lower

    def train(self, data: pd.DataFrame) -> bool:
        """训练模型"""
        try:
            if len(data) < self.min_training_samples:
                logger.warning(f"训练数据不足: {len(data)} < {self.min_training_samples}")
                return False

            # 准备特征和标签
            features = self._prepare_features(data)
            labels = self._prepare_labels(data)

            # 保存特征名称
            self.feature_names = features.columns.tolist()

            # 移除包含NaN的行
            valid_indices = ~(features.isna().any(axis=1) | labels.isna())
            features = features[valid_indices]
            labels = labels[valid_indices]

            if len(features) < self.min_training_samples:
                logger.warning("清理后的训练数据不足")
                return False

            # 标准化特征
            features_scaled = self.scaler.fit_transform(features)

            # 分割训练和验证集
            X_train, X_val, y_train, y_val = train_test_split(
                features_scaled, labels, test_size=0.2, random_state=42, stratify=labels
            )

            # 训练模型
            self.model.fit(X_train, y_train)

            # 验证模型
            train_score = self.model.score(X_train, y_train)
            val_score = self.model.score(X_val, y_val)

            logger.info(f"模型训练完成 - 训练准确率: {train_score: .3f}, 验证准确率: {val_score: .3f}")

            self.is_trained = True
            return True

        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            return False

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        if not self.is_trained or self.model is None:
            logger.warning("模型未训练，无法生成信号")
            return pd.Series(0, index=data.index)

        try:
            # 准备特征
            features = self._prepare_features(data)

            # 标准化特征
            features_scaled = self.scaler.transform(features)

            # 预测
            predictions = self.model.predict(features_scaled)

            # 转换为交易信号
            # 1 -> 1 (买入), 0 -> -1 (卖出)
            signals = pd.Series(np.where(predictions == 1, 1, -1), index=data.index)

            return signals

        except Exception as e:
            logger.error(f"信号生成失败: {e}")
            return pd.Series(0, index=data.index)


from ..utils.config import ML_CONFIG

class RandomForestStrategy(MLStrategy):
    """随机森林策略"""

    def __init__(self, n_estimators: int = None, max_depth: int = None, **kwargs):
        super().__init__(**kwargs)
        
        # 使用配置默认值
        rf_config = ML_CONFIG.get("random_forest", {})
        self.n_estimators = n_estimators or rf_config.get("n_estimators", 100)
        self.max_depth = max_depth or rf_config.get("max_depth", 10)
        self.random_state = rf_config.get("random_state", 42)
        
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators, 
            max_depth=self.max_depth, 
            random_state=self.random_state, 
            n_jobs=-1
        )

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """获取特征重要性"""
        if not self.is_trained or self.model is None:
            return None

        importance = self.model.feature_importances_
        
        # 使用保存的特征名称
        if hasattr(self, 'feature_names') and self.feature_names:
            feature_map = dict(zip(self.feature_names, importance))
            # 按重要性排序
            sorted_features = dict(sorted(feature_map.items(), key=lambda x: x[1], reverse=True))
            # 返回前20个最重要的特征
            return dict(list(sorted_features.items())[:20])
            
        # 降级方案
        top_indices = np.argsort(importance)[-10:][::-1]
        return {f"feature_{i}": importance[i] for i in top_indices}


class LogisticRegressionStrategy(MLStrategy):
    """逻辑回归策略"""

    def __init__(self, regularization: str = "l2", C: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.model = LogisticRegression(
            penalty=regularization, C=C, random_state=42, max_iter=1000
        )

    def get_coefficients(self) -> Optional[Dict[str, float]]:
        """获取模型系数"""
        if not self.is_trained or self.model is None:
            return None

        coefficients = self.model.coef_[0]

        return {f"coef_{i}": coef for i, coef in enumerate(coefficients)}


class EnsembleStrategy(BaseStrategy):
    """集成策略 - 结合多个ML模型"""

    def __init__(
        self,
        strategies: Optional[list] = None,
        weights: Optional[list] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # 默认策略组合
        if strategies is None:
            self.strategies = [
                RandomForestStrategy(**kwargs),
                LogisticRegressionStrategy(**kwargs),
            ]
        else:
            self.strategies = strategies

        # 权重
        if weights is None:
            self.weights = [1.0 / len(self.strategies)] * len(self.strategies)
        else:
            self.weights = weights

        if len(self.weights) != len(self.strategies):
            raise ValueError("权重数量必须与策略数量相同")

    def train_all(self, data: pd.DataFrame) -> Dict[str, bool]:
        """训练所有策略"""
        results = {}

        for i, strategy in enumerate(self.strategies):
            strategy_name = f"{strategy.__class__.__name__}_{i}"
            results[strategy_name] = strategy.train(data)

        return results

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成集成信号"""
        if not self.strategies:
            return pd.Series(0, index=data.index)

        # 收集所有策略的信号
        all_signals = []
        valid_weights = []

        for strategy, weight in zip(self.strategies, self.weights):
            if strategy.is_trained:
                signals = strategy.generate_signals(data)
                all_signals.append(signals)
                valid_weights.append(weight)

        if not all_signals:
            logger.warning("没有已训练的策略可用于集成")
            return pd.Series(0, index=data.index)

        # 标准化权重
        total_weight = sum(valid_weights)
        normalized_weights = [w / total_weight for w in valid_weights]

        # 加权平均
        ensemble_signals = pd.Series(0.0, index=data.index)
        for signals, weight in zip(all_signals, normalized_weights):
            ensemble_signals += signals * weight

        # 转换为离散信号
        return pd.Series(
            np.where(
                ensemble_signals > 0.3, 1, np.where(ensemble_signals < -0.3, -1, 0)
            ),
            index=data.index,
        )

    def get_strategy_performance(self, data: pd.DataFrame) -> Dict[str, Dict]:
        """获取各策略的性能表现"""
        performance = {}

        for i, strategy in enumerate(self.strategies):
            strategy_name = f"{strategy.__class__.__name__}_{i}"
            if strategy.is_trained:
                signals = strategy.generate_signals(data)

                # 计算简单的性能指标
                returns = data["Close"].pct_change()
                strategy_returns = signals.shift(1) * returns

                performance[strategy_name] = {
                    "total_return": strategy_returns.sum(),
                    "sharpe_ratio": strategy_returns.mean() / strategy_returns.std()
                    if strategy_returns.std() > 0
                    else 0,
                    "signal_count": (signals != 0).sum(),
                    "is_trained": True,
                }
            else:
                performance[strategy_name] = {"is_trained": False}

        return performance
