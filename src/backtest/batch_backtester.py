"""
批量回测模块

支持并行回测、参数网格搜索和结果聚合
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Callable, Tuple
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
import json
from itertools import product

from src.utils.data_validation import normalize_backtest_results
from src.utils.data_validation import validate_and_fix_backtest_results
from src.analytics.dashboard import PerformanceAnalyzer

logger = logging.getLogger(__name__)


def _run_single_backtest_worker(
    task,
    backtester_factory: Callable,
    strategy_factory: Callable,
    data_fetcher: Callable,
):
    """Top-level worker so batch backtests can use processes when factories are pickleable."""
    import time

    start_time = time.time()
    try:
        data = data_fetcher(task.symbol, task.start_date, task.end_date)
        if data is None or data.empty:
            return BacktestResult(
                task_id=task.task_id,
                research_label=task.research_label,
                symbol=task.symbol,
                strategy_name=task.strategy_name,
                parameters=task.parameters,
                metrics={},
                success=False,
                error="无法获取数据",
            )

        strategy = strategy_factory(task.strategy_name, task.parameters)
        backtester = backtester_factory(
            initial_capital=task.initial_capital,
            commission=task.commission,
            slippage=task.slippage,
        )
        result = backtester.run(strategy, data)
        normalized_metrics = _normalize_metrics(result)
        return BacktestResult(
            task_id=task.task_id,
            research_label=task.research_label,
            symbol=task.symbol,
            strategy_name=task.strategy_name,
            parameters=task.parameters,
            metrics=normalized_metrics,
            success=True,
            execution_time=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"回测执行错误 {task.task_id}: {e}")
        return BacktestResult(
            task_id=task.task_id,
            research_label=task.research_label,
            symbol=task.symbol,
            strategy_name=task.strategy_name,
            parameters=task.parameters,
            metrics={},
            success=False,
            error=str(e),
            execution_time=time.time() - start_time,
        )


class BayesianParameterOptimizer:
    """A lightweight Bayesian-style optimizer for discrete parameter spaces.

    We operate on an explicit candidate set and iteratively score unseen
    candidates with a distance-weighted surrogate plus an exploration bonus.
    This keeps the implementation dependency-light while still avoiding full
    grid evaluation on larger search spaces.
    """

    def __init__(
        self,
        exploration_weight: float = 0.65,
        initial_samples: int = 5,
        max_evaluations: Optional[int] = None,
        random_state: int = 42,
    ):
        self.exploration_weight = exploration_weight
        self.initial_samples = max(1, initial_samples)
        self.max_evaluations = max_evaluations
        self.random_state = random_state

    def optimize(
        self,
        parameter_candidates: List[Dict[str, Any]],
        evaluator: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], float]],
    ) -> Dict[str, Any]:
        if not parameter_candidates:
            metrics, score = evaluator({})
            return {
                "parameters": {},
                "train_metrics": metrics,
                "score": score,
                "evaluated_candidates": 1,
                "optimization_method": "bayesian",
            }

        candidates = [dict(candidate) for candidate in parameter_candidates]
        budget = self.max_evaluations or len(candidates)
        budget = max(1, min(int(budget), len(candidates)))
        rng = np.random.default_rng(self.random_state)

        observations: List[Dict[str, Any]] = []
        remaining_indices = list(range(len(candidates)))
        initial_count = min(self.initial_samples, budget, len(candidates))

        if initial_count:
            initial_indices = rng.choice(remaining_indices, size=initial_count, replace=False)
            for index in sorted(int(value) for value in np.atleast_1d(initial_indices)):
                candidate = candidates[index]
                metrics, score = evaluator(candidate)
                observations.append(
                    {
                        "parameters": candidate,
                        "metrics": metrics,
                        "score": score,
                    }
                )
            remaining_indices = [index for index in remaining_indices if index not in set(int(v) for v in np.atleast_1d(initial_indices))]

        while remaining_indices and len(observations) < budget:
            next_index = max(
                remaining_indices,
                key=lambda candidate_index: self._acquisition_score(
                    candidates[candidate_index],
                    observations,
                    candidates,
                ),
            )
            candidate = candidates[next_index]
            metrics, score = evaluator(candidate)
            observations.append(
                {
                    "parameters": candidate,
                    "metrics": metrics,
                    "score": score,
                }
            )
            remaining_indices.remove(next_index)

        best = max(observations, key=lambda item: item["score"]) if observations else None
        return {
            "parameters": best["parameters"] if best else {},
            "train_metrics": best["metrics"] if best else {},
            "score": best["score"] if best else float("-inf"),
            "evaluated_candidates": len(observations),
            "optimization_method": "bayesian",
        }

    def _acquisition_score(
        self,
        candidate: Dict[str, Any],
        observations: List[Dict[str, Any]],
        all_candidates: List[Dict[str, Any]],
    ) -> float:
        if not observations:
            return float("inf")

        distances = np.asarray(
            [
                self._candidate_distance(candidate, observed["parameters"], all_candidates)
                for observed in observations
            ],
            dtype=float,
        )
        scores = np.asarray([observed["score"] for observed in observations], dtype=float)

        weights = np.exp(-((distances / 0.6) ** 2)) + 1e-9
        weighted_mean = float(np.average(scores, weights=weights))
        weighted_var = float(np.average((scores - weighted_mean) ** 2, weights=weights))
        exploration_bonus = float(np.sqrt(max(weighted_var, 0.0)))
        novelty_bonus = float(np.min(distances)) if len(distances) else 1.0
        return weighted_mean + (self.exploration_weight * exploration_bonus) + (0.15 * novelty_bonus)

    def _candidate_distance(
        self,
        left: Dict[str, Any],
        right: Dict[str, Any],
        all_candidates: List[Dict[str, Any]],
    ) -> float:
        keys = sorted(set(left.keys()) | set(right.keys()))
        if not keys:
            return 0.0

        distances = []
        for key in keys:
            left_value = left.get(key)
            right_value = right.get(key)
            domain = [candidate.get(key) for candidate in all_candidates if key in candidate]
            distances.append(self._value_distance(left_value, right_value, domain))

        return float(np.mean(distances))

    @staticmethod
    def _value_distance(left: Any, right: Any, domain: List[Any]) -> float:
        if left == right:
            return 0.0

        numeric_domain = [
            float(value)
            for value in domain
            if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)
        ]
        if (
            isinstance(left, (int, float, np.integer, np.floating))
            and isinstance(right, (int, float, np.integer, np.floating))
            and not isinstance(left, bool)
            and not isinstance(right, bool)
        ):
            domain_min = min(numeric_domain) if numeric_domain else min(float(left), float(right))
            domain_max = max(numeric_domain) if numeric_domain else max(float(left), float(right))
            span = domain_max - domain_min
            if span <= 0:
                return 0.0
            return min(abs(float(left) - float(right)) / span, 1.0)

        return 1.0


def _normalize_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    validated_result = validate_and_fix_backtest_results(result)
    validated_result.update(PerformanceAnalyzer(validated_result).calculate_metrics())
    normalized_result = normalize_backtest_results(validated_result)
    return normalized_result.get('metrics', normalized_result)


def _create_strategy_instance(strategy_factory: Callable, parameters: Optional[Dict[str, Any]] = None):
    parameters = parameters or {}
    attempts = [
        lambda: strategy_factory(parameters=parameters),
        lambda: strategy_factory(params=parameters),
        lambda: strategy_factory(parameters),
        lambda: strategy_factory(),
    ]

    last_error = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    return strategy_factory()


def _score_metric(metrics: Dict[str, Any], metric: str) -> float:
    value = metrics.get(metric)
    if value is None:
        return float('-inf')

    numeric = float(value)
    if np.isnan(numeric):
        return float('-inf')
    return numeric


@dataclass
class BacktestTask:
    """回测任务"""
    task_id: str
    symbol: str
    strategy_name: str
    parameters: Dict[str, Any]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 100000
    commission: float = 0.001
    slippage: float = 0.001
    research_label: Optional[str] = None


@dataclass
class BacktestResult:
    """回测结果"""
    task_id: str
    symbol: str
    strategy_name: str
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    success: bool
    error: Optional[str] = None
    execution_time: float = 0
    research_label: Optional[str] = None


class BatchBacktester:
    """
    批量回测管理器
    
    支持:
    - 并行执行多个回测任务
    - 参数网格搜索
    - 进度回调
    - 结果排名和聚合
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        use_processes: bool = False
    ):
        """
        初始化批量回测器
        
        Args:
            max_workers: 最大并行工作线程/进程数
            use_processes: 是否使用进程池（CPU密集型）
        """
        self.max_workers = max_workers
        self.use_processes = use_processes
        self.results: List[BacktestResult] = []
        self.progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        设置进度回调函数
        
        Args:
            callback: 函数签名 (completed, total, current_task) -> None
        """
        self.progress_callback = callback
    
    def run_batch(
        self,
        tasks: List[BacktestTask],
        backtester_factory: Callable,
        strategy_factory: Callable,
        data_fetcher: Callable
    ) -> List[BacktestResult]:
        """
        批量执行回测任务
        
        Args:
            tasks: 回测任务列表
            backtester_factory: 创建Backtester实例的工厂函数
            strategy_factory: 创建策略实例的工厂函数(name, params) -> Strategy
            data_fetcher: 获取数据的函数(symbol, start, end) -> DataFrame
            
        Returns:
            回测结果列表
        """
        self.results = []
        total = len(tasks)
        completed = 0
        
        executor_class = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
        
        with executor_class(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(
                    _run_single_backtest_worker,
                    task,
                    backtester_factory,
                    strategy_factory,
                    data_fetcher
                ): task for task in tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    self.results.append(result)
                except Exception as e:
                    logger.error(f"回测任务失败 {task.task_id}: {e}")
                    self.results.append(BacktestResult(
                        task_id=task.task_id,
                        research_label=task.research_label,
                        symbol=task.symbol,
                        strategy_name=task.strategy_name,
                        parameters=task.parameters,
                        metrics={},
                        success=False,
                        error=str(e)
                    ))
                
                completed += 1
                if self.progress_callback:
                    self.progress_callback(completed, total, task.task_id)
        
        return self.results
    
    def _run_single_backtest(
        self,
        task: BacktestTask,
        backtester_factory: Callable,
        strategy_factory: Callable,
        data_fetcher: Callable
    ) -> BacktestResult:
        """执行单个回测"""
        return _run_single_backtest_worker(
            task,
            backtester_factory,
            strategy_factory,
            data_fetcher,
        )
    
    def generate_grid_tasks(
        self,
        symbol: str,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100000
    ) -> List[BacktestTask]:
        """
        生成参数网格搜索任务
        
        Args:
            symbol: 股票代码
            strategy_name: 策略名称
            param_grid: 参数网格 {'param1': [v1, v2], 'param2': [v3, v4]}
            
        Returns:
            任务列表
        """
        from itertools import product
        
        tasks = []
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        
        for i, values in enumerate(product(*param_values)):
            params = dict(zip(param_names, values))
            task = BacktestTask(
                task_id=f"grid_{symbol}_{strategy_name}_{i}",
                research_label=None,
                symbol=symbol,
                strategy_name=strategy_name,
                parameters=params,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital
            )
            tasks.append(task)
        
        return tasks
    
    def get_ranked_results(
        self,
        metric: str = 'sharpe_ratio',
        ascending: bool = False,
        top_n: Optional[int] = None
    ) -> List[BacktestResult]:
        """
        获取排名结果
        
        Args:
            metric: 排名指标
            ascending: 是否升序
            top_n: 返回前N个结果
            
        Returns:
            排序后的结果列表
        """
        successful = [r for r in self.results if r.success]
        
        def get_metric_value(result):
            return result.metrics.get(metric, float('-inf') if not ascending else float('inf'))
        
        sorted_results = sorted(successful, key=get_metric_value, reverse=not ascending)
        
        if top_n:
            return sorted_results[:top_n]
        return sorted_results
    
    def get_summary(self) -> Dict[str, Any]:
        """获取批量回测汇总"""
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        
        if not successful:
            return {
                'total_tasks': len(self.results),
                'successful': 0,
                'failed': len(failed),
                'best_result': None
            }
        
        # 按夏普比率找最佳结果
        best = max(successful, key=lambda r: r.metrics.get('sharpe_ratio', float('-inf')))
        
        # 计算平均指标
        avg_return = np.mean([r.metrics.get('total_return', 0) for r in successful])
        avg_sharpe = np.mean([r.metrics.get('sharpe_ratio', 0) for r in successful])
        avg_time = np.mean([r.execution_time for r in successful])
        
        return {
            'total_tasks': len(self.results),
            'successful': len(successful),
            'failed': len(failed),
            'average_return': avg_return,
            'average_sharpe': avg_sharpe,
            'average_execution_time': avg_time,
            'best_result': {
                'task_id': best.task_id,
                'research_label': best.research_label,
                'strategy': best.strategy_name,
                'parameters': best.parameters,
                'sharpe_ratio': best.metrics.get('sharpe_ratio'),
                'total_return': best.metrics.get('total_return'),
                'max_drawdown': best.metrics.get('max_drawdown'),
                'final_value': best.metrics.get('final_value'),
            }
        }
    
    def export_results(self, filepath: str, format: str = 'json'):
        """
        导出结果
        
        Args:
            filepath: 文件路径
            format: 格式 ('json', 'csv')
        """
        if format == 'json':
            data = [
                {
                    'task_id': r.task_id,
                    'symbol': r.symbol,
                    'strategy_name': r.strategy_name,
                    'parameters': r.parameters,
                    'metrics': r.metrics,
                    'success': r.success,
                    'error': r.error,
                    'execution_time': r.execution_time
                }
                for r in self.results
            ]
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
        elif format == 'csv':
            rows = []
            for r in self.results:
                row = {
                    'task_id': r.task_id,
                    'symbol': r.symbol,
                    'strategy_name': r.strategy_name,
                    'success': r.success,
                    'execution_time': r.execution_time,
                    **{f'param_{k}': v for k, v in r.parameters.items()},
                    **{f'metric_{k}': v for k, v in r.metrics.items()}
                }
                rows.append(row)
            pd.DataFrame(rows).to_csv(filepath, index=False)


class WalkForwardAnalyzer:
    """
    Walk-Forward分析器
    
    将数据分成多个训练/测试窗口进行滚动回测
    """
    
    def __init__(
        self,
        train_period: int = 252,  # 交易日
        test_period: int = 63,
        step_size: int = 21
    ):
        """
        Args:
            train_period: 训练窗口大小（交易日）
            test_period: 测试窗口大小
            step_size: 滚动步长
        """
        self.train_period = train_period
        self.test_period = test_period
        self.step_size = step_size
    
    def generate_windows(
        self,
        data: pd.DataFrame
    ) -> List[Dict[str, pd.DataFrame]]:
        """
        生成训练/测试窗口
        
        Returns:
            [{'train': train_data, 'test': test_data, 'window_id': i}, ...]
        """
        windows = []
        n = len(data)
        
        start = 0
        window_id = 0
        
        while start + self.train_period + self.test_period <= n:
            train_end = start + self.train_period
            test_end = train_end + self.test_period
            
            windows.append({
                'window_id': window_id,
                'train': data.iloc[start:train_end],
                'test': data.iloc[train_end:test_end],
                'train_start': data.index[start],
                'train_end': data.index[train_end - 1],
                'test_start': data.index[train_end],
                'test_end': data.index[test_end - 1]
            })
            
            start += self.step_size
            window_id += 1
        
        return windows
    
    def analyze(
        self,
        data: pd.DataFrame,
        strategy_factory: Callable,
        backtester_factory: Callable,
        parameter_grid: Optional[Dict[str, List[Any]]] = None,
        parameter_candidates: Optional[List[Dict[str, Any]]] = None,
        optimization_metric: str = 'sharpe_ratio',
        optimization_method: str = 'grid',
        optimization_budget: Optional[int] = None,
        monte_carlo_simulations: int = 250,
    ) -> Dict[str, Any]:
        """
        执行Walk-Forward分析
        """
        windows = self.generate_windows(data)
        
        if not windows:
            return {'error': '数据不足以进行Walk-Forward分析'}
        
        results = []
        training_results = []
        selected_parameter_keys = []
        
        for window in windows:
            try:
                optimization = self._optimize_on_train_window(
                    train_data=window['train'],
                    strategy_factory=strategy_factory,
                    backtester_factory=backtester_factory,
                    parameter_grid=parameter_grid,
                    parameter_candidates=parameter_candidates,
                    optimization_metric=optimization_metric,
                    optimization_method=optimization_method,
                    optimization_budget=optimization_budget,
                )
                strategy = _create_strategy_instance(strategy_factory, optimization['parameters'])
                backtester = backtester_factory()
                
                # 在测试集上评估
                test_result = backtester.run(strategy, window['test'])
                normalized_metrics = _normalize_metrics(test_result)
                training_results.append(optimization['train_metrics'])
                selected_parameter_keys.append(json.dumps(optimization['parameters'], sort_keys=True, ensure_ascii=False))
                
                results.append({
                    'window_id': window['window_id'],
                    'train_start': str(window['train_start']),
                    'train_end': str(window['train_end']),
                    'test_start': str(window['test_start']),
                    'test_end': str(window['test_end']),
                    'selected_parameters': optimization['parameters'],
                    'train_metrics': optimization['train_metrics'],
                    'optimization_method': optimization['optimization_method'],
                    'evaluated_candidates': optimization['evaluated_candidates'],
                    'metrics': normalized_metrics,
                })
            except Exception as e:
                logger.error(f"Window {window['window_id']} 分析失败: {e}")
        
        # 汇总结果
        if not results:
            return {'error': '所有窗口分析都失败'}
        
        returns = [r['metrics'].get('total_return', 0) for r in results]
        sharpes = [r['metrics'].get('sharpe_ratio', 0) for r in results]
        train_returns = [metrics.get('total_return', 0) for metrics in training_results]
        train_sharpes = [metrics.get('sharpe_ratio', 0) for metrics in training_results]
        monte_carlo = self._run_monte_carlo_analysis(returns, simulations=monte_carlo_simulations)
        parameter_stability = self._calculate_parameter_stability(selected_parameter_keys)
        overfitting = self._diagnose_overfitting(
            train_returns=train_returns,
            test_returns=returns,
            train_sharpes=train_sharpes,
            test_sharpes=sharpes,
            parameter_stability=parameter_stability,
            monte_carlo=monte_carlo,
        )
        
        return {
            'n_windows': len(results),
            'train_period': self.train_period,
            'test_period': self.test_period,
            'step_size': self.step_size,
            'window_results': results,
            'aggregate_metrics': {
                'average_return': np.mean(returns),
                'return_std': np.std(returns),
                'average_sharpe': np.mean(sharpes),
                'sharpe_std': np.std(sharpes),
                'positive_windows': sum(1 for r in returns if r > 0),
                'negative_windows': sum(1 for r in returns if r <= 0),
                'average_train_return': np.mean(train_returns) if train_returns else 0.0,
                'average_train_sharpe': np.mean(train_sharpes) if train_sharpes else 0.0,
                'parameter_stability': parameter_stability,
                'optimization_metric': optimization_metric,
                'optimization_method': optimization_method,
                'optimization_budget': optimization_budget,
            },
            'monte_carlo': monte_carlo,
            'overfitting_diagnostics': overfitting,
        }

    def _build_parameter_candidates(
        self,
        parameter_grid: Optional[Dict[str, List[Any]]] = None,
        parameter_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        if parameter_candidates:
            return [dict(candidate) for candidate in parameter_candidates]

        if parameter_grid:
            names = list(parameter_grid.keys())
            values = list(parameter_grid.values())
            return [dict(zip(names, candidate_values)) for candidate_values in product(*values)]

        return [{}]

    def _optimize_on_train_window(
        self,
        train_data: pd.DataFrame,
        strategy_factory: Callable,
        backtester_factory: Callable,
        parameter_grid: Optional[Dict[str, List[Any]]] = None,
        parameter_candidates: Optional[List[Dict[str, Any]]] = None,
        optimization_metric: str = 'sharpe_ratio',
        optimization_method: str = 'grid',
        optimization_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        candidates = self._build_parameter_candidates(parameter_grid, parameter_candidates)

        def evaluate(parameters: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
            strategy = _create_strategy_instance(strategy_factory, parameters)
            backtester = backtester_factory()
            train_result = backtester.run(strategy, train_data)
            normalized_metrics = _normalize_metrics(train_result)
            return normalized_metrics, _score_metric(normalized_metrics, optimization_metric)

        if optimization_method == 'bayesian' and len(candidates) > 1:
            optimizer = BayesianParameterOptimizer(
                max_evaluations=optimization_budget,
            )
            return optimizer.optimize(candidates, evaluate)

        best_parameters: Dict[str, Any] = {}
        best_metrics: Optional[Dict[str, Any]] = None
        best_score = float('-inf')

        for parameters in candidates:
            normalized_metrics, score = evaluate(parameters)
            if score > best_score:
                best_score = score
                best_parameters = parameters
                best_metrics = normalized_metrics

        return {
            'parameters': best_parameters,
            'train_metrics': best_metrics or {},
            'score': best_score,
            'evaluated_candidates': len(candidates),
            'optimization_method': 'grid',
        }

    def _run_monte_carlo_analysis(
        self,
        returns: List[float],
        simulations: int = 250,
    ) -> Dict[str, Any]:
        if simulations <= 0 or len(returns) < 2:
            return {
                'simulations': 0,
                'available': False,
            }

        series = np.asarray(returns, dtype=float)
        sample_size = len(series)
        simulated_means = []
        simulated_worst = []

        for _ in range(simulations):
            sample = np.random.choice(series, size=sample_size, replace=True)
            simulated_means.append(float(np.mean(sample)))
            simulated_worst.append(float(np.min(sample)))

        return {
            'simulations': simulations,
            'available': True,
            'mean_return_p10': float(np.percentile(simulated_means, 10)),
            'mean_return_p50': float(np.percentile(simulated_means, 50)),
            'mean_return_p90': float(np.percentile(simulated_means, 90)),
            'worst_window_p10': float(np.percentile(simulated_worst, 10)),
            'negative_mean_probability': float(np.mean(np.asarray(simulated_means) <= 0)),
        }

    def _calculate_parameter_stability(self, selected_parameter_keys: List[str]) -> float:
        if not selected_parameter_keys:
            return 0.0

        counts = {}
        for key in selected_parameter_keys:
            counts[key] = counts.get(key, 0) + 1

        dominant_count = max(counts.values())
        return dominant_count / len(selected_parameter_keys)

    def _diagnose_overfitting(
        self,
        train_returns: List[float],
        test_returns: List[float],
        train_sharpes: List[float],
        test_sharpes: List[float],
        parameter_stability: float,
        monte_carlo: Dict[str, Any],
    ) -> Dict[str, Any]:
        warnings = []
        average_train_return = float(np.mean(train_returns)) if train_returns else 0.0
        average_test_return = float(np.mean(test_returns)) if test_returns else 0.0
        average_train_sharpe = float(np.mean(train_sharpes)) if train_sharpes else 0.0
        average_test_sharpe = float(np.mean(test_sharpes)) if test_sharpes else 0.0

        if average_train_return - average_test_return >= 0.05:
            warnings.append('训练窗口收益显著高于测试窗口，存在样本内过拟合迹象')
        if average_train_sharpe - average_test_sharpe >= 0.5:
            warnings.append('训练窗口夏普比率明显高于样本外结果，参数泛化能力偏弱')
        if parameter_stability < 0.45:
            warnings.append('最优参数在不同训练窗口切换频繁，说明参数稳定性不足')
        if monte_carlo.get('available') and monte_carlo.get('negative_mean_probability', 0) >= 0.35:
            warnings.append('Monte Carlo 模拟中出现负平均收益的概率偏高，结果对样本扰动较敏感')

        if len(warnings) >= 3:
            level = 'high'
        elif len(warnings) >= 1:
            level = 'medium'
        else:
            level = 'low'

        return {
            'level': level,
            'warnings': warnings,
            'train_test_return_gap': average_train_return - average_test_return,
            'train_test_sharpe_gap': average_train_sharpe - average_test_sharpe,
            'parameter_stability': parameter_stability,
        }


# 全局实例
batch_backtester = BatchBacktester()
