import json

from src.backtest.history import BacktestHistory


def test_history_persists_num_trades_aliases(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    record_id = history.save(
        {
            "symbol": "AAPL",
            "strategy": "moving_average",
            "performance_metrics": {
                "total_return": 0.1,
                "annualized_return": 0.12,
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.08,
                "win_rate": 0.6,
                "num_trades": 4,
                "final_value": 11000,
            },
        }
    )

    saved = history.get_by_id(record_id)

    assert saved is not None
    assert saved["metrics"]["num_trades"] == 4
    assert saved["metrics"]["total_trades"] == 4


def test_history_repairs_corrupted_trailing_zero_snapshot(tmp_path):
    history_file = tmp_path / "history.json"
    corrupted_record = {
        "id": "bt_corrupted",
        "timestamp": "2026-03-17T15:00:00",
        "symbol": "AAPL",
        "strategy": "buy_and_hold",
        "start_date": "2026-03-10",
        "end_date": "2026-03-17",
        "parameters": {},
        "metrics": {
            "total_return": 0,
            "annualized_return": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "num_trades": 2,
            "total_trades": 2,
            "final_value": 0,
        },
        "result": {
            "initial_capital": 1000.0,
            "final_value": 0,
            "total_return": 0,
            "annualized_return": 0,
            "net_profit": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "sortino_ratio": 0,
            "calmar_ratio": 0,
            "volatility": 0,
            "var_95": 0,
            "num_trades": 2,
            "total_completed_trades": 1,
            "win_rate": 0,
            "profit_factor": 0,
            "portfolio": [
                {"date": "2026-03-10", "price": 100.0, "signal": 1, "position": 10.0, "cash": 0.0, "holdings": 1000.0, "total": 1000.0, "returns": 0.0},
                {"date": "2026-03-11", "price": 110.0, "signal": 0, "position": 10.0, "cash": 0.0, "holdings": 1100.0, "total": 1100.0, "returns": 0.1},
                {"date": "2026-03-12", "price": 130.0, "signal": 0, "position": 10.0, "cash": 0.0, "holdings": 1300.0, "total": 1300.0, "returns": 0.1818181818},
                {"date": "2026-03-13", "price": 0.0, "signal": -1, "position": 0.0, "cash": 0.0, "holdings": 0.0, "total": 0.0, "returns": 0.0},
            ],
            "trades": [
                {"date": "2026-03-10", "type": "BUY", "price": 100.0, "shares": 10, "cost": 1000.0, "pnl": 0.0},
                {"date": "2026-03-13", "type": "SELL", "price": 0.0, "shares": 10, "revenue": 0.0, "pnl": 0.0},
            ],
        },
    }
    history_file.write_text(json.dumps([corrupted_record]), encoding="utf-8")

    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    saved = history.get_by_id("bt_corrupted")

    assert saved is not None
    assert saved["metrics"]["final_value"] == 1300.0
    assert saved["metrics"]["total_return"] == 0.3
    assert saved["metrics"]["num_trades"] == 1
    assert saved["result"]["final_value"] == 1300.0
    assert saved["result"]["total_return"] == 0.3
    assert saved["result"]["num_trades"] == 1
    assert saved["result"]["total_completed_trades"] == 0
    assert saved["result"]["has_open_position"] is True
    assert len(saved["result"]["portfolio"]) == 3
    assert len(saved["result"]["trades"]) == 1

    persisted = json.loads(history_file.read_text(encoding="utf-8"))
    assert persisted[0]["result"]["final_value"] == 1300.0


def test_history_statistics_include_latest_record_metadata(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    history.save(
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "performance_metrics": {
                "total_return": 0.05,
                "annualized_return": 0.06,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.03,
                "win_rate": 1.0,
                "num_trades": 1,
                "final_value": 10500,
            },
        }
    )

    stats = history.get_statistics()

    assert stats["total_records"] == 1
    assert stats["strategy_count"] == 1
    assert stats["latest_record_at"] is not None
