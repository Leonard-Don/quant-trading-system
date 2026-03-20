import pandas as pd

from src.backtest.batch_backtester import BatchBacktester, BacktestTask, WalkForwardAnalyzer


class DummyBacktester:
    def __init__(self, initial_capital=10000, commission=0.001, slippage=0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(self, strategy, data):
        return {
            "initial_capital": self.initial_capital,
            "final_value": self.initial_capital * 1.1,
            "total_return": 0.1,
            "annualized_return": 0.12,
            "net_profit": self.initial_capital * 0.1,
            "sharpe_ratio": 1.5,
            "max_drawdown": -0.05,
            "sortino_ratio": 1.8,
            "calmar_ratio": 2.0,
            "num_trades": 2,
            "win_rate": 0.5,
            "profit_factor": 1.4,
            "best_trade": 200,
            "worst_trade": -80,
            "max_consecutive_wins": 1,
            "max_consecutive_losses": 1,
            "portfolio_history": [
                {
                    "date": "2024-01-01",
                    "total": self.initial_capital,
                    "cash": self.initial_capital,
                    "holdings": 0,
                    "position": 0,
                    "returns": 0,
                    "signal": 1,
                },
                {
                    "date": "2024-01-02",
                    "total": self.initial_capital * 1.1,
                    "cash": 0,
                    "holdings": self.initial_capital * 1.1,
                    "position": 10,
                    "returns": 0.1,
                    "signal": -1,
                },
            ],
            "trades": [
                {"date": "2024-01-01", "type": "BUY", "price": 100, "shares": 10, "value": 1000},
                {"date": "2024-01-02", "type": "SELL", "price": 110, "shares": 10, "value": 1100, "pnl": 100},
            ],
        }


def _backtester_factory(initial_capital=10000, commission=0.001, slippage=0.001):
    return DummyBacktester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )


def _strategy_factory(name=None, parameters=None):
    return {"name": name, "parameters": parameters or {}}


def _data_fetcher(symbol, start_date=None, end_date=None):
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    return pd.DataFrame({
        "open": range(10, 20),
        "high": range(11, 21),
        "low": range(9, 19),
        "close": range(10, 20),
        "volume": [1_000_000] * 10,
    }, index=dates)


def test_batch_backtester_reads_metrics_from_normalized_top_level_results():
    batch = BatchBacktester()
    results = batch.run_batch(
        tasks=[
            BacktestTask(
                task_id="task-1",
                symbol="AAPL",
                strategy_name="buy_and_hold",
                parameters={},
                initial_capital=10000,
            )
        ],
        backtester_factory=_backtester_factory,
        strategy_factory=_strategy_factory,
        data_fetcher=_data_fetcher,
    )

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].metrics["total_return"] == 0.1
    assert results[0].metrics["sharpe_ratio"] == 1.5


def test_walk_forward_analyzer_uses_normalized_results_metrics():
    analyzer = WalkForwardAnalyzer(train_period=5, test_period=3, step_size=2)
    dates = pd.date_range("2024-01-01", periods=15, freq="D")
    data = pd.DataFrame({
        "open": range(15),
        "high": range(1, 16),
        "low": range(15),
        "close": range(10, 25),
        "volume": [1_000_000] * 15,
    }, index=dates)

    result = analyzer.analyze(
        data=data,
        strategy_factory=lambda: _strategy_factory("buy_and_hold", {}),
        backtester_factory=lambda: _backtester_factory(10000),
    )

    assert result["n_windows"] > 0
    assert result["aggregate_metrics"]["average_return"] == 0.1
    assert result["aggregate_metrics"]["average_sharpe"] == 1.5
