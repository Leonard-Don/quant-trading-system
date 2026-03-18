"""
简化的性能分析模块
"""

import pandas as pd
from typing import Dict, Any

from src.utils.data_validation import normalize_backtest_results


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.trades = results.get("trades", [])

    def calculate_metrics(self) -> Dict[str, Any]:
        """计算补充分析指标，不覆盖回测引擎已给出的核心指标。"""
        normalized_results = normalize_backtest_results(self.results)
        metrics = {}

        # 交易统计
        if self.trades:
            trades_df = pd.DataFrame(normalized_results.get("trades", []))

            # 只分析卖出交易的PnL
            sell_trades = trades_df[trades_df["type"] == "SELL"]
            if not sell_trades.empty and "pnl" in sell_trades.columns:
                winning_trades = (sell_trades["pnl"] > 0).sum()
                losing_trades = (sell_trades["pnl"] < 0).sum()
                total_sell_trades = len(sell_trades)
                metrics["loss_rate"] = (
                    losing_trades / total_sell_trades if total_sell_trades > 0 else 0
                )

                # 盈亏统计
                winning_pnl = sell_trades[sell_trades["pnl"] > 0]["pnl"]
                losing_pnl = sell_trades[sell_trades["pnl"] < 0]["pnl"]

                avg_win = winning_pnl.mean() if len(winning_pnl) > 0 else 0
                avg_loss = losing_pnl.mean() if len(losing_pnl) > 0 else 0

                metrics["avg_win"] = avg_win
                metrics["avg_loss"] = avg_loss

                # 总盈利和总亏损
                total_profit = winning_pnl.sum() if len(winning_pnl) > 0 else 0
                total_loss = losing_pnl.sum() if len(losing_pnl) > 0 else 0

                metrics["total_profit"] = total_profit
                metrics["total_loss"] = total_loss

                # 连续盈利/亏损统计
                pnl_signs = (sell_trades["pnl"] > 0).astype(int)

                # 平均持仓时间（如果有日期信息）
                if "date" in sell_trades.columns:
                    try:
                        dates = pd.to_datetime(sell_trades["date"])
                        if len(dates) > 1:
                            avg_holding_days = (dates.max() - dates.min()).days / len(
                                dates
                            )
                            metrics["avg_holding_days"] = avg_holding_days
                    except (ValueError, KeyError, AttributeError):
                        metrics["avg_holding_days"] = 0
                else:
                    metrics["avg_holding_days"] = 0

            else:
                self._set_default_metrics(metrics)
        else:
            self._set_default_metrics(metrics)

        return metrics

    def _calculate_max_consecutive(self, series, value):
        """计算最大连续出现次数"""
        max_count = 0
        current_count = 0

        for val in series:
            if val == value:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0

        return max_count

    def _set_default_metrics(self, metrics):
        """设置默认指标值"""
        default_values = {
            "loss_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "total_profit": 0,
            "total_loss": 0,
            "avg_holding_days": 0,
        }
        for key, value in default_values.items():
            metrics.setdefault(key, value)
