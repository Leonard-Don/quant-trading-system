"""
数据结构验证模块
确保前后端数据结构一致性
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Union
import logging
from datetime import datetime

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
            return self.sanitize_for_json(data.fillna(0).to_dict("records"))
        elif isinstance(data, (pd.Series, np.ndarray)):
            return self.sanitize_for_json(data.tolist())
        elif pd.isna(data) or data is None:
            return 0 if isinstance(data, (int, float)) else None
        elif isinstance(data, (np.integer, np.floating)):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data


# 全局验证器实例
data_validator = DataStructureValidator()


def validate_and_fix_backtest_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """验证并修复回测结果的便捷函数"""
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
