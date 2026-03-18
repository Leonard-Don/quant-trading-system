"""
Backtest engine for testing trading strategies
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List
import logging
from .metrics import (
    calculate_annualized_return,
    calculate_sharpe_ratio, 
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_calmar_ratio,
    calculate_volatility,
    calculate_var
)

logger = logging.getLogger(__name__)


class Backtester:
    """Simple backtesting engine"""

    def __init__(
        self,
        initial_capital: float = 100000,
        commission: float = 0.001,
        slippage: float = 0.001,
    ):
        """
        Initialize backtester

        Args:
            initial_capital: Starting capital
            commission: Commission rate (e.g., 0.001 = 0.1%)
            slippage: Slippage rate
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.results = {}

    def run(
        self, strategy: Any, data: pd.DataFrame, position_size: float = 1.0
    ) -> Dict[str, Any]:
        """
        Run backtest

        Args:
            strategy: Strategy object with generate_signals method
            data: DataFrame with OHLCV data
            position_size: Position size as fraction of capital (1.0 = 100%)

        Returns:
            Dictionary with backtest results
        """
        if data.empty:
            logger.error("No data provided for backtest")
            return {}

        data = self._prepare_market_data(data)
        if data.empty:
            logger.error("No valid price data remaining after cleaning")
            return {}

        # Generate signals
        signals = strategy.generate_signals(data)

        # Initialize portfolio with proper data types
        portfolio = pd.DataFrame(index=data.index)
        portfolio["price"] = data["close"].astype(float)
        portfolio["signal"] = signals.astype(int)
        portfolio["position"] = 0.0
        portfolio["cash"] = 0.0
        portfolio["holdings"] = 0.0
        portfolio["total"] = 0.0
        portfolio["returns"] = 0.0

        # Track trades
        trades = []
        current_position = 0
        current_cash = self.initial_capital
        buy_price = 0  # Track buy price for PnL calculation

        for i in range(len(portfolio)):
            price = portfolio["price"].iloc[i]
            signal = portfolio["signal"].iloc[i]

            # Process signals
            if signal == 1 and current_position == 0:  # Buy
                # Calculate position size
                position_value = current_cash * position_size
                execution_multiplier = (1 + self.slippage) * (1 + self.commission)
                shares = int(position_value / (price * execution_multiplier))

                if shares > 0:
                    cost = shares * price * (1 + self.slippage)
                    commission_cost = cost * self.commission
                    total_cost = cost + commission_cost

                    if total_cost <= current_cash:
                        current_cash -= total_cost
                        current_position = shares
                        buy_price = price * (
                            1 + self.slippage
                        )  # Include slippage in buy price

                        trades.append(
                            {
                                "date": portfolio.index[i],
                                "type": "BUY",
                                "price": price,
                                "shares": shares,
                                "cost": total_cost,
                                "pnl": 0,  # Buy trades have no PnL
                            }
                        )

            elif signal == -1 and current_position > 0:  # Sell
                revenue = current_position * price * (1 - self.slippage)
                commission_cost = revenue * self.commission
                total_revenue = revenue - commission_cost

                # Calculate PnL for this trade
                total_cost = current_position * buy_price + (
                    current_position * buy_price * self.commission
                )
                pnl = total_revenue - total_cost

                current_cash += total_revenue

                trades.append(
                    {
                        "date": portfolio.index[i],
                        "type": "SELL",
                        "price": price,
                        "shares": current_position,
                        "revenue": total_revenue,
                        "pnl": pnl,
                    }
                )

                current_position = 0
                buy_price = 0

            # Update portfolio after processing each bar, including the first bar.
            portfolio.loc[portfolio.index[i], "position"] = current_position
            portfolio.loc[portfolio.index[i], "cash"] = float(current_cash)
            portfolio.loc[portfolio.index[i], "holdings"] = float(
                current_position * price
            )
            portfolio.loc[portfolio.index[i], "total"] = float(
                current_cash + (current_position * price)
            )

        # Calculate returns
        portfolio["returns"] = portfolio["total"].pct_change()

        # Calculate metrics
        results = self._calculate_metrics(portfolio, trades)
        results["portfolio"] = portfolio
        results["trades"] = trades

        self.results = results
        return results

    def _prepare_market_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Drop incomplete bars so NaN market data cannot zero out the portfolio."""
        cleaned = data.copy()

        if "close" not in cleaned.columns:
            logger.error("Backtest data is missing required 'close' column")
            return pd.DataFrame()

        numeric_cols = [col for col in ["open", "high", "low", "close", "volume"] if col in cleaned.columns]
        for col in numeric_cols:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")

        before = len(cleaned)
        cleaned = cleaned[np.isfinite(cleaned["close"])]
        cleaned = cleaned[cleaned["close"] > 0]
        dropped = before - len(cleaned)

        if dropped > 0:
            logger.info("Dropped %s incomplete market bars before backtest execution", dropped)

        return cleaned

    def _calculate_metrics(
        self, portfolio: pd.DataFrame, trades: list
    ) -> Dict[str, Any]:
        """Calculate performance metrics"""
        total_return = (
            portfolio["total"].iloc[-1] - self.initial_capital
        ) / self.initial_capital

        # Calculate annualized return
        days = len(portfolio)
        annualized_return = calculate_annualized_return(total_return, days)

        # Get daily returns series
        returns = portfolio["returns"].dropna()

        # Calculate Sharpe ratio
        sharpe_ratio = calculate_sharpe_ratio(returns)

        # Calculate max drawdown
        portfolio_values = portfolio["total"].values
        max_drawdown = calculate_max_drawdown(portfolio_values)

        # Trade statistics
        num_trades = len(trades)
        buy_trades = [t for t in trades if t["type"] == "BUY"]
        sell_trades = [t for t in trades if t["type"] == "SELL"]

        # Calculate trade-based metrics from completed BUY -> SELL pairs only
        completed_trade_pnls: List[float] = []
        completed_trade_returns: List[float] = []
        has_open_position = False

        i = 0
        while i < len(trades):
            if trades[i]["type"] == "BUY":
                if i + 1 < len(trades) and trades[i + 1]["type"] == "SELL":
                    buy_trade = trades[i]
                    sell_trade = trades[i + 1]

                    entry_value = buy_trade.get("cost") or (
                        buy_trade["price"] * buy_trade["shares"]
                    )
                    trade_pnl = sell_trade.get("pnl")
                    if trade_pnl is None:
                        exit_value = sell_trade.get("revenue") or (
                            sell_trade["price"] * sell_trade["shares"]
                        )
                        trade_pnl = exit_value - entry_value

                    trade_return = trade_pnl / entry_value if entry_value else 0.0

                    completed_trade_pnls.append(float(trade_pnl))
                    completed_trade_returns.append(float(trade_return))

                    i += 2
                else:
                    has_open_position = True
                    buy_trade = trades[i]
                    current_price = float(portfolio["price"].iloc[-1])
                    unrealized_pnl = (current_price - buy_trade["price"]) * buy_trade[
                        "shares"
                    ]

                    logger.info(
                        "检测到未平仓头寸: 买入价格=%.2f, 当前价格=%.2f, 未实现盈亏=%.2f",
                        buy_trade["price"],
                        current_price,
                        unrealized_pnl,
                    )
                    i += 1
            else:
                logger.warning(f"发现非BUY起始的交易: {trades[i]}")
                i += 1

        winning_trades = [pnl for pnl in completed_trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in completed_trade_pnls if pnl < 0]

        # Calculate win rate based on completed trades only
        total_completed_trades = len(completed_trade_pnls)
        win_rate = (
            len(winning_trades) / total_completed_trades if total_completed_trades > 0 else 0
        )

        # Calculate profit factor (gross profit / gross loss)
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0)
        )

        # Calculate best and worst trades
        best_trade = (
            max(completed_trade_pnls) if completed_trade_pnls else 0
        )
        worst_trade = (
            min(completed_trade_pnls) if completed_trade_pnls else 0
        )

        # Calculate net profit
        net_profit = portfolio["total"].iloc[-1] - self.initial_capital

        # Calculate consecutive wins/losses
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0

        for trade_pnl in completed_trade_pnls:
            if trade_pnl > 0:
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
            elif trade_pnl < 0:
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_wins = 0
                consecutive_losses = 0

        # Calculate average trade
        avg_trade = (
            sum(completed_trade_pnls) / len(completed_trade_pnls)
            if completed_trade_pnls
            else 0
        )

        # Calculate Sortino ratio (downside deviation)
        sortino_ratio = calculate_sortino_ratio(returns)

        # Calculate Calmar ratio (annual return / max drawdown)
        calmar_ratio = calculate_calmar_ratio(annualized_return, max_drawdown)

        # Calculate annualized volatility
        volatility = calculate_volatility(returns)
        
        # Calculate Value at Risk (95% confidence)
        var_95 = calculate_var(returns)

        metrics = {
            "initial_capital": self.initial_capital,
            "final_value": portfolio["total"].iloc[-1],
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "num_trades": num_trades,
            "num_buy_trades": len(buy_trades),
            "num_sell_trades": len(sell_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "net_profit": net_profit,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "avg_trade": avg_trade,
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "total_completed_trades": total_completed_trades,
            "has_open_position": has_open_position,  # 标记是否有未平仓头寸
        }

        return metrics

    def plot_results(self, show: bool = True):
        """Plot backtest results"""
        if not self.results or "portfolio" not in self.results:
            logger.error("No results to plot")
            return

        import matplotlib.pyplot as plt

        portfolio = self.results["portfolio"]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10))

        # Plot portfolio value
        axes[0].plot(portfolio.index, portfolio["total"], label="Portfolio Value")
        axes[0].axhline(
            y=self.initial_capital, color="r", linestyle="--", label="Initial Capital"
        )
        axes[0].set_ylabel("Portfolio Value ($)")
        axes[0].set_title("Portfolio Performance")
        axes[0].legend()
        axes[0].grid(True)

        # Plot price and signals
        axes[1].plot(portfolio.index, portfolio["price"], label="Price", alpha=0.7)

        # Mark buy signals
        buy_signals = portfolio[portfolio["signal"] == 1]
        if not buy_signals.empty:
            axes[1].scatter(
                buy_signals.index,
                buy_signals["price"],
                color="green",
                marker="^",
                s=100,
                label="Buy",
            )

        # Mark sell signals
        sell_signals = portfolio[portfolio["signal"] == -1]
        if not sell_signals.empty:
            axes[1].scatter(
                sell_signals.index,
                sell_signals["price"],
                color="red",
                marker="v",
                s=100,
                label="Sell",
            )

        axes[1].set_ylabel("Price ($)")
        axes[1].set_title("Price and Trading Signals")
        axes[1].legend()
        axes[1].grid(True)

        # Plot returns
        axes[2].plot(
            portfolio.index, portfolio["returns"].cumsum(), label="Cumulative Returns"
        )
        axes[2].set_ylabel("Cumulative Returns")
        axes[2].set_xlabel("Date")
        axes[2].set_title("Cumulative Returns")
        axes[2].legend()
        axes[2].grid(True)

        plt.tight_layout()

        if show:
            plt.show()

        return fig

    def print_summary(self):
        """Print summary of backtest results"""
        if not self.results:
            logger.error("No results to display")
            return

        metrics = self.results

        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Initial Capital:       ${metrics['initial_capital']:,.2f}")
        print(f"Final Value:           ${metrics['final_value']:,.2f}")
        print(f"Net Profit:            ${metrics['net_profit']:,.2f}")
        print(f"Total Return:          {metrics['total_return']:.2%}")
        print(f"Annualized Return:     {metrics['annualized_return']:.2%}")
        print("-" * 60)
        print("RISK METRICS")
        print("-" * 60)
        print(f"Sharpe Ratio:          {metrics['sharpe_ratio']:.2f}")
        print(f"Sortino Ratio:         {metrics['sortino_ratio']:.2f}")
        print(f"Calmar Ratio:          {metrics['calmar_ratio']:.2f}")
        print(f"Max Drawdown:          {metrics['max_drawdown']:.2%}")
        print(f"Value at Risk (95%):   {metrics['var_95']:.2%}")
        print("-" * 60)
        print("TRADE STATISTICS")
        print("-" * 60)
        print(f"Total Trades:          {metrics['num_trades']}")
        print(f"Completed Trades:      {metrics['total_completed_trades']}")
        print(f"Win Rate:              {metrics['win_rate']:.2%}")
        print(f"Profit Factor:         {metrics['profit_factor']:.2f}")
        print(f"Average Trade:         ${metrics['avg_trade']:,.2f}")
        print(f"Best Trade:            ${metrics['best_trade']:,.2f}")
        print(f"Worst Trade:           ${metrics['worst_trade']:,.2f}")
        print(f"Max Consecutive Wins:  {metrics['max_consecutive_wins']}")
        print(f"Max Consecutive Losses: {metrics['max_consecutive_losses']}")
        print(f"Gross Profit:          ${metrics['gross_profit']:,.2f}")
        print(f"Gross Loss:            ${metrics['gross_loss']:,.2f}")
        print("=" * 60)
