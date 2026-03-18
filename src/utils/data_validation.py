"""
数据结构验证模块
确保前后端数据结构一致性
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Union
import logging
import math
from datetime import datetime
from copy import deepcopy

from src.backtest.metrics import (
    calculate_annualized_return,
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var,
    calculate_volatility,
)

logger = logging.getLogger(__name__)


class DataStructureValidator:
    """数据结构验证器"""

    def __init__(self):
        self.required_backtest_fields = {
            # 基础指标
            "initial_capital": (int, float),
            "final_value": (int, float),
            "total_return": (int, float),
            "annualized_return": (int, float),
            "net_profit": (int, float),
            # 风险指标
            "sharpe_ratio": (int, float),
            "max_drawdown": (int, float),
            "sortino_ratio": (int, float),
            "calmar_ratio": (int, float),
            # 交易统计
            "num_trades": int,
            "win_rate": (int, float),
            "profit_factor": (int, float),
            "best_trade": (int, float),
            "worst_trade": (int, float),
            "max_consecutive_wins": int,
            "max_consecutive_losses": int,
            # 数据结构
            "portfolio": list,
            "trades": list,
        }

        self.required_portfolio_fields = [
            "cash",
            "holdings",
            "total",
            "position",
            "returns",
        ]

        self.required_trade_fields = ["date", "type", "price", "shares"]

    def validate_backtest_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """验证回测结果数据结构"""
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "fixed_fields": [],
        }

        try:
            # 检查必需字段
            for field, expected_type in self.required_backtest_fields.items():
                if field not in results:
                    validation_result["errors"].append(
                        f"Missing required field: {field}"
                    )
                    validation_result["is_valid"] = False
                    continue

                value = results[field]

                # 检查类型
                if not isinstance(value, expected_type):
                    if field in ["portfolio", "trades"]:
                        # 特殊处理数据结构字段
                        if field == "portfolio" and isinstance(value, pd.DataFrame):
                            # 转换DataFrame为list
                            results[field] = self._convert_portfolio_to_list(value)
                            validation_result["fixed_fields"].append(
                                f"Converted {field} from DataFrame to list"
                            )
                        elif field == "trades" and not isinstance(value, list):
                            validation_result["errors"].append(
                                f"Field {field} must be a list, got {type(value)}"
                            )
                            validation_result["is_valid"] = False
                    else:
                        # 数值字段类型检查
                        if pd.isna(value) or value is None:
                            results[field] = 0.0
                            validation_result["fixed_fields"].append(
                                f"Fixed null value in {field}"
                            )
                        elif not isinstance(value, expected_type):
                            try:
                                if expected_type == int:
                                    results[field] = int(float(value))
                                else:
                                    results[field] = float(value)
                                validation_result["fixed_fields"].append(
                                    f"Converted {field} to {expected_type}"
                                )
                            except (ValueError, TypeError):
                                validation_result["errors"].append(
                                    f"Cannot convert {field} to {expected_type}"
                                )
                                validation_result["is_valid"] = False

            # 验证portfolio结构
            if "portfolio" in results and isinstance(results["portfolio"], list):
                portfolio_validation = self._validate_portfolio_structure(
                    results["portfolio"]
                )
                validation_result["warnings"].extend(portfolio_validation["warnings"])
                if not portfolio_validation["is_valid"]:
                    validation_result["errors"].extend(portfolio_validation["errors"])
                    validation_result["is_valid"] = False

            # 验证trades结构
            if "trades" in results and isinstance(results["trades"], list):
                trades_validation = self._validate_trades_structure(results["trades"])
                validation_result["warnings"].extend(trades_validation["warnings"])
                if not trades_validation["is_valid"]:
                    validation_result["errors"].extend(trades_validation["errors"])
                    validation_result["is_valid"] = False

            # 验证数值合理性
            self._validate_numerical_consistency(results, validation_result)

        except Exception as e:
            logger.error(f"Error validating backtest results: {e}")
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Validation error: {str(e)}")

        return validation_result

    def _convert_portfolio_to_list(self, portfolio_df: pd.DataFrame) -> List[Dict]:
        """将portfolio DataFrame转换为list格式"""
        try:
            # 确保所有必需字段存在
            for field in self.required_portfolio_fields:
                if field not in portfolio_df.columns:
                    if field == "returns":
                        portfolio_df["returns"] = portfolio_df["total"].pct_change()
                    else:
                        portfolio_df[field] = 0.0

            # 处理NaN值
            portfolio_df = portfolio_df.fillna(0)

            # 重置索引并转换为字典列表
            portfolio_df = portfolio_df.reset_index()

            # 确保日期字段正确格式化
            if "Date" in portfolio_df.columns:
                portfolio_df["Date"] = portfolio_df["Date"].dt.strftime("%Y-%m-%d")
            elif portfolio_df.index.name == "Date":
                portfolio_df["Date"] = portfolio_df.index.strftime("%Y-%m-%d")

            return portfolio_df.to_dict("records")

        except Exception as e:
            logger.error(f"Error converting portfolio to list: {e}")
            return []

    def _validate_portfolio_structure(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """验证portfolio数据结构"""
        result = {"is_valid": True, "errors": [], "warnings": []}

        if not portfolio:
            result["warnings"].append("Portfolio is empty")
            return result

        # 检查第一条记录的字段
        first_record = portfolio[0]
        missing_fields = []

        for field in self.required_portfolio_fields:
            if field not in first_record:
                missing_fields.append(field)

        if missing_fields:
            result["errors"].append(f"Portfolio missing fields: {missing_fields}")
            result["is_valid"] = False

        # 检查数值字段
        for record in portfolio[:5]:  # 只检查前5条记录
            for field in ["cash", "holdings", "total"]:
                if field in record:
                    value = record[field]
                    if not isinstance(value, (int, float)) or pd.isna(value):
                        result["warnings"].append(
                            f"Invalid value in portfolio.{field}: {value}"
                        )

        return result

    def _validate_trades_structure(self, trades: List[Dict]) -> Dict[str, Any]:
        """验证trades数据结构"""
        result = {"is_valid": True, "errors": [], "warnings": []}

        if not trades:
            result["warnings"].append("No trades found")
            return result

        # 检查交易记录字段
        for i, trade in enumerate(trades[:10]):  # 只检查前10条记录
            missing_fields = []
            for field in self.required_trade_fields:
                if field not in trade:
                    missing_fields.append(field)

            if missing_fields:
                result["errors"].append(f"Trade {i} missing fields: {missing_fields}")
                result["is_valid"] = False

            # 检查交易类型
            if "type" in trade and trade["type"] not in ["BUY", "SELL"]:
                result["warnings"].append(
                    f"Trade {i} has invalid type: {trade['type']}"
                )

        return result

    def _validate_numerical_consistency(
        self, results: Dict[str, Any], validation_result: Dict[str, Any]
    ):
        """验证数值一致性"""
        try:
            # 检查win_rate是否在合理范围内
            if "win_rate" in results:
                win_rate = results["win_rate"]
                if not (0 <= win_rate <= 1):
                    validation_result["warnings"].append(
                        f"Win rate {win_rate:.2%} is outside normal range [0, 1]"
                    )

            # 检查total_return和final_value的一致性
            if all(
                field in results
                for field in ["initial_capital", "final_value", "total_return"]
            ):
                expected_return = (
                    results["final_value"] - results["initial_capital"]
                ) / results["initial_capital"]
                actual_return = results["total_return"]

                if abs(expected_return - actual_return) > 0.001:  # 允许0.1%的误差
                    validation_result["warnings"].append(
                        f"Total return inconsistency: expected {expected_return:.2%}, got {actual_return:.2%}"
                    )

            # 检查sharpe_ratio的合理性
            if "sharpe_ratio" in results:
                sharpe = results["sharpe_ratio"]
                if abs(sharpe) > 10:  # 夏普比率通常不会超过10
                    validation_result["warnings"].append(
                        f"Sharpe ratio {sharpe:.2f} seems unusually high"
                    )

        except Exception as e:
            validation_result["warnings"].append(
                f"Error in numerical validation: {str(e)}"
            )

    def sanitize_for_json(self, data: Any) -> Any:
        """清理数据以确保JSON序列化兼容性"""
        if isinstance(data, dict):
            return {k: self.sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_for_json(item) for item in data]
        elif isinstance(data, pd.DataFrame):
            return self.sanitize_for_json(self._dataframe_to_records(data))
        elif isinstance(data, (pd.Series, np.ndarray)):
            return self.sanitize_for_json(data.tolist())
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return 0.0
            return data
        elif pd.isna(data) or data is None:
            return 0 if isinstance(data, (int, float)) else None
        elif isinstance(data, (np.integer, np.floating)):
            numeric_value = float(data)
            if math.isnan(numeric_value) or math.isinf(numeric_value):
                return 0.0
            return numeric_value
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data

    def _dataframe_to_records(self, dataframe: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert DataFrame to records while preserving datetime indexes as a date column."""
        working_df = dataframe.copy()

        if not isinstance(working_df.index, pd.RangeIndex):
            index_name = working_df.index.name or "index"
            working_df = working_df.reset_index()

            first_col = working_df.columns[0]
            if first_col == index_name and pd.api.types.is_datetime64_any_dtype(working_df[first_col]):
                working_df = working_df.rename(columns={first_col: "date"})
        else:
            working_df = working_df.reset_index(drop=True)

        working_df = working_df.fillna(0)
        return working_df.to_dict("records")


