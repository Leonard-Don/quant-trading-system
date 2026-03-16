"""
配对交易策略模块 (Pairs Trading / Statistical Arbitrage)

实现基于协整关系的统计套利策略
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from scipy import stats
import logging
from .strategies import BaseStrategy
from ..utils.performance import timing_decorator

logger = logging.getLogger(__name__)


class PairsTradingStrategy(BaseStrategy):
    """
    配对交易策略
    
    基于两只相关股票的价差进行交易，当价差偏离均值时
    做多被低估的股票，做空被高估的股票
    """
    
    def __init__(
        self,
        lookback_period: int = 60,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.5,
        stop_loss_zscore: float = 4.0,
        **kwargs
    ):
        """
        初始化配对交易策略
        
        Args:
            lookback_period: 回看周期，用于计算价差的均值和标准差
            entry_zscore: 入场Z分数阈值
            exit_zscore: 出场Z分数阈值
            stop_loss_zscore: 止损Z分数阈值
        """
        super().__init__(
            name="PairsTrading",
            parameters={
                "lookback_period": lookback_period,
                "entry_zscore": entry_zscore,
                "exit_zscore": exit_zscore,
                "stop_loss_zscore": stop_loss_zscore
            }
        )
        self.lookback_period = lookback_period
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.stop_loss_zscore = stop_loss_zscore
        
        # 存储配对信息
        self.pair_info = {}
        self.hedge_ratio = 1.0
    
    def find_cointegrated_pairs(
        self, 
        price_data: Dict[str, pd.Series],
        significance_level: float = 0.05
    ) -> List[Tuple[str, str, float]]:
        """
        查找协整的股票对
        
        Args:
            price_data: 字典，键为股票代码，值为价格序列
            significance_level: 显著性水平
            
        Returns:
            协整对列表: [(symbol1, symbol2, p_value), ...]
        """
        symbols = list(price_data.keys())
        n = len(symbols)
        cointegrated_pairs = []
        
        for i in range(n):
            for j in range(i + 1, n):
                sym1, sym2 = symbols[i], symbols[j]
                try:
                    # 对齐数据
                    s1 = price_data[sym1].dropna()
                    s2 = price_data[sym2].dropna()
                    common_idx = s1.index.intersection(s2.index)
                    s1 = s1.loc[common_idx]
                    s2 = s2.loc[common_idx]
                    
                    if len(s1) < 30:
                        continue
                    
                    # Engle-Granger协整检验
                    p_value = self._engle_granger_test(s1.values, s2.values)
                    
                    if p_value < significance_level:
                        cointegrated_pairs.append((sym1, sym2, p_value))
                        
                except Exception as e:
                    logger.warning(f"协整检验失败 {sym1}-{sym2}: {e}")
                    
        # 按p值排序
        cointegrated_pairs.sort(key=lambda x: x[2])
        return cointegrated_pairs
    
    def _engle_granger_test(self, y1: np.ndarray, y2: np.ndarray) -> float:
        """
        执行Engle-Granger协整检验
        
        Returns:
            p_value: 协整检验的p值，越小表示越可能协整
        """
        # 简化版：使用OLS残差的ADF检验
        # 完整版应该使用statsmodels的coint函数
        
        # 计算对冲比率（OLS回归）
        X = np.column_stack([np.ones(len(y1)), y1])
        beta = np.linalg.lstsq(X, y2, rcond=None)[0]
        
        # 计算价差（残差）
        spread = y2 - beta[0] - beta[1] * y1
        
        # 简化的ADF检验（使用残差的自相关）
        # 真正的ADF检验应该用statsmodels
        diff_spread = np.diff(spread)
        lagged_spread = spread[:-1]
        
        if len(diff_spread) < 10:
            return 1.0
        
        # 简单回归 diff_spread ~ lagged_spread
        X = np.column_stack([np.ones(len(lagged_spread)), lagged_spread])
        try:
            beta_adf = np.linalg.lstsq(X, diff_spread, rcond=None)[0]
            residuals = diff_spread - X @ beta_adf
            se = np.sqrt(np.sum(residuals**2) / (len(residuals) - 2))
            t_stat = beta_adf[1] / (se / np.sqrt(np.sum(lagged_spread**2)))
            
            # 近似p值（使用t分布，这是简化版）
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), len(residuals) - 2))
            return p_value
        except:
            return 1.0
    
    def calculate_hedge_ratio(
        self, 
        price1: pd.Series, 
        price2: pd.Series
    ) -> float:
        """
        计算对冲比率
        
        使用OLS回归计算price2 = alpha + beta * price1中的beta
        """
        X = np.column_stack([np.ones(len(price1)), price1.values])
        y = price2.values
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        return beta[1]
    
    def calculate_spread(
        self,
        price1: pd.Series,
        price2: pd.Series,
        hedge_ratio: Optional[float] = None
    ) -> pd.Series:
        """
        计算价差
        
        spread = price2 - hedge_ratio * price1
        """
        if hedge_ratio is None:
            hedge_ratio = self.calculate_hedge_ratio(price1, price2)
        
        self.hedge_ratio = hedge_ratio
        spread = price2 - hedge_ratio * price1
        return spread
    
    def calculate_zscore(self, spread: pd.Series) -> pd.Series:
        """
        计算价差的Z分数
        """
        mean = spread.rolling(window=self.lookback_period).mean()
        std = spread.rolling(window=self.lookback_period).std()
        zscore = (spread - mean) / std
        return zscore
    
    @timing_decorator
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        
        对于单股票回测，这个方法使用data中的close和另一个参考价格
        对于配对交易，需要使用generate_pair_signals方法
        
        Args:
            data: 必须包含'close'和'pair_close'列
            
        Returns:
            信号序列: 1=买入, -1=卖出, 0=持有
        """
        if 'pair_close' not in data.columns:
            # 如果没有配对数据，使用自身价格模拟
            logger.warning("配对交易需要pair_close列，使用模拟数据")
            price1 = data['close']
            price2 = data['close'].shift(1).fillna(method='bfill')
        else:
            price1 = data['close']
            price2 = data['pair_close']
        
        return self.generate_pair_signals(price1, price2)
    
    def generate_pair_signals(
        self,
        price1: pd.Series,
        price2: pd.Series
    ) -> pd.Series:
        """
        生成配对交易信号
        
        Args:
            price1: 第一只股票价格序列
            price2: 第二只股票价格序列
            
        Returns:
            信号序列: 
                1 = 做多价差（做多stock2，做空stock1）
               -1 = 做空价差（做空stock2，做多stock1）
                0 = 持有/平仓
        """
        # 计算价差和Z分数
        spread = self.calculate_spread(price1, price2)
        zscore = self.calculate_zscore(spread)
        
        signals = pd.Series(index=price1.index, data=0)
        position = 0
        
        for i in range(len(zscore)):
            z = zscore.iloc[i]
            
            if pd.isna(z):
                continue
            
            # 止损
            if abs(z) > self.stop_loss_zscore and position != 0:
                signals.iloc[i] = -position  # 平仓
                position = 0
                continue
            
            # 入场
            if position == 0:
                if z > self.entry_zscore:
                    signals.iloc[i] = -1  # 做空价差
                    position = -1
                elif z < -self.entry_zscore:
                    signals.iloc[i] = 1  # 做多价差
                    position = 1
            
            # 出场
            elif position == 1 and z > -self.exit_zscore:
                signals.iloc[i] = -1  # 平仓做多
                position = 0
            elif position == -1 and z < self.exit_zscore:
                signals.iloc[i] = 1  # 平仓做空
                position = 0
        
        self.signals = signals
        return signals
    
    def get_pair_metrics(
        self,
        price1: pd.Series,
        price2: pd.Series
    ) -> Dict[str, Any]:
        """
        获取配对指标
        """
        spread = self.calculate_spread(price1, price2)
        zscore = self.calculate_zscore(spread)
        
        # 计算相关系数
        returns1 = price1.pct_change().dropna()
        returns2 = price2.pct_change().dropna()
        correlation = returns1.corr(returns2)
        
        # 计算价差统计
        spread_clean = spread.dropna()
        zscore_clean = zscore.dropna()
        
        return {
            "hedge_ratio": self.hedge_ratio,
            "correlation": correlation,
            "spread_mean": spread_clean.mean(),
            "spread_std": spread_clean.std(),
            "current_zscore": zscore_clean.iloc[-1] if len(zscore_clean) > 0 else None,
            "half_life": self._calculate_half_life(spread_clean),
            "lookback_period": self.lookback_period
        }
    
    def _calculate_half_life(self, spread: pd.Series) -> Optional[float]:
        """
        计算价差均值回归的半衰期
        """
        try:
            spread_lag = spread.shift(1).dropna()
            spread_diff = spread.diff().dropna()
            
            # 对齐
            common_idx = spread_lag.index.intersection(spread_diff.index)
            spread_lag = spread_lag.loc[common_idx]
            spread_diff = spread_diff.loc[common_idx]
            
            if len(spread_lag) < 10:
                return None
            
            # 回归 spread_diff ~ spread_lag
            X = spread_lag.values.reshape(-1, 1)
            y = spread_diff.values
            
            beta = np.linalg.lstsq(X, y, rcond=None)[0][0]
            
            if beta >= 0:
                return None  # 不是均值回归
            
            half_life = -np.log(2) / beta
            return half_life
        except:
            return None


