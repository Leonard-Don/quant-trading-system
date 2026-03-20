"""
批量回测模块

支持并行回测、参数网格搜索和结果聚合
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import logging
import json

from src.utils.data_validation import normalize_backtest_results
from src.utils.data_validation import validate_and_fix_backtest_results
from src.analytics.dashboard import PerformanceAnalyzer

logger = logging.getLogger(__name__)


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
        
        # 使用线程池（yfinance不支持多进程）
        executor_class = ThreadPoolExecutor
        
        with executor_class(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(
                    self._run_single_backtest,
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
        import time
        start_time = time.time()
        
        try:
            # 获取数据
            data = data_fetcher(task.symbol, task.start_date, task.end_date)
            
            if data is None or data.empty:
                return BacktestResult(
                    task_id=task.task_id,
                    symbol=task.symbol,
                    strategy_name=task.strategy_name,
                    parameters=task.parameters,
                    metrics={},
                    success=False,
                    error="无法获取数据"
                )
            
            # 创建策略
            strategy = strategy_factory(task.strategy_name, task.parameters)
            
            # 创建回测器并执行
            backtester = backtester_factory(
                initial_capital=task.initial_capital,
                commission=task.commission,
                slippage=task.slippage,
            )
            result = backtester.run(strategy, data)
            result = validate_and_fix_backtest_results(result)
            result.update(PerformanceAnalyzer(result).calculate_metrics())
            normalized_result = normalize_backtest_results(result)
            
            execution_time = time.time() - start_time
            
            return BacktestResult(
                task_id=task.task_id,
                symbol=task.symbol,
                strategy_name=task.strategy_name,
                parameters=task.parameters,
                metrics=normalized_result.get('metrics', normalized_result),
                success=True,
                execution_time=execution_time
            )
            
        except Exception as e:
            logger.error(f"回测执行错误 {task.task_id}: {e}")
            return BacktestResult(
                task_id=task.task_id,
                symbol=task.symbol,
                strategy_name=task.strategy_name,
                parameters=task.parameters,
                metrics={},
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
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
                'strategy': best.strategy_name,
                'parameters': best.parameters,
                'sharpe_ratio': best.metrics.get('sharpe_ratio'),
                'total_return': best.metrics.get('total_return')
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
        backtester_factory: Callable
    ) -> Dict[str, Any]:
        """
        执行Walk-Forward分析
        """
        windows = self.generate_windows(data)
        
        if not windows:
            return {'error': '数据不足以进行Walk-Forward分析'}
        
        results = []
        
        for window in windows:
            try:
                # 在训练集上优化（简化版：直接使用默认参数）
                strategy = strategy_factory()
                backtester = backtester_factory()
                
                # 在测试集上评估
                test_result = backtester.run(strategy, window['test'])
                test_result = validate_and_fix_backtest_results(test_result)
                test_result.update(PerformanceAnalyzer(test_result).calculate_metrics())
                normalized_result = normalize_backtest_results(test_result)
                
                results.append({
                    'window_id': window['window_id'],
                    'test_start': str(window['test_start']),
                    'test_end': str(window['test_end']),
                    'metrics': normalized_result.get('metrics', normalized_result)
                })
            except Exception as e:
                logger.error(f"Window {window['window_id']} 分析失败: {e}")
        
        # 汇总结果
        if not results:
            return {'error': '所有窗口分析都失败'}
        
        returns = [r['metrics'].get('total_return', 0) for r in results]
        sharpes = [r['metrics'].get('sharpe_ratio', 0) for r in results]
        
        return {
            'n_windows': len(results),
            'window_results': results,
            'aggregate_metrics': {
                'average_return': np.mean(returns),
                'return_std': np.std(returns),
                'average_sharpe': np.mean(sharpes),
                'sharpe_std': np.std(sharpes),
                'positive_windows': sum(1 for r in returns if r > 0),
                'negative_windows': sum(1 for r in returns if r <= 0)
            }
        }


# 全局实例
batch_backtester = BatchBacktester()
