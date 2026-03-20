import json

from src.reporting.data_exporter import DataExporter


def _sample_backtest_results():
    return {
        "initial_capital": 10000,
        "final_value": 11200,
        "total_return": 0.12,
        "annualized_return": 0.18,
        "net_profit": 1200,
        "sharpe_ratio": 1.4,
        "max_drawdown": -0.06,
        "sortino_ratio": 1.7,
        "calmar_ratio": 2.1,
        "num_trades": 2,
        "win_rate": 0.5,
        "profit_factor": 1.5,
        "best_trade": 300,
        "worst_trade": -100,
        "max_consecutive_wins": 1,
        "max_consecutive_losses": 1,
        "portfolio_history": [
            {"date": "2024-01-01", "total": 10000, "returns": 0, "signal": 1},
            {"date": "2024-01-02", "total": 10500, "returns": 0.05, "signal": 0},
            {"date": "2024-01-03", "total": 11200, "returns": 0.0666667, "signal": -1},
        ],
        "trades": [
            {"date": "2024-01-01", "type": "BUY", "price": 100, "shares": 10, "value": 1000},
            {"date": "2024-01-03", "type": "SELL", "price": 112, "shares": 10, "value": 1120, "pnl": 120},
        ],
    }


def test_data_exporter_generates_report_from_portfolio_history_and_trades(tmp_path):
    exporter = DataExporter(output_dir=tmp_path)

    report = exporter.generate_backtest_report(
        _sample_backtest_results(),
        symbol="AAPL",
        strategy_name="buy_and_hold",
        include_charts=False,
    )

    assert report["summary"]["initial_capital"] == 10000
    assert report["summary"]["final_value"] == 11200
    assert report["trade_analysis"]["total_trades"] == 1
    assert report["performance_metrics"]["total_return"] == 0.12

    saved_path = tmp_path / f'{report["report_id"]}.json'
    assert saved_path.exists()
    saved_report = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_report["summary"]["final_value"] == 11200


def test_data_exporter_csv_uses_normalized_portfolio_history(tmp_path):
    exporter = DataExporter(output_dir=tmp_path)

    csv_path = exporter.export_to_csv(_sample_backtest_results(), "normalized_backtest")

    csv_content = (tmp_path / "normalized_backtest.csv").read_text(encoding="utf-8-sig")
    assert csv_path.endswith("normalized_backtest.csv")
    assert "Portfolio_Value" in csv_content
    assert "11200" in csv_content
