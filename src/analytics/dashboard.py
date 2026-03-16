"""
简化的性能分析模块
"""

import pandas as pd
from typing import Dict, Any


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.trades = results.get("trades", [])

    def calculate_metrics(self) -> Dict[str, Any]:
        """计算性能指标"""
        metrics = {}

        # 基础指标
        metrics["total_return"] = self.results.get("total_return", 0)
        metrics["annualized_return"] = self.results.get("annualized_return", 0)
        metrics["sharpe_ratio"] = self.results.get("sharpe_ratio", 0)
        metrics["max_drawdown"] = self.results.get("max_drawdown", 0)
        metrics["num_trades"] = self.results.get("num_trades", 0)

        # 交易统计
        if self.trades:
            trades_df = pd.DataFrame(self.trades)

            # 只分析卖出交易的PnL
            sell_trades = trades_df[trades_df["type"] == "SELL"]
            if not sell_trades.empty and "pnl" in sell_trades.columns:
                winning_trades = (sell_trades["pnl"] > 0).sum()
                losing_trades = (sell_trades["pnl"] < 0).sum()
                total_sell_trades = len(sell_trades)

                metrics["win_rate"] = (
                    winning_trades / total_sell_trades if total_sell_trades > 0 else 0
                )
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

                # 盈亏比
                if avg_loss != 0:
                    metrics["profit_factor"] = abs(avg_win / avg_loss)
                else:
                    metrics["profit_factor"] = float("inf") if avg_win > 0 else 0

                # 总盈利和总亏损
                total_profit = winning_pnl.sum() if len(winning_pnl) > 0 else 0
                total_loss = losing_pnl.sum() if len(losing_pnl) > 0 else 0

                metrics["total_profit"] = total_profit
                metrics["total_loss"] = total_loss

                # 净利润
                metrics["net_profit"] = (
                    total_profit + total_loss
                )  # total_loss is negative

                # 最佳和最差交易
                metrics["best_trade"] = (
                    sell_trades["pnl"].max() if not sell_trades.empty else 0
                )
                metrics["worst_trade"] = (
                    sell_trades["pnl"].min() if not sell_trades.empty else 0
                )

                # 连续盈利/亏损统计
                pnl_signs = (sell_trades["pnl"] > 0).astype(int)
                consecutive_wins = self._calculate_max_consecutive(pnl_signs, 1)
                consecutive_losses = self._calculate_max_consecutive(pnl_signs, 0)

                metrics["max_consecutive_wins"] = consecutive_wins
                metrics["max_consecutive_losses"] = consecutive_losses

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
                # 如果没有PnL数据，设置默认值
                self._set_default_metrics(metrics)
        else:
            # 没有交易记录
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
            "win_rate": 0,
            "loss_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "total_profit": 0,
            "total_loss": 0,
            "net_profit": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "avg_holding_days": 0,
        }
        metrics.update(default_values)
