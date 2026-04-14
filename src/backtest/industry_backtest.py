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
from src.data.data_manager import DataManager
from .base_backtester import BaseBacktester
from .metrics import (
    calculate_returns,
    calculate_var,
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
    diagnostics: Optional[Dict[str, Any]] = None


class IndustryBacktester(BaseBacktester):
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
    DEFAULT_BENCHMARK = "SPY"
    DEFAULT_INDUSTRY_PROXY_MAP = {
        "电子": [
            {"symbol": "159995", "name": "芯片 ETF", "market_cap": 1_200_000_000},
            {"symbol": "512480", "name": "半导体 ETF", "market_cap": 1_100_000_000},
            {"symbol": "159801", "name": "电子 ETF", "market_cap": 950_000_000},
            {"symbol": "XLK", "name": "科技精选行业 ETF", "market_cap": 1_000_000_000},
            {"symbol": "SMH", "name": "半导体 ETF", "market_cap": 900_000_000},
            {"symbol": "QQQ", "name": "纳指100 ETF", "market_cap": 800_000_000},
        ],
        "医药生物": [
            {"symbol": "512010", "name": "医药 ETF", "market_cap": 1_100_000_000},
            {"symbol": "159938", "name": "医药卫生 ETF", "market_cap": 980_000_000},
            {"symbol": "512170", "name": "医疗 ETF", "market_cap": 900_000_000},
            {"symbol": "XLV", "name": "医疗保健 ETF", "market_cap": 900_000_000},
            {"symbol": "IBB", "name": "生物科技 ETF", "market_cap": 800_000_000},
            {"symbol": "XBI", "name": "生物科技成长 ETF", "market_cap": 700_000_000},
        ],
        "新能源": [
            {"symbol": "516160", "name": "新能源 ETF", "market_cap": 1_050_000_000},
            {"symbol": "159806", "name": "新能车 ETF", "market_cap": 960_000_000},
            {"symbol": "516150", "name": "光伏 ETF", "market_cap": 900_000_000},
            {"symbol": "ICLN", "name": "全球清洁能源 ETF", "market_cap": 850_000_000},
            {"symbol": "TAN", "name": "太阳能 ETF", "market_cap": 750_000_000},
            {"symbol": "LIT", "name": "锂电池 ETF", "market_cap": 700_000_000},
        ],
        "金融": [
            {"symbol": "512800", "name": "银行 ETF", "market_cap": 1_000_000_000},
            {"symbol": "512070", "name": "证券保险 ETF", "market_cap": 900_000_000},
            {"symbol": "159933", "name": "金融 ETF", "market_cap": 860_000_000},
            {"symbol": "XLF", "name": "金融 ETF", "market_cap": 950_000_000},
            {"symbol": "KRE", "name": "区域银行 ETF", "market_cap": 650_000_000},
            {"symbol": "VFH", "name": "金融先锋 ETF", "market_cap": 600_000_000},
        ],
    }
    
    def __init__(
        self,
        industry_analyzer=None,
        leader_scorer=None,
        data_manager: Optional[DataManager] = None,
        data_provider: Optional[Any] = None,
        initial_capital: float = 1000000,
        commission_rate: float = 0.001,
        slippage: float = 0.001,
        benchmark_symbol: str = DEFAULT_BENCHMARK,
        industry_proxy_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        strict_data_validation: bool = True,
        ranking_lookback_days: int = 63,
        min_price_observations: int = 10,
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
        super().__init__(
            initial_capital=initial_capital,
            commission=commission_rate,
            slippage=slippage,
        )
        self.analyzer = industry_analyzer
        self.scorer = leader_scorer
        self.data_manager = data_manager or DataManager()
        self.data_provider = data_provider
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.benchmark_symbol = benchmark_symbol
        self.industry_proxy_map = industry_proxy_map or self.DEFAULT_INDUSTRY_PROXY_MAP.copy()
        self.strict_data_validation = strict_data_validation
        self.ranking_lookback_days = ranking_lookback_days
        self.min_price_observations = min_price_observations
        self._bootstrap_industry_components()
        
        # 回测状态
        self._positions: Dict[str, float] = {}
        self._cash: float = initial_capital
        self._equity_history: List[Tuple[datetime, float]] = []
        self._trades: List[Dict] = []
        self._price_cache: Dict[str, pd.Series] = {}
        self._run_diagnostics: Dict[str, Any] = {}

    def _bootstrap_industry_components(self) -> None:
        """Auto-wire analyzer/scorer from a real market-data provider when possible."""
        provider = self.data_provider or self._resolve_industry_provider()
        if provider is None:
            return

        self.data_provider = provider

        if self.analyzer is None:
            try:
                from src.analytics.industry_analyzer import IndustryAnalyzer

                self.analyzer = IndustryAnalyzer(provider)
            except Exception as exc:
                logger.warning(f"Failed to initialize IndustryAnalyzer: {exc}")

        if self.scorer is None:
            try:
                from src.analytics.leader_stock_scorer import LeaderStockScorer

                self.scorer = LeaderStockScorer(provider)
            except Exception as exc:
                logger.warning(f"Failed to initialize LeaderStockScorer: {exc}")

    def _resolve_industry_provider(self) -> Optional[Any]:
        """Find a provider capable of industry analytics, preferring real sources."""
        if self.analyzer is not None and getattr(self.analyzer, "provider", None) is not None:
            return self.analyzer.provider
        if self.scorer is not None and getattr(self.scorer, "provider", None) is not None:
            return self.scorer.provider

        # Respect custom data managers used in tests or local simulations.
        if not isinstance(self.data_manager, DataManager):
            return None

        provider_factory = getattr(self.data_manager, "provider_factory", None)
        if provider_factory is not None:
            for provider_name in ("akshare", "us_stock", "yahoo"):
                try:
                    provider = provider_factory.get_provider(provider_name)
                    if self._provider_supports_industry(provider):
                        return provider
                except Exception:
                    continue

        try:
            from src.data.providers.akshare_provider import AKShareProvider

            provider = AKShareProvider()
            if self._provider_supports_industry(provider):
                return provider
        except Exception as exc:
            logger.debug(f"Unable to bootstrap AKShareProvider for industry backtest: {exc}")

        return None

    @staticmethod
    def _provider_supports_industry(provider: Any) -> bool:
        required_methods = (
            "get_industry_money_flow",
            "get_stock_list_by_industry",
            "get_stock_financial_data",
        )
        return all(callable(getattr(provider, method, None)) for method in required_methods)

    def run(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """BaseBacktester-compatible wrapper around ``run_backtest``."""
        result = self.run_backtest(*args, **kwargs)
        return {
            "total_return": result.total_return,
            "annualized_return": result.annualized_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "benchmark_return": result.benchmark_return,
            "excess_return": result.excess_return,
            "trade_count": result.trade_count,
            "daily_returns": result.daily_returns,
            "equity_curve": result.equity_curve,
            "diagnostics": result.diagnostics or {},
        }
    
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
        self._price_cache = {}
        self._run_diagnostics = {
            "provider_name": type(self.data_provider).__name__ if self.data_provider is not None else None,
            "provider_bootstrapped": self.data_provider is not None,
            "strict_data_validation": self.strict_data_validation,
            "ranking_lookback_days": self.ranking_lookback_days,
            "min_price_observations": self.min_price_observations,
            "industry_selection_source": None,
            "leader_selection_source": None,
            "proxy_ranking_used": False,
            "fallback_defaults_used": False,
            "symbols_requested": 0,
            "symbols_loaded": 0,
            "symbols_missing": [],
            "benchmark_symbol": self.benchmark_symbol,
            "benchmark_data_available": False,
        }
    
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
        hot_industries = self._get_hot_industries(date, top_industries)
        
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
            target_stocks = self._rank_proxy_constituents(
                hot_industries=hot_industries,
                date=date,
                stocks_per_industry=stocks_per_industry,
            )
        else:
            self._run_diagnostics["leader_selection_source"] = "scorer"
        
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
        
        优先使用真实历史价格；如果没有精确匹配日期，则取最近一个可用收盘价。
        """
        price_series = self._load_price_series(symbol, date)
        if price_series.empty:
            return 0.0

        eligible = price_series[price_series.index <= pd.Timestamp(date)]
        if eligible.empty:
            eligible = price_series
        return float(eligible.iloc[-1])
    
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
                equity_curve=pd.Series(),
                diagnostics={**self._run_diagnostics},
            )
        
        # 转换为 Series
        dates = [d for d, _ in daily_returns]
        returns = [r for _, r in daily_returns]
        returns_series = pd.Series(returns, index=dates)
        
        # 资金曲线
        equity_dates = [d for d, _ in self._equity_history]
        equity_values = [v for _, v in self._equity_history]
        equity_curve = pd.Series(equity_values, index=equity_dates)
        
        common_metrics = self.calculate_common_metrics(equity_curve)
        total_return = common_metrics["total_return"]
        annualized_return = common_metrics["annualized_return"]
        sharpe_ratio = common_metrics["sharpe_ratio"]
        max_drawdown = common_metrics["max_drawdown"]
        sortino_ratio = common_metrics["sortino_ratio"]
        volatility = common_metrics["volatility"]
        var_95 = calculate_var(returns_series)
        calmar_ratio = common_metrics["calmar_ratio"]
        
        # 胜率
        winning_days = sum(1 for r in returns if r > 0)
        win_rate = winning_days / len(returns) if returns else 0
        
        benchmark_return = self._calculate_benchmark_return(
            start_date=equity_curve.index[0],
            end_date=equity_curve.index[-1],
            benchmark_symbol=self.benchmark_symbol,
        )
        diagnostics = {
            **self._run_diagnostics,
            "provider_name": type(self.data_provider).__name__ if self.data_provider is not None else None,
            "proxy_coverage_ratio": (
                float(self._run_diagnostics.get("symbols_loaded", 0))
                / max(float(self._run_diagnostics.get("symbols_requested", 0) or 1), 1.0)
            ),
            "active_positions": len(self._positions),
        }
        
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
            var_95=var_95,
            diagnostics=diagnostics,
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
        
        benchmark_return = self._calculate_benchmark_return(
            start_date=result.equity_curve.index[0] if not result.equity_curve.empty else None,
            end_date=result.equity_curve.index[-1] if not result.equity_curve.empty else None,
            benchmark_symbol=benchmark,
        )
        if benchmark_return == 0 and result.benchmark_return:
            benchmark_return = result.benchmark_return
        
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

    def _get_hot_industries(self, date: datetime, top_industries: int) -> List[Dict[str, Any]]:
        hot_industries: List[Dict[str, Any]] = []
        if self.analyzer:
            try:
                hot_industries = self.analyzer.rank_industries(top_n=top_industries)
            except Exception as exc:
                logger.warning(f"Failed to get hot industries: {exc}")

        if hot_industries:
            self._run_diagnostics["industry_selection_source"] = "analyzer"
            return hot_industries

        hot_industries = self._rank_industries_from_proxies(
            date=date,
            top_industries=top_industries,
        )
        if hot_industries:
            self._run_diagnostics["industry_selection_source"] = "proxy"
            self._run_diagnostics["proxy_ranking_used"] = True
            return hot_industries

        if self.strict_data_validation:
            logger.warning("No valid industry ranking data available; skipping rebalance")
            self._run_diagnostics["industry_selection_source"] = "none"
            return []

        self._run_diagnostics["industry_selection_source"] = "default"
        self._run_diagnostics["fallback_defaults_used"] = True
        return self._get_default_hot_industries(top_industries)

    def _get_default_hot_industries(self, top_industries: int) -> List[Dict[str, Any]]:
        industries = []
        for index, industry_name in enumerate(list(self.industry_proxy_map.keys())[:top_industries]):
            industries.append({
                "industry_name": industry_name,
                "score": round(max(0.4, 0.85 - index * 0.08), 3),
            })
        return industries

    def _rank_industries_from_proxies(
        self,
        *,
        date: datetime,
        top_industries: int,
    ) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        for industry_name, proxies in self.industry_proxy_map.items():
            proxy_scores: List[float] = []
            for proxy in proxies:
                proxy_frame = self._load_symbol_frame(proxy["symbol"], date)
                score = self._score_proxy_frame(proxy_frame)
                if score is not None:
                    proxy_scores.append(score)
            if proxy_scores:
                ranked.append(
                    {
                        "industry_name": industry_name,
                        "score": round(float(np.mean(proxy_scores)), 4),
                        "data_points": len(proxy_scores),
                    }
                )

        ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ranked[:top_industries]

    def _rank_proxy_constituents(
        self,
        *,
        hot_industries: List[Dict[str, Any]],
        date: datetime,
        stocks_per_industry: int,
    ) -> List[Dict[str, Any]]:
        proxies: List[Dict[str, Any]] = []
        for industry in hot_industries:
            industry_name = str(industry.get("industry_name", "")).strip()
            ranked_candidates: List[Dict[str, Any]] = []
            for index, proxy in enumerate(self.industry_proxy_map.get(industry_name, [])):
                proxy_frame = self._load_symbol_frame(proxy["symbol"], date)
                score = self._score_proxy_frame(proxy_frame)
                if score is None and self.strict_data_validation:
                    continue
                ranked_candidates.append(
                    {
                        "symbol": proxy["symbol"],
                        "name": proxy.get("name", proxy["symbol"]),
                        "industry": industry_name,
                        "market_cap": proxy.get(
                            "market_cap", 1_000_000_000 - index * 50_000_000
                        ),
                        "total_score": round(
                            (
                                float(score)
                                if score is not None
                                else float(industry.get("score", 0.5))
                            )
                            * 100,
                            2,
                        ),
                    }
                )

            ranked_candidates.sort(
                key=lambda item: item.get("total_score", 0), reverse=True
            )
            for candidate in ranked_candidates[:stocks_per_industry]:
                proxies.append(
                    candidate
                )
        if proxies:
            self._run_diagnostics["leader_selection_source"] = "proxy"
        return proxies

    def _load_symbol_frame(self, symbol: str, anchor_date: datetime) -> pd.DataFrame:
        normalized_symbol = str(symbol).strip().upper()
        self._run_diagnostics["symbols_requested"] = int(self._run_diagnostics.get("symbols_requested", 0)) + 1

        def _mark_missing() -> None:
            missing = self._run_diagnostics.setdefault("symbols_missing", [])
            if normalized_symbol not in missing:
                missing.append(normalized_symbol)

        try:
            frame = self.data_manager.get_historical_data(
                normalized_symbol,
                start_date=anchor_date - timedelta(days=400),
                end_date=anchor_date + timedelta(days=5),
            )
        except Exception as exc:
            logger.warning(f"Failed to fetch history for {symbol}: {exc}")
            _mark_missing()
            return pd.DataFrame()

        if frame.empty:
            _mark_missing()
            return pd.DataFrame()

        normalized = frame.copy()
        normalized.columns = [str(col).lower() for col in normalized.columns]
        if "close" not in normalized.columns:
            _mark_missing()
            return pd.DataFrame()
        normalized.index = pd.to_datetime(normalized.index)
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        if "volume" in normalized.columns:
            normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
        cleaned = normalized.dropna(subset=["close"]).sort_index()
        if cleaned.empty:
            _mark_missing()
            return cleaned
        self._run_diagnostics["symbols_loaded"] = int(self._run_diagnostics.get("symbols_loaded", 0)) + 1
        return cleaned

    def _score_proxy_frame(self, frame: pd.DataFrame) -> Optional[float]:
        if frame.empty or len(frame) < self.min_price_observations:
            return None

        window = frame.tail(self.ranking_lookback_days)
        if len(window) < self.min_price_observations:
            return None

        prices = window["close"].astype(float)
        if prices.iloc[0] <= 0:
            return None

        momentum = float(prices.iloc[-1] / prices.iloc[0] - 1)
        returns = prices.pct_change().dropna()
        realized_vol = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        avg_volume = float(window.get("volume", pd.Series(dtype=float)).fillna(0).mean())
        liquidity_boost = np.log1p(max(avg_volume, 0.0)) / 100 if avg_volume > 0 else 0.0
        return momentum - realized_vol + liquidity_boost

    def _load_price_series(self, symbol: str, anchor_date: datetime) -> pd.Series:
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_symbol in self._price_cache:
            return self._price_cache[normalized_symbol]

        data = self._load_symbol_frame(normalized_symbol, anchor_date)
        if data.empty:
            self._price_cache[normalized_symbol] = pd.Series(dtype="float64")
            return self._price_cache[normalized_symbol]

        close_series = pd.to_numeric(data["close"], errors="coerce").dropna()
        close_series.index = pd.to_datetime(close_series.index)
        if getattr(close_series.index, "tz", None) is not None:
            close_series.index = close_series.index.tz_localize(None)
        self._price_cache[normalized_symbol] = close_series.sort_index()
        return self._price_cache[normalized_symbol]

    def _calculate_benchmark_return(
        self,
        *,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        benchmark_symbol: str,
    ) -> float:
        if not start_date or not end_date:
            return 0.0

        benchmark_series = self._load_price_series(benchmark_symbol, end_date)
        if benchmark_series.empty:
            return 0.0
        self._run_diagnostics["benchmark_data_available"] = True

        normalized_start = pd.Timestamp(start_date).tz_localize(None) if pd.Timestamp(start_date).tzinfo else pd.Timestamp(start_date)
        normalized_end = pd.Timestamp(end_date).tz_localize(None) if pd.Timestamp(end_date).tzinfo else pd.Timestamp(end_date)
        benchmark_series = benchmark_series[
            (benchmark_series.index >= normalized_start)
            & (benchmark_series.index <= normalized_end)
        ]
        if len(benchmark_series) < 2:
            return 0.0

        return float(calculate_returns(benchmark_series))
