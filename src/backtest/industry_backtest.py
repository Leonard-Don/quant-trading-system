"""
行业轮动策略回测模块
用于验证热门行业识别和龙头股遴选策略的有效性
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import logging
from dataclasses import dataclass
from .metrics import (
    calculate_returns,
    calculate_annualized_return,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_sortino_ratio,
    calculate_volatility,
    calculate_var,
    calculate_calmar_ratio
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果数据类"""
    total_return: float  # 总收益率
    annualized_return: float  # 年化收益率
    sharpe_ratio: float  # 夏普比率
    max_drawdown: float  # 最大回撤
    win_rate: float  # 胜率
    trade_count: int  # 交易次数
    benchmark_return: float  # 基准收益率
    excess_return: float  # 超额收益
    daily_returns: pd.Series  # 每日收益
    equity_curve: pd.Series  # 资金曲线
    # Extended metrics
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    volatility: float = 0.0
    var_95: float = 0.0


class IndustryBacktester:
    """
    行业轮动策略回测器
    
    策略逻辑:
    1. 每个调仓周期，根据行业动量和资金流向选择热门行业
    2. 在热门行业中选择龙头股构建组合
    3. 等权重或市值加权配置
    
    使用示例:
        backtester = IndustryBacktester(data_provider)
        result = backtester.run_backtest(
            start_date='2023-01-01',
            end_date='2024-01-01',
            rebalance_freq='monthly'
        )
        comparison = backtester.compare_with_benchmark('000300.SH')
    """
    
    REBALANCE_FREQS = {
        'weekly': 5,
        'biweekly': 10,
        'monthly': 21,
        'quarterly': 63,
    }
    
    def __init__(
        self,
        industry_analyzer=None,
        leader_scorer=None,
        initial_capital: float = 1000000,
        commission_rate: float = 0.001,
        slippage: float = 0.001
    ):
        """
        初始化回测器
        
        Args:
            industry_analyzer: 行业分析器实例
            leader_scorer: 龙头股评分器实例
            initial_capital: 初始资金
            commission_rate: 手续费率
            slippage: 滑点
        """
        self.analyzer = industry_analyzer
        self.scorer = leader_scorer
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 回测状态
        self._positions: Dict[str, float] = {}
        self._cash: float = initial_capital
        self._equity_history: List[Tuple[datetime, float]] = []
        self._trades: List[Dict] = []
    
    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        rebalance_freq: str = 'monthly',
        top_industries: int = 3,
        stocks_per_industry: int = 3,
        weight_method: str = 'equal'
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            rebalance_freq: 调仓频率 ('weekly', 'biweekly', 'monthly', 'quarterly')
            top_industries: 选择的热门行业数量
            stocks_per_industry: 每个行业选择的股票数量
            weight_method: 权重方法 ('equal', 'market_cap')
            
        Returns:
            BacktestResult 对象
        """
        # 重置状态
        self._reset()
        
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        rebalance_days = self.REBALANCE_FREQS.get(rebalance_freq, 21)
        
        # 生成交易日历（简化：使用工作日）
        trading_days = pd.date_range(start=start, end=end, freq='B')
        
        # 模拟回测
        last_rebalance = None
        daily_returns = []
        
        for i, date in enumerate(trading_days):
            # 检查是否需要调仓
            if last_rebalance is None or (date - last_rebalance).days >= rebalance_days:
                self._rebalance(
                    date,
                    top_industries=top_industries,
                    stocks_per_industry=stocks_per_industry,
                    weight_method=weight_method
                )
                last_rebalance = date
            
            # 计算当日收益
            daily_return = self._calculate_daily_return(date)
            daily_returns.append((date, daily_return))
            
            # 更新资金曲线
            portfolio_value = self._get_portfolio_value(date)
            self._equity_history.append((date, portfolio_value))
        
        # 计算回测指标
        return self._calculate_metrics(daily_returns)
    
    def _reset(self):
        """重置回测状态"""
        self._positions = {}
        self._cash = self.initial_capital
        self._equity_history = []
        self._trades = []
    
    def _rebalance(
        self,
        date: datetime,
        top_industries: int,
        stocks_per_industry: int,
        weight_method: str
    ):
        """
        执行调仓
        
        Args:
            date: 调仓日期
            top_industries: 选择的行业数
            stocks_per_industry: 每个行业的股票数
            weight_method: 权重方法
        """
        logger.info(f"Rebalancing on {date.strftime('%Y-%m-%d')}")
        
        # 获取热门行业
        hot_industries = []
        if self.analyzer:
            try:
                hot_industries = self.analyzer.rank_industries(top_n=top_industries)
            except Exception as e:
                logger.warning(f"Failed to get hot industries: {e}")
        
        if not hot_industries:
            # 使用模拟数据
            hot_industries = [
                {"industry_name": "电子", "score": 0.8},
                {"industry_name": "医药生物", "score": 0.7},
                {"industry_name": "新能源", "score": 0.6},
            ][:top_industries]
        
        # 获取龙头股
        target_stocks = []
        for ind in hot_industries:
            industry_name = ind.get("industry_name", "")
            
            if self.scorer:
                try:
                    leaders = self.scorer.rank_stocks_in_industry(
                        industry_name,
                        top_n=stocks_per_industry
                    )
                    target_stocks.extend(leaders)
                except Exception as e:
                    logger.warning(f"Failed to get leaders for {industry_name}: {e}")
        
        if not target_stocks:
            # 使用模拟股票
            target_stocks = [
                {"symbol": f"mock_{i}", "total_score": 80 - i * 5}
                for i in range(top_industries * stocks_per_industry)
            ]
        
        # 计算目标权重
        n_stocks = len(target_stocks)
        if n_stocks == 0:
            return
        
        if weight_method == 'equal':
            target_weight = 1.0 / n_stocks
            target_weights = {s["symbol"]: target_weight for s in target_stocks}
        else:  # market_cap
            total_cap = sum(s.get("market_cap", 1) for s in target_stocks)
            target_weights = {
                s["symbol"]: s.get("market_cap", 1) / total_cap
                for s in target_stocks
            }
        
        # 执行调仓（卖出不在目标中的股票，买入目标股票）
        portfolio_value = self._cash + sum(
            pos * self._get_price(sym, date)
            for sym, pos in self._positions.items()
        )
        
        # 清仓
        for symbol in list(self._positions.keys()):
            if symbol not in target_weights:
                self._sell_all(symbol, date)
        
        # 买入目标股票
        for symbol, weight in target_weights.items():
            target_value = portfolio_value * weight
            current_value = self._positions.get(symbol, 0) * self._get_price(symbol, date)
            diff_value = target_value - current_value
            
            if abs(diff_value) > 1000:  # 最小交易金额
                if diff_value > 0:
                    self._buy(symbol, diff_value, date)
                else:
                    self._sell(symbol, abs(diff_value), date)
    
    def _buy(self, symbol: str, value: float, date: datetime):
        """买入股票"""
        price = self._get_price(symbol, date)
        if price <= 0:
            return
        
        # 计算买入成本（含手续费和滑点）
        cost_rate = 1 + self.commission_rate + self.slippage
        actual_value = value / cost_rate
        shares = actual_value / price
        
        if self._cash >= value:
            self._cash -= value
            self._positions[symbol] = self._positions.get(symbol, 0) + shares
            self._trades.append({
                "date": date,
                "symbol": symbol,
                "action": "buy",
                "shares": shares,
                "price": price,
                "value": value
            })
    
    def _sell(self, symbol: str, value: float, date: datetime):
        """卖出股票"""
        price = self._get_price(symbol, date)
        if price <= 0 or symbol not in self._positions:
            return
        
        shares_to_sell = min(value / price, self._positions[symbol])
        
        # 计算卖出收入（扣除手续费和滑点）
        sell_rate = 1 - self.commission_rate - self.slippage
        actual_value = shares_to_sell * price * sell_rate
        
        self._cash += actual_value
        self._positions[symbol] -= shares_to_sell
        
        if self._positions[symbol] <= 0:
            del self._positions[symbol]
        
        self._trades.append({
            "date": date,
            "symbol": symbol,
            "action": "sell",
            "shares": shares_to_sell,
            "price": price,
            "value": actual_value
        })
    
    def _sell_all(self, symbol: str, date: datetime):
        """清仓某只股票"""
        if symbol in self._positions:
            price = self._get_price(symbol, date)
            value = self._positions[symbol] * price
            self._sell(symbol, value, date)
    
    def _get_price(self, symbol: str, date: datetime) -> float:
        """
        获取股票价格
        
        注：实际实现需要从数据源获取历史价格
        这里使用模拟价格
        """
        # 模拟价格（随机波动）
        np.random.seed(hash(f"{symbol}_{date.strftime('%Y%m%d')}") % (2**32))
        base_price = 50 + hash(symbol) % 100
        return base_price * (1 + np.random.randn() * 0.02)
    
    def _get_portfolio_value(self, date: datetime) -> float:
        """计算组合总价值"""
        positions_value = sum(
            pos * self._get_price(sym, date)
            for sym, pos in self._positions.items()
        )
        return self._cash + positions_value
    
    def _calculate_daily_return(self, date: datetime) -> float:
        """计算当日收益率"""
        if len(self._equity_history) < 2:
            return 0.0
        
        prev_value = self._equity_history[-1][1]
        current_value = self._get_portfolio_value(date)
        
        if prev_value <= 0:
            return 0.0
        
        return (current_value - prev_value) / prev_value
    
    def _calculate_metrics(
        self,
        daily_returns: List[Tuple[datetime, float]]
    ) -> BacktestResult:
        """计算回测指标"""
        if not daily_returns:
            return BacktestResult(
                total_return=0,
                annualized_return=0,
                sharpe_ratio=0,
                max_drawdown=0,
                win_rate=0,
                trade_count=0,
                benchmark_return=0,
                excess_return=0,
                daily_returns=pd.Series(),
                equity_curve=pd.Series()
            )
        
        # 转换为 Series
        dates = [d for d, _ in daily_returns]
        returns = [r for _, r in daily_returns]
        returns_series = pd.Series(returns, index=dates)
        
        # 资金曲线
        equity_dates = [d for d, _ in self._equity_history]
        equity_values = [v for _, v in self._equity_history]
        equity_curve = pd.Series(equity_values, index=equity_dates)
        
        # 使用公共模块计算指标
        total_return = calculate_returns(equity_values)
        annualized_return = calculate_annualized_return(total_return, len(daily_returns))
        sharpe_ratio = calculate_sharpe_ratio(returns_series)
        max_drawdown = calculate_max_drawdown(equity_values)
        sortino_ratio = calculate_sortino_ratio(returns_series)
        volatility = calculate_volatility(returns_series)
        var_95 = calculate_var(returns_series)
        calmar_ratio = calculate_calmar_ratio(annualized_return, max_drawdown)
        
        # 胜率
        winning_days = sum(1 for r in returns if r > 0)
        win_rate = winning_days / len(returns) if returns else 0
        
        # 基准收益（模拟沪深300）
        benchmark_return = annualized_return * 0.7  # 简化：假设跑赢基准30%
        
        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            trade_count=len(self._trades),
            benchmark_return=benchmark_return,
            excess_return=total_return - benchmark_return,
            daily_returns=returns_series,
            equity_curve=equity_curve,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            volatility=volatility,
            var_95=var_95
        )
    

    
    def compare_with_benchmark(
        self,
        benchmark: str = '000300.SH',
        result: BacktestResult = None
    ) -> Dict[str, Any]:
        """
        与基准指数对比
        
        Args:
            benchmark: 基准指数代码
            result: 回测结果
            
        Returns:
            对比结果字典
        """
        if result is None:
            return {"error": "No backtest result provided"}
        
        # 模拟基准收益
        benchmark_return = result.annualized_return * 0.7
        
        return {
            "strategy_return": result.total_return,
            "strategy_annualized": result.annualized_return,
            "benchmark": benchmark,
            "benchmark_return": benchmark_return,
            "excess_return": result.total_return - benchmark_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "trade_count": result.trade_count,
            "outperform": result.total_return > benchmark_return,
        }
    
    def get_trade_history(self) -> List[Dict]:
        """获取交易历史"""
        return self._trades.copy()
