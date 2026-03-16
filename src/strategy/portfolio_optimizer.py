"""
投资组合优化模块

实现Markowitz均值-方差优化和其他组合优化方法
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """
    投资组合优化器
    
    支持:
    - 均值-方差优化 (Markowitz)
    - 最大夏普比率组合
    - 风险平价
    - 最小方差组合
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,
        constraints: Optional[Dict] = None
    ):
        """
        初始化优化器
        
        Args:
            risk_free_rate: 无风险利率 (年化)
            constraints: 约束条件 {'min_weight': 0.0, 'max_weight': 1.0}
        """
        self.risk_free_rate = risk_free_rate
        self.constraints = constraints or {
            'min_weight': 0.0,
            'max_weight': 1.0
        }
        
        # 存储优化结果
        self.optimal_weights = None
        self.expected_return = None
        self.expected_volatility = None
        self.sharpe_ratio = None
    
    def calculate_portfolio_stats(
        self,
        weights: np.ndarray,
        returns: pd.DataFrame
    ) -> Tuple[float, float, float]:
        """
        计算组合统计量
        
        Args:
            weights: 权重数组
            returns: 收益率DataFrame
            
        Returns:
            (预期收益率, 波动率, 夏普比率)
        """
        mean_returns = returns.mean() * 252  # 年化
        cov_matrix = returns.cov() * 252  # 年化
        
        portfolio_return = np.dot(weights, mean_returns)
        portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe = (portfolio_return - self.risk_free_rate) / portfolio_volatility
        
        return portfolio_return, portfolio_volatility, sharpe
    
    def optimize_max_sharpe(
        self,
        returns: pd.DataFrame,
        include_short: bool = False
    ) -> Dict[str, Any]:
        """
        最大化夏普比率
        
        Args:
            returns: 日收益率DataFrame，列为资产名称
            include_short: 是否允许做空
            
        Returns:
            优化结果字典
        """
        n_assets = len(returns.columns)
        
        # 目标函数：负夏普比率（因为我们要最小化）
        def neg_sharpe(weights):
            ret, vol, sharpe = self.calculate_portfolio_stats(weights, returns)
            return -sharpe
        
        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}  # 权重和为1
        ]
        
        # 边界
        if include_short:
            bounds = tuple((-1, 1) for _ in range(n_assets))
        else:
            bounds = tuple((
                self.constraints['min_weight'],
                self.constraints['max_weight']
            ) for _ in range(n_assets))
        
        # 初始权重：等权
        init_weights = np.array([1/n_assets] * n_assets)
        
        # 优化
        result = minimize(
            neg_sharpe,
            init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000}
        )
        
        if result.success:
            self.optimal_weights = result.x
            ret, vol, sharpe = self.calculate_portfolio_stats(result.x, returns)
            self.expected_return = ret
            self.expected_volatility = vol
            self.sharpe_ratio = sharpe
            
            return {
                'success': True,
                'weights': dict(zip(returns.columns, result.x)),
                'expected_return': ret,
                'expected_volatility': vol,
                'sharpe_ratio': sharpe,
                'optimization_method': 'max_sharpe'
            }
        else:
            return {
                'success': False,
                'error': result.message,
                'optimization_method': 'max_sharpe'
            }
    
    def optimize_min_variance(
        self,
        returns: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        最小化组合方差
        """
        n_assets = len(returns.columns)
        cov_matrix = returns.cov() * 252
        
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        ]
        
        bounds = tuple((
            self.constraints['min_weight'],
            self.constraints['max_weight']
        ) for _ in range(n_assets))
        
        init_weights = np.array([1/n_assets] * n_assets)
        
        result = minimize(
            portfolio_variance,
            init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        if result.success:
            ret, vol, sharpe = self.calculate_portfolio_stats(result.x, returns)
            
            return {
                'success': True,
                'weights': dict(zip(returns.columns, result.x)),
                'expected_return': ret,
                'expected_volatility': vol,
                'sharpe_ratio': sharpe,
                'optimization_method': 'min_variance'
            }
        else:
            return {
                'success': False,
                'error': result.message,
                'optimization_method': 'min_variance'
            }
    
    def optimize_risk_parity(
        self,
        returns: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        风险平价优化
        
        使每个资产对组合风险的贡献相等
        """
        n_assets = len(returns.columns)
        cov_matrix = returns.cov() * 252
        
        def risk_budget_objective(weights):
            # 组合波动率
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            
            # 边际风险贡献
            marginal_contrib = np.dot(cov_matrix, weights)
            
            # 风险贡献
            risk_contrib = weights * marginal_contrib / port_vol
            
            # 目标：使所有风险贡献相等
            target_contrib = port_vol / n_assets
            return np.sum((risk_contrib - target_contrib) ** 2)
        
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        ]
        
        bounds = tuple((0.01, 1) for _ in range(n_assets))  # 最小1%
        init_weights = np.array([1/n_assets] * n_assets)
        
        result = minimize(
            risk_budget_objective,
            init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        if result.success:
            ret, vol, sharpe = self.calculate_portfolio_stats(result.x, returns)
            
            # 计算实际风险贡献
            port_vol = np.sqrt(np.dot(result.x.T, np.dot(cov_matrix, result.x)))
            marginal_contrib = np.dot(cov_matrix, result.x)
            risk_contrib = result.x * marginal_contrib / port_vol
            
            return {
                'success': True,
                'weights': dict(zip(returns.columns, result.x)),
                'expected_return': ret,
                'expected_volatility': vol,
                'sharpe_ratio': sharpe,
                'risk_contributions': dict(zip(returns.columns, risk_contrib)),
                'optimization_method': 'risk_parity'
            }
        else:
            return {
                'success': False,
                'error': result.message,
                'optimization_method': 'risk_parity'
            }
    
    def optimize_target_return(
        self,
        returns: pd.DataFrame,
        target_return: float
    ) -> Dict[str, Any]:
        """
        给定目标收益率，最小化风险
        """
        n_assets = len(returns.columns)
        mean_returns = returns.mean() * 252
        cov_matrix = returns.cov() * 252
        
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
            {'type': 'eq', 'fun': lambda x: np.dot(x, mean_returns) - target_return}
        ]
        
        bounds = tuple((
            self.constraints['min_weight'],
            self.constraints['max_weight']
        ) for _ in range(n_assets))
        
        init_weights = np.array([1/n_assets] * n_assets)
        
        result = minimize(
            portfolio_variance,
            init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        if result.success:
            ret, vol, sharpe = self.calculate_portfolio_stats(result.x, returns)
            
            return {
                'success': True,
                'weights': dict(zip(returns.columns, result.x)),
                'expected_return': ret,
                'expected_volatility': vol,
                'sharpe_ratio': sharpe,
                'target_return': target_return,
                'optimization_method': 'target_return'
            }
        else:
            return {
                'success': False,
                'error': result.message,
                'optimization_method': 'target_return'
            }
    
    def generate_efficient_frontier(
        self,
        returns: pd.DataFrame,
        n_points: int = 50
    ) -> List[Dict[str, float]]:
        """
        生成有效前沿
        """
        mean_returns = returns.mean() * 252
        
        # 确定收益率范围
        min_ret = mean_returns.min()
        max_ret = mean_returns.max()
        target_returns = np.linspace(min_ret, max_ret, n_points)
        
        frontier = []
        
        for target in target_returns:
            result = self.optimize_target_return(returns, target)
            if result['success']:
                frontier.append({
                    'return': result['expected_return'],
                    'volatility': result['expected_volatility'],
                    'sharpe': result['sharpe_ratio']
                })
        
        return frontier
    
    def optimize_strategy_weights(
        self,
        strategy_returns: pd.DataFrame,
        method: str = 'max_sharpe'
    ) -> Dict[str, Any]:
        """
        优化多个策略的权重分配
        
        Args:
            strategy_returns: DataFrame，列为策略名称，行为日期
            method: 优化方法 ('max_sharpe', 'min_variance', 'risk_parity')
            
        Returns:
            优化结果
        """
        if method == 'max_sharpe':
            return self.optimize_max_sharpe(strategy_returns)
        elif method == 'min_variance':
            return self.optimize_min_variance(strategy_returns)
        elif method == 'risk_parity':
            return self.optimize_risk_parity(strategy_returns)
        else:
            raise ValueError(f"未知的优化方法: {method}")
    
    def get_correlation_matrix(
        self,
        returns: pd.DataFrame
    ) -> pd.DataFrame:
        """
        获取相关性矩阵
        """
        return returns.corr()
    
    def get_covariance_matrix(
        self,
        returns: pd.DataFrame,
        annualized: bool = True
    ) -> pd.DataFrame:
        """
        获取协方差矩阵
        """
        cov = returns.cov()
        if annualized:
            cov = cov * 252
        return cov


class DynamicRebalancer:
    """
    动态再平衡器
    
    根据市场条件动态调整权重
    """
    
    def __init__(
        self,
        rebalance_threshold: float = 0.05,
        rebalance_frequency: str = 'monthly'
    ):
        """
        Args:
            rebalance_threshold: 触发再平衡的偏离阈值
            rebalance_frequency: 再平衡频率 ('daily', 'weekly', 'monthly')
        """
        self.rebalance_threshold = rebalance_threshold
        self.rebalance_frequency = rebalance_frequency
        self.optimizer = PortfolioOptimizer()
    
    def check_rebalance_needed(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float]
    ) -> bool:
        """
        检查是否需要再平衡
        """
        for asset in target_weights:
            current = current_weights.get(asset, 0)
            target = target_weights[asset]
            if abs(current - target) > self.rebalance_threshold:
                return True
        return False
    
    def calculate_trades(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        portfolio_value: float
    ) -> Dict[str, float]:
        """
        计算需要执行的交易量
        """
        trades = {}
        for asset in set(current_weights.keys()) | set(target_weights.keys()):
            current = current_weights.get(asset, 0)
            target = target_weights.get(asset, 0)
            weight_diff = target - current
            trades[asset] = weight_diff * portfolio_value
        return trades