# 全局验证器实例
data_validator = DataStructureValidator()

BACKTEST_METRIC_FIELDS = [
    "initial_capital",
    "final_value",
    "total_return",
    "annualized_return",
    "volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "max_drawdown",
    "var_95",
    "num_trades",
    "total_trades",
    "num_buy_trades",
    "num_sell_trades",
    "win_rate",
    "profit_factor",
    "best_trade",
    "worst_trade",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "avg_trade",
    "max_consecutive_wins",
    "max_consecutive_losses",
    "total_completed_trades",
    "has_open_position",
]


def _coerce_number(value: Any, target_type):
    """Best-effort numeric coercion used by compatibility normalization."""
    if value is None:
        return None

    try:
        if target_type is int:
            return int(float(value))
        return float(value)
    except (TypeError, ValueError):
        return value


def normalize_trade_record(trade: Dict[str, Any], copy_data: bool = True) -> Dict[str, Any]:
    """Normalize trade aliases so downstream consumers can use one shape."""
    normalized = deepcopy(trade) if copy_data else trade

    trade_type = normalized.get("type")
    action = normalized.get("action")

    if not trade_type and action:
        action_value = str(action).lower()
        if action_value == "buy":
            trade_type = "BUY"
        elif action_value == "sell":
            trade_type = "SELL"

    if not action and trade_type:
        upper_type = str(trade_type).upper()
        if upper_type == "BUY":
            action = "buy"
        elif upper_type == "SELL":
            action = "sell"

    shares = normalized.get("shares", normalized.get("quantity"))
    shares = _coerce_number(shares, int) if shares is not None else 0

    value = normalized.get("value")
    if value is None:
        if str(trade_type).upper() == "BUY":
            value = normalized.get("cost")
        elif str(trade_type).upper() == "SELL":
            value = normalized.get("revenue")

    if value is None:
        price = _coerce_number(normalized.get("price"), float)
        if isinstance(price, (int, float)) and isinstance(shares, int):
            value = price * shares

    normalized["type"] = str(trade_type).upper() if trade_type else normalized.get("type")
    normalized["action"] = action or normalized.get("action")
    normalized["shares"] = shares
    normalized["quantity"] = shares

    if value is not None:
        normalized["value"] = _coerce_number(value, float)

    return normalized


