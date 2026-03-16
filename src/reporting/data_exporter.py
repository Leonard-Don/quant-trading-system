"""
数据导出与图表生成模块
负责生成回测结果的 JSON/CSV/Excel 报告以及可视化图表
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
import logging
from pathlib import Path
import base64
from io import BytesIO
import csv

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# 设置中文字体和样式
plt.rcParams["font.sans-serif"] = ["SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")


class DataExporter:
    """数据导出与分析器"""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or PROJECT_ROOT / "reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def generate_backtest_report(
        self,
        backtest_results: Dict[str, Any],
        symbol: str,
        strategy_name: str,
        include_charts: bool = True,
    ) -> Dict[str, Any]:
        """生成详细的回测数据报告"""
        try:
            report_id = f"backtest_{symbol}_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 基本信息
            report = {
                "report_id": report_id,
                "generated_at": datetime.now().isoformat(),
                "symbol": symbol,
                "strategy": strategy_name,
                "summary": self._generate_summary(backtest_results),
                "performance_metrics": self._extract_performance_metrics(
                    backtest_results
                ),
                "risk_metrics": self._calculate_risk_metrics(backtest_results),
                "trade_analysis": self._analyze_trades(backtest_results),
            }

            # 生成图表
            if include_charts:
                report["charts"] = self._generate_charts(
                    backtest_results, symbol, strategy_name
                )

            # 保存报告
            report_path = self.output_dir / f"{report_id}.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            report["file_path"] = str(report_path)

            self.logger.info(f"回测数据报告生成完成: {report_id}")
            return report

        except Exception as e:
            self.logger.error(f"生成回测报告失败: {e}")
            raise

    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """生成报告摘要"""
        try:
            portfolio_value = results.get("portfolio_value", [])
            if not portfolio_value:
                return {"error": "No portfolio data available"}

            initial_value = portfolio_value[0]
            final_value = portfolio_value[-1]
            total_return = ((final_value - initial_value) / initial_value) * 100

            return {
                "initial_capital": initial_value,
                "final_value": final_value,
                "total_return_pct": round(total_return, 2),
                "total_return_amount": round(final_value - initial_value, 2),
                "trading_days": len(portfolio_value),
                "strategy_performance": "盈利" if total_return > 0 else "亏损",
            }

        except Exception as e:
            self.logger.error(f"生成摘要失败: {e}")
            return {"error": str(e)}

    def _extract_performance_metrics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """提取性能指标"""
        try:
            metrics = {}

            # 从结果中提取各种指标
            for key, value in results.items():
                if (
                    key.endswith("_ratio")
                    or key.endswith("_return")
                    or key.endswith("_drawdown")
                ):
                    if isinstance(value, (int, float)):
                        metrics[key] = round(value, 4)

            # 计算额外指标
            portfolio_value = results.get("portfolio_value", [])
            if portfolio_value:
                returns = pd.Series(portfolio_value).pct_change().dropna()

                metrics.update(
                    {
                        "volatility": round(returns.std() * np.sqrt(252), 4),
                        "skewness": round(returns.skew(), 4),
                        "kurtosis": round(returns.kurtosis(), 4),
                        "positive_days": int((returns > 0).sum()),
                        "negative_days": int((returns < 0).sum()),
                        "max_daily_gain": round(returns.max() * 100, 2),
                        "max_daily_loss": round(returns.min() * 100, 2),
                    }
                )

            return metrics

        except Exception as e:
            self.logger.error(f"提取性能指标失败: {e}")
            return {"error": str(e)}

    def _calculate_risk_metrics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """计算风险指标"""
        try:
            portfolio_value = results.get("portfolio_value", [])
            if not portfolio_value:
                return {"error": "No portfolio data available"}

            returns = pd.Series(portfolio_value).pct_change().dropna()

            # VaR计算
            var_95 = np.percentile(returns, 5) * 100
            var_99 = np.percentile(returns, 1) * 100

            # CVaR计算
            cvar_95 = returns[returns <= np.percentile(returns, 5)].mean() * 100
            cvar_99 = returns[returns <= np.percentile(returns, 1)].mean() * 100

            # 最大回撤
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = drawdown.min() * 100

            # 回撤持续时间
            drawdown_duration = self._calculate_drawdown_duration(drawdown)

            return {
                "var_95": round(var_95, 2),
                "var_99": round(var_99, 2),
                "cvar_95": round(cvar_95, 2),
                "cvar_99": round(cvar_99, 2),
                "max_drawdown_pct": round(max_drawdown, 2),
                "max_drawdown_duration_days": drawdown_duration,
                "downside_deviation": round(
                    returns[returns < 0].std() * np.sqrt(252) * 100, 2
                ),
                "sortino_ratio": round(
                    returns.mean() / returns[returns < 0].std() * np.sqrt(252), 4
                )
                if len(returns[returns < 0]) > 0
                else 0,
            }

        except Exception as e:
            self.logger.error(f"计算风险指标失败: {e}")
            return {"error": str(e)}

    def _calculate_drawdown_duration(self, drawdown: pd.Series) -> int:
        """计算最大回撤持续时间"""
        try:
            # 找到最大回撤点
            max_dd_idx = drawdown.idxmin()

            # 向前找到回撤开始点
            start_idx = max_dd_idx
            for i in range(max_dd_idx, -1, -1):
                if drawdown.iloc[i] >= 0:
                    start_idx = i
                    break

            # 向后找到回撤结束点
            end_idx = len(drawdown) - 1
            for i in range(max_dd_idx, len(drawdown)):
                if drawdown.iloc[i] >= 0:
                    end_idx = i
                    break

            return end_idx - start_idx

        except Exception:
            return 0

    def _analyze_trades(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """分析交易记录"""
        try:
            signals = results.get("signals", [])
            if not signals:
                return {"error": "No trading signals available"}

            # 转换为pandas Series
            signals_series = pd.Series(signals)

            buy_signals = (signals_series == 1).sum()
            sell_signals = (signals_series == -1).sum()

            # 计算持仓时间
            positions = []
            current_position = None

            for i, signal in enumerate(signals):
                if signal == 1 and current_position is None:  # 开仓
                    current_position = {"entry": i, "type": "long"}
                elif signal == -1 and current_position is not None:  # 平仓
                    current_position["exit"] = i
                    current_position["duration"] = i - current_position["entry"]
                    positions.append(current_position)
                    current_position = None

            # 统计分析
            if positions:
                durations = [pos["duration"] for pos in positions]
                avg_holding_period = np.mean(durations)
                max_holding_period = max(durations)
                min_holding_period = min(durations)
            else:
                avg_holding_period = max_holding_period = min_holding_period = 0

            return {
                "total_trades": len(positions),
                "buy_signals": int(buy_signals),
                "sell_signals": int(sell_signals),
                "avg_holding_period": round(avg_holding_period, 1),
                "max_holding_period": max_holding_period,
                "min_holding_period": min_holding_period,
                "trade_frequency": round(len(positions) / len(signals) * 100, 2)
                if signals
                else 0,
            }

        except Exception as e:
            self.logger.error(f"分析交易记录失败: {e}")
            return {"error": str(e)}

    def _generate_charts(
        self, results: Dict[str, Any], symbol: str, strategy: str
    ) -> Dict[str, str]:
        """生成图表"""
        try:
            charts = {}

            # 生成组合价值图
            if "portfolio_value" in results:
                charts["portfolio_value"] = self._create_portfolio_chart(
                    results["portfolio_value"], symbol, strategy
                )

            # 生成回撤图
            if "portfolio_value" in results:
                charts["drawdown"] = self._create_drawdown_chart(
                    results["portfolio_value"], symbol, strategy
                )

            # 生成收益分布图
            if "portfolio_value" in results:
                charts[
                    "returns_distribution"
                ] = self._create_returns_distribution_chart(
                    results["portfolio_value"], symbol, strategy
                )

            return charts

        except Exception as e:
            self.logger.error(f"生成图表失败: {e}")
            return {"error": str(e)}

    def _create_portfolio_chart(
        self, portfolio_value: List[float], symbol: str, strategy: str
    ) -> str:
        """创建组合价值图表"""
        try:
            fig, ax = plt.subplots(figsize=(12, 6))

            dates = pd.date_range(
                start="2023-01-01", periods=len(portfolio_value), freq="D"
            )
            ax.plot(dates, portfolio_value, linewidth=2, color="#1f77b4")

            ax.set_title(
                f"{symbol} - {strategy} 策略组合价值变化", fontsize=14, fontweight="bold"
            )
            ax.set_xlabel("日期", fontsize=12)
            ax.set_ylabel("组合价值 ($)", fontsize=12)
            ax.grid(True, alpha=0.3)

            # 添加收益率标注
            initial_value = portfolio_value[0]
            final_value = portfolio_value[-1]
            total_return = ((final_value - initial_value) / initial_value) * 100

            ax.text(
                0.02,
                0.98,
                f"总收益率: {total_return: .2f}%",
                transform=ax.transAxes,
                fontsize=12,
                bbox=dict(boxstyle="round, pad=0.3", facecolor="lightblue", alpha=0.7),
                verticalalignment="top",
            )

            plt.tight_layout()

            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close()

            return f"data: image/png; base64, {chart_data}"

        except Exception as e:
            self.logger.error(f"创建组合价值图表失败: {e}")
            return ""

    def _create_drawdown_chart(
        self, portfolio_value: List[float], symbol: str, strategy: str
    ) -> str:
        """创建回撤图表"""
        try:
            fig, ax = plt.subplots(figsize=(12, 6))

            # 计算回撤
            returns = pd.Series(portfolio_value).pct_change().dropna()
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max * 100

            dates = pd.date_range(start="2023-01-01", periods=len(drawdown), freq="D")
            ax.fill_between(dates, drawdown, 0, color="red", alpha=0.3)
            ax.plot(dates, drawdown, color="red", linewidth=1)

            ax.set_title(
                f"{symbol} - {strategy} 策略回撤分析", fontsize=14, fontweight="bold"
            )
            ax.set_xlabel("日期", fontsize=12)
            ax.set_ylabel("回撤 (%)", fontsize=12)
            ax.grid(True, alpha=0.3)

            # 添加最大回撤标注
            max_drawdown = drawdown.min()
            ax.text(
                0.02,
                0.02,
                f"最大回撤: {max_drawdown: .2f}%",
                transform=ax.transAxes,
                fontsize=12,
                bbox=dict(boxstyle="round, pad=0.3", facecolor="lightcoral", alpha=0.7),
            )

            plt.tight_layout()

            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close()

            return f"data: image/png; base64, {chart_data}"

        except Exception as e:
            self.logger.error(f"创建回撤图表失败: {e}")
            return ""

    def _create_returns_distribution_chart(
        self, portfolio_value: List[float], symbol: str, strategy: str
    ) -> str:
        """创建收益分布图表"""
        try:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

            # 计算日收益率
            returns = pd.Series(portfolio_value).pct_change().dropna() * 100

            # 直方图
            ax1.hist(returns, bins=30, alpha=0.7, color="skyblue", edgecolor="black")
            ax1.axvline(
                returns.mean(),
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"平均: {returns.mean(): .2f}%",
            )
            ax1.set_title("日收益率分布", fontsize=14, fontweight="bold")
            ax1.set_xlabel("日收益率 (%)", fontsize=12)
            ax1.set_ylabel("频次", fontsize=12)
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # Q-Q图
            from scipy import stats

            stats.probplot(returns, dist="norm", plot=ax2)
            ax2.set_title("Q-Q图 (正态性检验)", fontsize=14, fontweight="bold")
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()

            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close()

            return f"data: image/png; base64, {chart_data}"

        except Exception as e:
            self.logger.error(f"创建收益分布图表失败: {e}")
            return ""

    def export_to_csv(self, data: Dict[str, Any], filename: str) -> str:
        """导出数据到CSV"""
        try:
            csv_path = self.output_dir / f"{filename}.csv"

            # 处理不同类型的数据
            if "portfolio_value" in data:
                df = pd.DataFrame(
                    {
                        "Date": pd.date_range(
                            start="2023-01-01",
                            periods=len(data["portfolio_value"]),
                            freq="D",
                        ),
                        "Portfolio_Value": data["portfolio_value"],
                        "Signals": data.get(
                            "signals", [0] * len(data["portfolio_value"])
                        ),
                    }
                )
                df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            else:
                # 将字典数据转换为CSV
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Metric", "Value"])

                    def write_dict(d, prefix=""):
                        for key, value in d.items():
                            if isinstance(value, dict):
                                write_dict(value, f"{prefix}{key}.")
                            else:
                                writer.writerow([f"{prefix}{key}", value])

                    write_dict(data)

            self.logger.info(f"数据导出到CSV完成: {csv_path}")
            return str(csv_path)

        except Exception as e:
            self.logger.error(f"导出CSV失败: {e}")
            raise

    def export_to_excel(self, data: Dict[str, Any], filename: str) -> str:
        """导出数据到Excel"""
        try:
            excel_path = self.output_dir / f"{filename}.xlsx"

            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                # 组合价值数据
                if "portfolio_value" in data:
                    df = pd.DataFrame(
                        {
                            "Date": pd.date_range(
                                start="2023-01-01",
                                periods=len(data["portfolio_value"]),
                                freq="D",
                            ),
                            "Portfolio_Value": data["portfolio_value"],
                            "Signals": data.get(
                                "signals", [0] * len(data["portfolio_value"])
                            ),
                        }
                    )
                    df.to_excel(writer, sheet_name="Portfolio_Data", index=False)

                # 性能指标
                if "performance_metrics" in data:
                    metrics_df = pd.DataFrame(
                        list(data["performance_metrics"].items()),
                        columns=["Metric", "Value"],
                    )
                    metrics_df.to_excel(
                        writer, sheet_name="Performance_Metrics", index=False
                    )

                # 风险指标
                if "risk_metrics" in data:
                    risk_df = pd.DataFrame(
                        list(data["risk_metrics"].items()), columns=["Metric", "Value"]
                    )
                    risk_df.to_excel(writer, sheet_name="Risk_Metrics", index=False)

                # 交易分析
                if "trade_analysis" in data:
                    trade_df = pd.DataFrame(
                        list(data["trade_analysis"].items()),
                        columns=["Metric", "Value"],
                    )
                    trade_df.to_excel(writer, sheet_name="Trade_Analysis", index=False)

            self.logger.info(f"数据导出到Excel完成: {excel_path}")
            return str(excel_path)

        except Exception as e:
            self.logger.error(f"导出Excel失败: {e}")
            raise


# 全局实例
data_exporter = DataExporter()
