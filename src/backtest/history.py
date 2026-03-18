"""
回测历史记录服务
保存和管理回测结果历史
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading
import hashlib

from src.utils.config import PROJECT_ROOT
from src.utils.data_validation import ensure_json_serializable, normalize_backtest_results

logger = logging.getLogger(__name__)


class BacktestHistory:
    """回测历史管理器"""

    def __init__(self, storage_path: str = None, max_records: int = 100):
        """
        初始化回测历史管理器
        
        Args:
            storage_path: 存储路径，默认为项目根目录下的 data/backtest_history
            max_records: 最大保存记录数
        """
        if storage_path is None:
            # 使用项目根目录
            storage_path = PROJECT_ROOT / "data" / "backtest_history"
        
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_path / "history.json"
        self.max_records = max_records
        self.history: List[Dict] = []
        self._lock = threading.RLock()
        self._load_history()
        
        logger.info(f"BacktestHistory initialized with {len(self.history)} records")

    def _load_history(self):
        """从文件加载历史记录"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    records = data if isinstance(data, list) else data.get("history", [])
                    repaired = []
                    changed = False
                    for record in records:
                        normalized_record = dict(record)
                        original_result = record.get("result")
                        if isinstance(original_result, dict):
                            normalized_result = ensure_json_serializable(
                                normalize_backtest_results(original_result)
                            )
                            if normalized_result != original_result:
                                changed = True
                            normalized_record["result"] = normalized_result

                            metrics = normalized_result.get("metrics", normalized_result)
                            normalized_record["metrics"] = ensure_json_serializable({
                                "total_return": metrics.get("total_return", 0),
                                "annualized_return": metrics.get("annualized_return", 0),
                                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                                "max_drawdown": metrics.get("max_drawdown", 0),
                                "win_rate": metrics.get("win_rate", 0),
                                "num_trades": metrics.get("num_trades", 0),
                                "total_trades": metrics.get("total_trades", metrics.get("num_trades", 0)),
                                "final_value": metrics.get("final_value", 0),
                                "sortino_ratio": metrics.get("sortino_ratio", 0),
                                "volatility": metrics.get("volatility", 0),
                                "var_95": metrics.get("var_95", 0),
                                "calmar_ratio": metrics.get("calmar_ratio", 0),
                            })
                            if normalized_record.get("metrics") != record.get("metrics"):
                                changed = True

                        repaired.append(normalized_record)

                    self.history = repaired
                    if changed:
                        self._persist()
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
            self.history = []

    def _persist(self):
        """保存历史记录到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to persist history: {e}")

    def _generate_id(self, result: Dict) -> str:
        """生成唯一ID"""
        content = f"{result.get('symbol', '')}_{result.get('strategy', '')}_{datetime.now().isoformat()}"
        return f"bt_{hashlib.md5(content.encode()).hexdigest()[:12]}"

    def save(self, result: Dict[str, Any]) -> str:
        """
        保存回测结果
        
        Args:
            result: 回测结果字典
            
        Returns:
            记录ID
        """
        with self._lock:
            result = ensure_json_serializable(normalize_backtest_results(result))
            record_id = self._generate_id(result)
            
            # 提取关键信息
            metrics = (
                result.get("metrics")
                or result.get("performance_metrics")
                or result
            )
            
            record = {
                "id": record_id,
                "timestamp": datetime.now().isoformat(),
                "symbol": result.get("symbol", "Unknown"),
                "strategy": result.get("strategy", "Unknown"),
                "start_date": result.get("start_date", ""),
                "end_date": result.get("end_date", ""),
                "parameters": result.get("parameters", {}),
                "metrics": ensure_json_serializable({
                    "total_return": metrics.get("total_return", 0),
                    "annualized_return": metrics.get("annualized_return", 0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "win_rate": metrics.get("win_rate", 0),
                    "num_trades": metrics.get("num_trades", 0),
                    "total_trades": metrics.get("total_trades", metrics.get("num_trades", 0)),
                    "final_value": metrics.get("final_value", 0),
                    "sortino_ratio": metrics.get("sortino_ratio", 0),
                    "volatility": metrics.get("volatility", 0),
                    "var_95": metrics.get("var_95", 0),
                    "calmar_ratio": metrics.get("calmar_ratio", 0)
                }),
                "result": result.get("result") or result.get("backtest_result") or result,
            }
            
            # 添加到历史记录
            self.history.insert(0, record)
            
            # 限制记录数量
            if len(self.history) > self.max_records:
                self.history = self.history[:self.max_records]
            
            # 持久化
            self._persist()
            
            logger.info(f"Saved backtest record: {record_id}")
            return record_id

    def get_history(self, limit: int = 20, symbol: str = None, strategy: str = None) -> List[Dict]:
        """
        获取历史记录
        
        Args:
            limit: 返回记录数量限制
            symbol: 按股票代码过滤
            strategy: 按策略名称过滤
            
        Returns:
            历史记录列表
        """
        with self._lock:
            filtered = self.history
            
            if symbol:
                filtered = [r for r in filtered if r.get("symbol", "").upper() == symbol.upper()]
            
            if strategy:
                filtered = [r for r in filtered if r.get("strategy", "").lower() == strategy.lower()]
            
            return filtered[:limit]

    def get_by_id(self, record_id: str) -> Optional[Dict]:
        """
        根据ID获取记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            记录详情或 None
        """
        with self._lock:
            for record in self.history:
                if record.get("id") == record_id:
                    return record
            return None

    def delete(self, record_id: str) -> bool:
        """
        删除记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否删除成功
        """
        with self._lock:
            original_length = len(self.history)
            self.history = [r for r in self.history if r.get("id") != record_id]
            
            if len(self.history) < original_length:
                self._persist()
                logger.info(f"Deleted backtest record: {record_id}")
                return True
            return False

    def clear(self):
        """清空所有历史记录"""
        with self._lock:
            self.history = []
            self._persist()
            logger.info("Cleared all backtest history")

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取历史统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            if not self.history:
                return {
                    "total_records": 0,
                    "strategies": {},
                    "symbols": {},
                    "avg_return": 0,
                    "strategy_count": 0,
                    "latest_record_at": None,
                }
            
            strategies = {}
            symbols = {}
            total_return = 0
            
            for record in self.history:
                strategy = record.get("strategy", "Unknown")
                symbol = record.get("symbol", "Unknown")
                
                strategies[strategy] = strategies.get(strategy, 0) + 1
                symbols[symbol] = symbols.get(symbol, 0) + 1
                total_return += record.get("metrics", {}).get("total_return", 0)
            
            return {
                "total_records": len(self.history),
                "strategies": strategies,
                "symbols": symbols,
                "avg_return": total_return / len(self.history) if self.history else 0,
                "strategy_count": len(strategies),
                "latest_record_at": self.history[0].get("timestamp") if self.history else None,
                "most_tested_symbol": max(symbols, key=symbols.get) if symbols else None,
                "most_used_strategy": max(strategies, key=strategies.get) if strategies else None
            }


# 全局实例
backtest_history = BacktestHistory()