def normalize_backtest_metrics(
    metrics: Dict[str, Any], copy_data: bool = True
) -> Dict[str, Any]:
    """Normalize metric aliases without changing public field names."""
    normalized = deepcopy(metrics) if copy_data else metrics

    num_trades = normalized.get("num_trades")
    total_trades = normalized.get("total_trades")

    if num_trades is None:
        num_trades = total_trades

    if num_trades is None and isinstance(normalized.get("trades"), list):
        num_trades = len(normalized["trades"])

    num_trades = _coerce_number(num_trades, int) if num_trades is not None else 0
    normalized["num_trades"] = num_trades
    normalized["total_trades"] = num_trades

    for field in [
        "total_completed_trades",
        "num_buy_trades",
        "num_sell_trades",
        "max_consecutive_wins",
        "max_consecutive_losses",
    ]:
        if field in normalized and normalized[field] is not None:
            normalized[field] = _coerce_number(normalized[field], int)

    return normalized


def _is_valid_number(value: Any) -> bool:
    """Return True when value is a finite numeric scalar."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False

    return np.isfinite(numeric_value)


def _is_corrupted_portfolio_row(row: Dict[str, Any], previous_row: Optional[Dict[str, Any]]) -> bool:
    """Detect a trailing placeholder row produced by an incomplete market bar."""
    if not isinstance(row, dict) or not isinstance(previous_row, dict):
        return False

    last_total = _coerce_number(row.get("total"), float)
    prev_total = _coerce_number(previous_row.get("total"), float)
    last_price = _coerce_number(row.get("price"), float)
    last_cash = _coerce_number(row.get("cash"), float)
    last_holdings = _coerce_number(row.get("holdings"), float)
    last_position = _coerce_number(row.get("position"), float)

    return (
        isinstance(prev_total, (int, float))
        and prev_total > 0
        and isinstance(last_total, (int, float))
        and last_total <= 0
        and (
            not _is_valid_number(last_price)
            or last_price <= 0
        )
        and _coerce_number(last_cash, float) == 0
        and _coerce_number(last_holdings, float) == 0
        and _coerce_number(last_position, float) == 0
    )


def _is_corrupted_trade(trade: Dict[str, Any], corrupted_dates: set[str]) -> bool:
    """Detect a synthetic trailing SELL created by a corrupted final price bar."""
    if not isinstance(trade, dict):
        return False

    trade_date = str(trade.get("date", ""))
    trade_type = str(trade.get("type") or trade.get("action") or "").upper()
    price = _coerce_number(trade.get("price"), float)
    value = _coerce_number(
        trade.get("value", trade.get("revenue", trade.get("cost"))), float
    )

    return (
        trade_type == "SELL"
        and trade_date in corrupted_dates
        and (not _is_valid_number(price) or price <= 0)
        and (value is None or not _is_valid_number(value) or value <= 0)
    )


def _repair_trailing_corruption(
    results: Dict[str, Any], copy_data: bool = True
) -> Dict[str, Any]:
    """
    Repair old backtest snapshots whose final bar was an incomplete market row.

    These snapshots typically end with a zero-value portfolio row and a bogus SELL
    trade at price 0, which makes final_value and total_return collapse to 0.
    """
    repaired = deepcopy(results) if copy_data else results

    portfolio_source = repaired.get("portfolio")
    portfolio_history_source = repaired.get("portfolio_history")

    portfolio = deepcopy(portfolio_source) if isinstance(portfolio_source, list) else []
    portfolio_history = (
        deepcopy(portfolio_history_source)
        if isinstance(portfolio_history_source, list)
        else deepcopy(portfolio)
    )

    if not portfolio:
        return repaired

    corrupted_dates: set[str] = set()
    while len(portfolio) > 1 and _is_corrupted_portfolio_row(portfolio[-1], portfolio[-2]):
        corrupted_dates.add(str(portfolio[-1].get("date", "")))
        portfolio.pop()
        if portfolio_history:
            portfolio_history.pop()

    if not corrupted_dates:
        return repaired

    trades = repaired.get("trades")
    cleaned_trades = deepcopy(trades) if isinstance(trades, list) else []
    while cleaned_trades and _is_corrupted_trade(cleaned_trades[-1], corrupted_dates):
        cleaned_trades.pop()

    totals = pd.Series(
        [float(row.get("total", 0) or 0) for row in portfolio],
        dtype="float64",
    )
    returns = totals.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)

    for index, row in enumerate(portfolio):
        row["returns"] = float(returns.iloc[index])
    for index, row in enumerate(portfolio_history):
        row["returns"] = float(returns.iloc[index])

    initial_capital = _coerce_number(repaired.get("initial_capital"), float)
    if not isinstance(initial_capital, (int, float)) or initial_capital <= 0:
        initial_capital = _coerce_number(totals.iloc[0], float) or 0.0

    final_value = float(totals.iloc[-1]) if len(totals) else 0.0
    total_return = (
        (final_value - initial_capital) / initial_capital if initial_capital else 0.0
    )
    annualized_return = calculate_annualized_return(total_return, len(portfolio))
    returns_values = returns.iloc[1:] if len(returns) > 1 else pd.Series(dtype="float64")
    max_drawdown = calculate_max_drawdown(totals.values) if len(totals) else 0.0

    completed_trade_pnls: List[float] = []
    has_open_position = False
    index = 0
    while index < len(cleaned_trades):
        trade = cleaned_trades[index]
        trade_type = str(trade.get("type") or trade.get("action") or "").upper()
        if trade_type != "BUY":
            index += 1
            continue

        if index + 1 < len(cleaned_trades):
            next_trade = cleaned_trades[index + 1]
            next_type = str(next_trade.get("type") or next_trade.get("action") or "").upper()
            if next_type == "SELL":
                entry_value = trade.get("cost")
                if entry_value is None:
                    entry_price = _coerce_number(trade.get("price"), float) or 0.0
                    entry_shares = _coerce_number(trade.get("shares", trade.get("quantity")), int) or 0
                    entry_value = entry_price * entry_shares

                trade_pnl = next_trade.get("pnl")
                if trade_pnl is None:
                    exit_value = next_trade.get("revenue", next_trade.get("value"))
                    if exit_value is None:
                        exit_price = _coerce_number(next_trade.get("price"), float) or 0.0
                        exit_shares = _coerce_number(next_trade.get("shares", next_trade.get("quantity")), int) or 0
                        exit_value = exit_price * exit_shares
                    trade_pnl = (exit_value or 0.0) - (entry_value or 0.0)

                completed_trade_pnls.append(float(trade_pnl or 0.0))
                index += 2
                continue

        has_open_position = True
        index += 1

    winning_trades = [pnl for pnl in completed_trade_pnls if pnl > 0]
    losing_trades = [pnl for pnl in completed_trade_pnls if pnl < 0]
    gross_profit = float(sum(winning_trades)) if winning_trades else 0.0
    gross_loss = float(abs(sum(losing_trades))) if losing_trades else 0.0
    total_completed_trades = len(completed_trade_pnls)
    win_rate = (
        len(winning_trades) / total_completed_trades if total_completed_trades else 0.0
    )
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )
    best_trade = max(completed_trade_pnls) if completed_trade_pnls else 0.0
    worst_trade = min(completed_trade_pnls) if completed_trade_pnls else 0.0
    avg_trade = (
        sum(completed_trade_pnls) / total_completed_trades
        if total_completed_trades
        else 0.0
    )

    consecutive_wins = 0
    consecutive_losses = 0
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    for pnl in completed_trade_pnls:
        if pnl > 0:
            consecutive_wins += 1
            consecutive_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
        elif pnl < 0:
            consecutive_losses += 1
            consecutive_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_wins = 0
            consecutive_losses = 0

    repaired_metrics = {
        "initial_capital": float(initial_capital),
        "final_value": final_value,
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "net_profit": float(final_value - initial_capital),
        "sharpe_ratio": float(calculate_sharpe_ratio(returns_values)),
        "max_drawdown": float(max_drawdown),
        "sortino_ratio": float(calculate_sortino_ratio(returns_values)),
        "calmar_ratio": float(calculate_calmar_ratio(annualized_return, max_drawdown)),
        "volatility": float(calculate_volatility(returns_values)),
        "var_95": float(calculate_var(returns_values)),
        "num_trades": len(cleaned_trades),
        "total_trades": len(cleaned_trades),
        "num_buy_trades": len(
            [trade for trade in cleaned_trades if str(trade.get("type") or trade.get("action") or "").upper() == "BUY"]
        ),
        "num_sell_trades": len(
            [trade for trade in cleaned_trades if str(trade.get("type") or trade.get("action") or "").upper() == "SELL"]
        ),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "best_trade": float(best_trade),
        "worst_trade": float(worst_trade),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "avg_trade": float(avg_trade),
        "max_consecutive_wins": int(max_consecutive_wins),
        "max_consecutive_losses": int(max_consecutive_losses),
        "total_completed_trades": int(total_completed_trades),
        "has_open_position": bool(has_open_position),
    }

    repaired["portfolio"] = portfolio
    repaired["portfolio_history"] = portfolio_history
    repaired["trades"] = cleaned_trades

    for field, value in repaired_metrics.items():
        repaired[field] = value

    for metrics_key in ["metrics", "performance_metrics"]:
        if not isinstance(repaired.get(metrics_key), dict):
            repaired[metrics_key] = {}
        repaired[metrics_key].update(repaired_metrics)

    logger.info(
        "Repaired trailing corrupted backtest snapshot by trimming %s portfolio row(s) and %s trade(s)",
        len(corrupted_dates),
        (len(trades) if isinstance(trades, list) else 0) - len(cleaned_trades),
    )

    return repaired


def normalize_backtest_results(
    results: Dict[str, Any], copy_data: bool = True
) -> Dict[str, Any]:
    """Normalize top-level backtest results, nested metrics, and trade aliases."""
    normalized = deepcopy(results) if copy_data else results

    if "trades" in normalized and isinstance(normalized["trades"], list):
        normalized["trades"] = [
            normalize_trade_record(trade, copy_data=False) for trade in normalized["trades"]
        ]

    if "portfolio" in normalized and "portfolio_history" not in normalized:
        normalized["portfolio_history"] = normalized["portfolio"]
    elif "portfolio_history" in normalized and "portfolio" not in normalized:
        normalized["portfolio"] = normalized["portfolio_history"]

    normalized = _repair_trailing_corruption(normalized, copy_data=False)

    metrics = normalized.get("metrics") if isinstance(normalized.get("metrics"), dict) else {}
    performance_metrics = (
        normalized.get("performance_metrics")
        if isinstance(normalized.get("performance_metrics"), dict)
        else {}
    )

    merged_metrics = {}
    for field in BACKTEST_METRIC_FIELDS:
        if field in normalized:
            merged_metrics[field] = normalized[field]
        elif field in metrics:
            merged_metrics[field] = metrics[field]
        elif field in performance_metrics:
            merged_metrics[field] = performance_metrics[field]

    merged_metrics = normalize_backtest_metrics(merged_metrics, copy_data=False)

    for field, value in merged_metrics.items():
        normalized[field] = value

    normalized["metrics"] = normalize_backtest_metrics(
        {**metrics, **merged_metrics}, copy_data=False
    )
    normalized["performance_metrics"] = normalize_backtest_metrics(
        {**performance_metrics, **merged_metrics}, copy_data=False
    )

    return normalized


def validate_and_fix_backtest_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """验证并修复回测结果的便捷函数"""
    results = normalize_backtest_results(results)
    validation = data_validator.validate_backtest_results(results)

    if validation["fixed_fields"]:
        logger.info(f"Fixed data structure issues: {validation['fixed_fields']}")

    if validation["warnings"]:
        logger.warning(f"Data validation warnings: {validation['warnings']}")

    if not validation["is_valid"]:
        logger.error(f"Data validation errors: {validation['errors']}")
        raise ValueError(f"Invalid data structure: {validation['errors']}")

    return results


def ensure_json_serializable(data: Any) -> Any:
    """确保数据可以JSON序列化"""
    return data_validator.sanitize_for_json(data)
