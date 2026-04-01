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


class TunableBacktester:
    def __init__(self, initial_capital=10000, commission=0.001, slippage=0.001):
        self.initial_capital = initial_capital

    def run(self, strategy, data):
        parameters = strategy.get("parameters", {})
        edge = float(parameters.get("edge", 0))
        regime_bias = 0.08 if float(data["close"].iloc[-1]) > float(data["close"].iloc[0]) else -0.03
        total_return = regime_bias + edge
        sharpe_ratio = 0.8 + (edge * 10)
        final_value = self.initial_capital * (1 + total_return)
        return {
            "initial_capital": self.initial_capital,
            "final_value": final_value,
            "total_return": total_return,
            "annualized_return": total_return,
            "net_profit": final_value - self.initial_capital,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": -0.06,
            "sortino_ratio": sharpe_ratio + 0.2,
            "calmar_ratio": 1.5,
            "num_trades": 1,
            "win_rate": 1.0 if total_return > 0 else 0.0,
            "profit_factor": 1.2,
            "best_trade": max(final_value - self.initial_capital, 0),
            "worst_trade": min(final_value - self.initial_capital, 0),
            "max_consecutive_wins": 1 if total_return > 0 else 0,
            "max_consecutive_losses": 1 if total_return <= 0 else 0,
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
                    "total": final_value,
                    "cash": final_value,
                    "holdings": 0,
                    "position": 0,
                    "returns": total_return,
                    "signal": -1,
                },
            ],
            "trades": [],
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


def _tunable_backtester_factory(initial_capital=10000, commission=0.001, slippage=0.001):
    return TunableBacktester(initial_capital=initial_capital, commission=commission, slippage=slippage)


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


def test_batch_backtester_summary_exposes_best_result_risk_metrics():
    batch = BatchBacktester()
    batch.run_batch(
        tasks=[
            BacktestTask(
                task_id="task-1",
                symbol="AAPL",
                strategy_name="buy_and_hold",
                parameters={},
                initial_capital=10000,
                research_label="低成本",
            )
        ],
        backtester_factory=_backtester_factory,
        strategy_factory=_strategy_factory,
        data_fetcher=_data_fetcher,
    )

    summary = batch.get_summary()

    assert summary["best_result"]["research_label"] == "低成本"
    assert summary["best_result"]["max_drawdown"] == -0.05
    assert summary["best_result"]["final_value"] == 11000


def test_batch_backtester_preserves_research_label_for_failed_tasks():
    batch = BatchBacktester()

    results = batch.run_batch(
        tasks=[
            BacktestTask(
                task_id="task-fail",
                symbol="AAPL",
                strategy_name="broken_strategy",
                parameters={},
                initial_capital=10000,
                research_label="高成本",
            )
        ],
        backtester_factory=_backtester_factory,
        strategy_factory=lambda name=None, parameters=None: (_ for _ in ()).throw(RuntimeError("boom")),
        data_fetcher=_data_fetcher,
    )

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].research_label == "高成本"
    assert "boom" in results[0].error


def test_walk_forward_analyzer_optimizes_parameters_on_training_windows():
    analyzer = WalkForwardAnalyzer(train_period=5, test_period=3, step_size=2)
    dates = pd.date_range("2024-01-01", periods=16, freq="D")
    data = pd.DataFrame({
        "open": range(16),
        "high": range(1, 17),
        "low": range(16),
        "close": [10, 11, 12, 13, 14, 13, 12, 11, 15, 16, 17, 18, 14, 13, 12, 11],
        "volume": [1_000_000] * 16,
    }, index=dates)

    result = analyzer.analyze(
        data=data,
        strategy_factory=lambda parameters=None: _strategy_factory("moving_average", parameters or {}),
        backtester_factory=lambda: _tunable_backtester_factory(10000),
        parameter_candidates=[
            {"edge": 0.0},
            {"edge": 0.04},
            {"edge": 0.08},
        ],
        optimization_metric="sharpe_ratio",
        monte_carlo_simulations=50,
    )

    assert result["n_windows"] > 0
    assert all(window["selected_parameters"]["edge"] == 0.08 for window in result["window_results"])
    assert result["aggregate_metrics"]["parameter_stability"] == 1.0
    assert result["window_results"][0]["train_metrics"]["sharpe_ratio"] > 0


def test_walk_forward_analyzer_emits_monte_carlo_and_overfitting_diagnostics():
    analyzer = WalkForwardAnalyzer(train_period=5, test_period=3, step_size=2)
    dates = pd.date_range("2024-01-01", periods=16, freq="D")
    data = pd.DataFrame({
        "open": range(16),
        "high": range(1, 17),
        "low": range(16),
        "close": [10, 11, 12, 13, 14, 9, 8, 7, 15, 16, 17, 18, 10, 9, 8, 7],
        "volume": [1_000_000] * 16,
    }, index=dates)

    result = analyzer.analyze(
        data=data,
        strategy_factory=lambda parameters=None: _strategy_factory("moving_average", parameters or {}),
        backtester_factory=lambda: _tunable_backtester_factory(10000),
        parameter_candidates=[
            {"edge": 0.0},
            {"edge": 0.06},
        ],
        monte_carlo_simulations=40,
    )

    assert result["monte_carlo"]["available"] is True
    assert result["monte_carlo"]["simulations"] == 40
    assert "level" in result["overfitting_diagnostics"]
    assert isinstance(result["overfitting_diagnostics"]["warnings"], list)


def test_walk_forward_analyzer_supports_bayesian_optimization_budget():
    analyzer = WalkForwardAnalyzer(train_period=5, test_period=3, step_size=2)
    dates = pd.date_range("2024-01-01", periods=18, freq="D")
    data = pd.DataFrame({
        "open": range(18),
        "high": range(1, 19),
        "low": range(18),
        "close": [10, 11, 12, 13, 14, 13, 12, 11, 15, 16, 17, 18, 19, 20, 17, 16, 15, 14],
        "volume": [1_000_000] * 18,
    }, index=dates)

    result = analyzer.analyze(
        data=data,
        strategy_factory=lambda parameters=None: _strategy_factory("moving_average", parameters or {}),
        backtester_factory=lambda: _tunable_backtester_factory(10000),
        parameter_candidates=[
            {"edge": 0.0},
            {"edge": 0.02},
            {"edge": 0.04},
            {"edge": 0.06},
            {"edge": 0.08},
        ],
        optimization_metric="sharpe_ratio",
        optimization_method="bayesian",
        optimization_budget=3,
        monte_carlo_simulations=30,
    )

    assert result["aggregate_metrics"]["optimization_method"] == "bayesian"
    assert result["aggregate_metrics"]["optimization_budget"] == 3
    assert all(window["optimization_method"] == "bayesian" for window in result["window_results"])
    assert all(window["evaluated_candidates"] <= 3 for window in result["window_results"])