class MultiPairStrategy(BaseStrategy):
    """
    多配对组合策略
    
    同时交易多个配对，分散风险
    """
    
    def __init__(
        self,
        max_pairs: int = 5,
        correlation_threshold: float = 0.7,
        **kwargs
    ):
        super().__init__(
            name="MultiPair",
            parameters={
                "max_pairs": max_pairs,
                "correlation_threshold": correlation_threshold
            }
        )
        self.max_pairs = max_pairs
        self.correlation_threshold = correlation_threshold
        self.pairs_strategies: List[PairsTradingStrategy] = []
    
    def select_pairs(
        self,
        price_data: Dict[str, pd.Series]
    ) -> List[Tuple[str, str]]:
        """
        选择最佳配对
        """
        base_strategy = PairsTradingStrategy()
        cointegrated = base_strategy.find_cointegrated_pairs(price_data)
        
        selected = []
        used_symbols = set()
        
        for sym1, sym2, p_value in cointegrated:
            if len(selected) >= self.max_pairs:
                break
            
            # 避免重复使用同一只股票
            if sym1 not in used_symbols and sym2 not in used_symbols:
                selected.append((sym1, sym2))
                used_symbols.add(sym1)
                used_symbols.add(sym2)
        
        return selected
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        对于多配对策略，需要使用generate_multi_signals方法
        """
        return pd.Series(index=data.index, data=0)
    
    def generate_multi_signals(
        self,
        price_data: Dict[str, pd.Series],
        pairs: List[Tuple[str, str]]
    ) -> Dict[str, pd.Series]:
        """
        为多个配对生成信号
        
        Returns:
            字典: {(sym1, sym2): signals}
        """
        all_signals = {}
        
        for sym1, sym2 in pairs:
            if sym1 not in price_data or sym2 not in price_data:
                continue
            
            strategy = PairsTradingStrategy()
            signals = strategy.generate_pair_signals(
                price_data[sym1],
                price_data[sym2]
            )
            all_signals[(sym1, sym2)] = signals
        
        return all_signals
