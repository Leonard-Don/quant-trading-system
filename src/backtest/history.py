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
import subprocess
import sqlite3

from src.utils.config import PROJECT_ROOT
from src.utils.data_validation import ensure_json_serializable, normalize_backtest_results

logger = logging.getLogger(__name__)

SUMMARY_METRIC_FIELDS = [
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "num_trades",
    "total_trades",
    "final_value",
    "sortino_ratio",
    "volatility",
    "var_95",
    "calmar_ratio",
    "net_profit",
    "profit_factor",
    "recovery_factor",
    "expectancy",
    "avg_win",
    "avg_loss",
    "total_profit",
    "total_loss",
    "loss_rate",
    "avg_holding_days",
    "total_completed_trades",
    "has_open_position",
    "total_tasks",
    "successful",
    "average_return",
    "average_sharpe",
    "ranking_metric",
    "n_windows",
    "return_std",
    "positive_windows",
    "negative_windows",
    "train_period",
    "test_period",
    "step_size",
]


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
        self.sqlite_file = self.storage_path / "history.sqlite3"
        self.max_records = max_records
        self.history: List[Dict] = []
        self._lock = threading.RLock()
        self._load_history()
        
        logger.info(f"BacktestHistory initialized with {len(self.history)} records")

    @staticmethod
    def _build_summary_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
        summary = {}

        for field in SUMMARY_METRIC_FIELDS:
            if field == "total_trades":
                summary[field] = metrics.get("total_trades", metrics.get("num_trades", 0))
            elif field == "has_open_position":
                summary[field] = bool(metrics.get(field, False))
            else:
                summary[field] = metrics.get(field, 0)

        return ensure_json_serializable(summary)

    @staticmethod
    def _merge_metric_sources(result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **(result.get("performance_metrics") or {}),
            **(result.get("metrics") or {}),
            **result,
        }

    @staticmethod
    def _build_record_summary(record: Dict[str, Any]) -> Dict[str, Any]:
        return ensure_json_serializable({
            "id": record.get("id"),
            "timestamp": record.get("timestamp"),
            "record_type": record.get("record_type", "backtest"),
            "title": record.get("title", ""),
            "code_version": record.get("code_version", "unknown"),
            "strategy_version": record.get("strategy_version", record.get("code_version", "unknown")),
            "symbol": record.get("symbol", "Unknown"),
            "strategy": record.get("strategy", "Unknown"),
            "start_date": record.get("start_date", ""),
            "end_date": record.get("end_date", ""),
            "metrics": record.get("metrics", {}),
            "summary_only": True,
        })

    @staticmethod
    def _get_code_version() -> str:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            return completed.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def _load_history(self):
        """从文件加载历史记录"""
        try:
            self._ensure_database()
            records = self._load_from_database()
            changed = False

            if not records and self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    records = data if isinstance(data, list) else data.get("history", [])
                changed = True

            repaired, repaired_changed = self._repair_records(records)
            self.history = repaired
            if changed or repaired_changed:
                self._persist()
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
            self.history = []

    def _ensure_database(self):
        with sqlite3.connect(self.sqlite_file) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_history (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    record_type TEXT,
                    title TEXT,
                    code_version TEXT,
                    strategy_version TEXT,
                    symbol TEXT,
                    strategy TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    parameters_json TEXT,
                    metrics_json TEXT,
                    result_json TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_history_timestamp ON backtest_history(timestamp DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_history_filters ON backtest_history(record_type, symbol, strategy)"
            )
            connection.commit()

    def _load_from_database(self) -> List[Dict[str, Any]]:
        if not self.sqlite_file.exists():
            return []

        with sqlite3.connect(self.sqlite_file) as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, record_type, title, code_version, strategy_version,
                       symbol, strategy, start_date, end_date, parameters_json, metrics_json, result_json
                FROM backtest_history
                ORDER BY timestamp DESC
                """
            ).fetchall()

        records = []
        for row in rows:
            records.append(
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "record_type": row[2],
                    "title": row[3],
                    "code_version": row[4],
                    "strategy_version": row[5],
                    "symbol": row[6],
                    "strategy": row[7],
                    "start_date": row[8],
                    "end_date": row[9],
                    "parameters": json.loads(row[10]) if row[10] else {},
                    "metrics": json.loads(row[11]) if row[11] else {},
                    "result": json.loads(row[12]) if row[12] else {},
                }
            )

        return records

    def _repair_records(self, records: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool]:
        repaired = []
        changed = False
        for record in records:
            normalized_record = dict(record)
            normalized_record.setdefault("record_type", "backtest")
            normalized_record.setdefault("title", "")
            normalized_record.setdefault("code_version", "unknown")
            normalized_record.setdefault("strategy_version", normalized_record.get("code_version", "unknown"))
            original_result = record.get("result")
            if isinstance(original_result, dict):
                if normalized_record.get("record_type") == "backtest":
                    normalized_result = ensure_json_serializable(
                        normalize_backtest_results(original_result)
                    )
                else:
                    normalized_result = ensure_json_serializable(original_result)
                if normalized_result != original_result:
                    changed = True
                normalized_record["result"] = normalized_result

                if normalized_record.get("record_type") == "backtest":
                    metrics = self._merge_metric_sources(normalized_result)
                else:
                    metrics = {
                        **self._merge_metric_sources(normalized_result),
                        **(normalized_record.get("metrics") or {}),
                    }
                normalized_metrics = self._build_summary_metrics(metrics)
                if normalized_metrics != record.get("metrics"):
                    changed = True
                normalized_record["metrics"] = normalized_metrics

            repaired.append(normalized_record)
        return repaired, changed

    def _persist(self):
        """保存历史记录到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2, default=str)
            self._persist_to_database()
        except Exception as e:
            logger.error(f"Failed to persist history: {e}")

    def _persist_to_database(self):
        self._ensure_database()
        with sqlite3.connect(self.sqlite_file) as connection:
            connection.execute("DELETE FROM backtest_history")
            connection.executemany(
                """
                INSERT INTO backtest_history (
                    id, timestamp, record_type, title, code_version, strategy_version,
                    symbol, strategy, start_date, end_date,
                    parameters_json, metrics_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.get("id"),
                        record.get("timestamp"),
                        record.get("record_type", "backtest"),
                        record.get("title", ""),
                        record.get("code_version", "unknown"),
                        record.get("strategy_version", record.get("code_version", "unknown")),
                        record.get("symbol", "Unknown"),
                        record.get("strategy", "Unknown"),
                        record.get("start_date", ""),
                        record.get("end_date", ""),
                        json.dumps(record.get("parameters", {}), ensure_ascii=False),
                        json.dumps(record.get("metrics", {}), ensure_ascii=False),
                        json.dumps(record.get("result", {}), ensure_ascii=False),
                    )
                    for record in self.history
                ],
            )
            connection.commit()

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
            record_type = result.get("record_type", "backtest")
            if record_type == "backtest":
                result = ensure_json_serializable(normalize_backtest_results(result))
            else:
                result = ensure_json_serializable(result)
            record_id = self._generate_id(result)
            
            # 提取关键信息
            metrics = self._merge_metric_sources(result)
            
            record = {
                "id": record_id,
                "timestamp": datetime.now().isoformat(),
                "record_type": record_type,
                "title": result.get("title", ""),
                "code_version": result.get("code_version") or self._get_code_version(),
                "strategy_version": result.get("strategy_version") or result.get("code_version") or self._get_code_version(),
                "symbol": result.get("symbol", "Unknown"),
                "strategy": result.get("strategy", "Unknown"),
                "start_date": result.get("start_date", ""),
                "end_date": result.get("end_date", ""),
                "parameters": result.get("parameters", {}),
                "metrics": self._build_summary_metrics(metrics),
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

    def _filter_history(self, symbol: str = None, strategy: str = None, record_type: str = None) -> List[Dict]:
        """Return filtered history records without pagination."""
        filtered = self.history

        if symbol:
            filtered = [
                record for record in filtered
                if record.get("symbol", "").upper() == symbol.upper()
            ]

        if strategy:
            filtered = [
                record for record in filtered
                if record.get("strategy", "").lower() == strategy.lower()
            ]

        if record_type:
            filtered = [
                record for record in filtered
                if record.get("record_type", "backtest").lower() == record_type.lower()
            ]

        return filtered

    def get_history(
        self,
        limit: int = 20,
        symbol: str = None,
        strategy: str = None,
        record_type: str = None,
        offset: int = 0,
        summary_only: bool = False,
    ) -> List[Dict]:
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
            filtered = self._filter_history(symbol=symbol, strategy=strategy, record_type=record_type)
            start = max(offset, 0)
            end = start + limit if limit is not None else None
            page = filtered[start:end]
            if summary_only:
                return [self._build_record_summary(record) for record in page]
            return page

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

    def get_statistics(self, symbol: str = None, strategy: str = None, record_type: str = None) -> Dict[str, Any]:
        """
        获取历史统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            filtered_history = self._filter_history(symbol=symbol, strategy=strategy, record_type=record_type)

            if not filtered_history:
                return {
                    "total_records": 0,
                    "strategies": {},
                    "symbols": {},
                    "record_types": {},
                    "avg_return": 0,
                    "strategy_count": 0,
                    "latest_record_at": None,
                }
            
            strategies = {}
            symbols = {}
            record_types = {}
            total_return = 0
            
            for record in filtered_history:
                strategy = record.get("strategy", "Unknown")
                symbol = record.get("symbol", "Unknown")
                record_type = record.get("record_type", "backtest")
                
                strategies[strategy] = strategies.get(strategy, 0) + 1
                symbols[symbol] = symbols.get(symbol, 0) + 1
                total_return += record.get("metrics", {}).get("total_return", 0)
                record_types[record_type] = record_types.get(record_type, 0) + 1
            
            return {
                "total_records": len(filtered_history),
                "strategies": strategies,
                "symbols": symbols,
                "record_types": record_types,
                "avg_return": total_return / len(filtered_history) if filtered_history else 0,
                "strategy_count": len(strategies),
                "latest_record_at": filtered_history[0].get("timestamp") if filtered_history else None,
                "most_tested_symbol": max(symbols, key=symbols.get) if symbols else None,
                "most_used_strategy": max(strategies, key=strategies.get) if strategies else None
            }


# 全局实例
backtest_history = BacktestHistory()