class StrategyWeightOptimizer:
    """
    策略权重优化器
    
    专门用于优化多个交易策略的权重分配
    支持基于历史回测收益的权重优化
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,
        min_weight: float = 0.0,
        max_weight: float = 0.5  # 单策略最大50%权重
    ):
        """
        初始化策略权重优化器
        
        Args:
            risk_free_rate: 无风险利率
            min_weight: 单策略最小权重
            max_weight: 单策略最大权重
        """
        self.optimizer = PortfolioOptimizer(
            risk_free_rate=risk_free_rate,
            constraints={'min_weight': min_weight, 'max_weight': max_weight}
        )
        self.optimal_weights = {}
        self.optimization_history = []
    
    def optimize_from_backtest_results(
        self,
        backtest_results: Dict[str, Dict],
        method: str = 'max_sharpe'
    ) -> Dict[str, Any]:
        """
        基于回测结果优化策略权重
        
        Args:
            backtest_results: 回测结果字典
                格式: {strategy_name: {'returns': pd.Series, 'metrics': {...}}}
            method: 优化方法
            
        Returns:
            优化结果
        """
        # 提取收益率
        returns_dict = {}
        for name, result in backtest_results.items():
            if 'returns' in result and result['returns'] is not None:
                returns_dict[name] = result['returns']
        
        if len(returns_dict) < 2:
            logger.warning("需要至少2个策略才能优化权重")
            return {'success': False, 'error': '策略数量不足'}
        
        # 创建收益率 DataFrame
        returns_df = pd.DataFrame(returns_dict)
        returns_df = returns_df.dropna()
        
        if len(returns_df) < 30:
            logger.warning("历史数据不足")
            return {'success': False, 'error': '历史数据不足'}
        
        # 优化
        result = self.optimizer.optimize_strategy_weights(returns_df, method)
        
        if result['success']:
            self.optimal_weights = result['weights']
            self.optimization_history.append({
                'method': method,
                'weights': result['weights'],
                'sharpe': result['sharpe_ratio']
            })
        
        return result
    
    def optimize_from_signals(
        self,
        strategy_signals: Dict[str, pd.Series],
        price_data: pd.DataFrame,
        method: str = 'max_sharpe'
    ) -> Dict[str, Any]:
        """
        基于策略信号和价格数据优化权重
        
        Args:
            strategy_signals: 策略信号字典 {strategy_name: signals}
            price_data: 价格数据
            method: 优化方法
            
        Returns:
            优化结果
        """
        # 计算每个策略的收益率
        close = price_data['close'] if 'close' in price_data.columns else price_data['Close']
        base_returns = close.pct_change()
        
        strategy_returns = {}
        for name, signals in strategy_signals.items():
            # 策略收益 = 信号 * 基础收益（考虑滞后）
            strat_returns = signals.shift(1) * base_returns
            strat_returns = strat_returns.dropna()
            if len(strat_returns) > 30:
                strategy_returns[name] = strat_returns
        
        if len(strategy_returns) < 2:
            return {'success': False, 'error': '有效策略数量不足'}
        
        returns_df = pd.DataFrame(strategy_returns).dropna()
        return self.optimizer.optimize_strategy_weights(returns_df, method)
    
    def get_weighted_signal(
        self,
        strategy_signals: Dict[str, pd.Series]
    ) -> pd.Series:
        """
        生成加权组合信号
        
        Args:
            strategy_signals: 策略信号字典
            
        Returns:
            加权组合信号
        """
        if not self.optimal_weights:
            # 没有优化权重时使用等权
            weights = {k: 1.0 / len(strategy_signals) for k in strategy_signals}
        else:
            weights = self.optimal_weights
        
        # 对齐索引
        common_index = None
        for signals in strategy_signals.values():
            if common_index is None:
                common_index = signals.index
            else:
                common_index = common_index.intersection(signals.index)
        
        weighted_signals = pd.Series(0.0, index=common_index)
        total_weight = 0
        
        for name, signals in strategy_signals.items():
            weight = weights.get(name, 0)
            if weight > 0:
                weighted_signals += signals.loc[common_index] * weight
                total_weight += weight
        
        if total_weight > 0:
            weighted_signals /= total_weight
        
        # 转换为离散信号
        return pd.Series(
            np.where(weighted_signals > 0.3, 1,
                     np.where(weighted_signals < -0.3, -1, 0)),
            index=common_index
        )
    
    def compare_strategies(
        self,
        strategy_returns: pd.DataFrame
    ) -> pd.DataFrame:
        """
        比较各策略的性能指标
        
        Args:
            strategy_returns: 策略收益率 DataFrame
            
        Returns:
            策略对比 DataFrame
        """
        metrics = []
        
        for strategy in strategy_returns.columns:
            returns = strategy_returns[strategy].dropna()
            
            if len(returns) < 10:
                continue
            
            # 计算各种指标
            annual_return = returns.mean() * 252
            annual_vol = returns.std() * np.sqrt(252)
            sharpe = (annual_return - self.optimizer.risk_free_rate) / annual_vol if annual_vol > 0 else 0
            
            # 最大回撤
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = drawdown.min()
            
            # 胜率
            win_rate = (returns > 0).sum() / len(returns)
            
            # Calmar 比率
            calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
            
            metrics.append({
                'strategy': strategy,
                'annual_return': annual_return,
                'annual_volatility': annual_vol,
                'sharpe_ratio': sharpe,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'calmar_ratio': calmar,
                'optimal_weight': self.optimal_weights.get(strategy, 0)
            })
        
        return pd.DataFrame(metrics).sort_values('sharpe_ratio', ascending=False)


# 全局优化器实例
portfolio_optimizer = PortfolioOptimizer()
strategy_weight_optimizer = StrategyWeightOptimizer()

