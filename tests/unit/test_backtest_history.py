import json
import sqlite3

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


def test_history_statistics_support_symbol_and_strategy_filters(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    history.save(
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "performance_metrics": {
                "total_return": 0.05,
                "num_trades": 1,
                "final_value": 10500,
            },
        }
    )
    history.save(
        {
            "symbol": "MSFT",
            "strategy": "macd",
            "performance_metrics": {
                "total_return": 0.12,
                "num_trades": 4,
                "final_value": 11200,
            },
        }
    )

    symbol_stats = history.get_statistics(symbol="MSFT")
    strategy_stats = history.get_statistics(strategy="buy_and_hold")

    assert symbol_stats["total_records"] == 1
    assert symbol_stats["avg_return"] == 0.12
    assert symbol_stats["most_tested_symbol"] == "MSFT"

    assert strategy_stats["total_records"] == 1
    assert strategy_stats["most_used_strategy"] == "buy_and_hold"


def test_history_supports_offset_pagination(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    for index in range(3):
        history.save(
            {
                "symbol": "AAPL",
                "strategy": "buy_and_hold",
                "performance_metrics": {
                    "total_return": 0.01 * index,
                    "num_trades": index + 1,
                    "final_value": 10000 + index,
                },
            }
        )

    page = history.get_history(limit=1, offset=1)

    assert len(page) == 1
    assert page[0]["metrics"]["num_trades"] == 2


def test_history_persists_extended_metrics_summary(tmp_path):
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
                "recovery_factor": 1250,
                "expectancy": 82.5,
                "avg_win": 300,
                "avg_loss": -120,
                "total_profit": 900,
                "total_loss": -240,
                "loss_rate": 0.25,
                "avg_holding_days": 6.5,
                "total_completed_trades": 2,
                "has_open_position": True,
            },
        }
    )

    saved = history.get_by_id(record_id)

    assert saved is not None
    assert saved["metrics"]["recovery_factor"] == 1250
    assert saved["metrics"]["expectancy"] == 82.5
    assert saved["metrics"]["avg_win"] == 300
    assert saved["metrics"]["avg_loss"] == -120
    assert saved["metrics"]["total_profit"] == 900
    assert saved["metrics"]["total_loss"] == -240
    assert saved["metrics"]["loss_rate"] == 0.25
    assert saved["metrics"]["avg_holding_days"] == 6.5
    assert saved["metrics"]["total_completed_trades"] == 2
    assert saved["metrics"]["has_open_position"] is True


def test_history_persists_code_version_metadata(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    record_id = history.save(
        {
            "symbol": "AAPL",
            "strategy": "moving_average",
            "performance_metrics": {
                "total_return": 0.1,
                "num_trades": 2,
                "final_value": 11000,
            },
            "code_version": "abc1234",
        }
    )

    saved = history.get_by_id(record_id)

    assert saved is not None
    assert saved["code_version"] == "abc1234"
    assert saved["strategy_version"] == "abc1234"


def test_history_persists_advanced_experiment_records_without_backtest_normalization(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    record_id = history.save(
        {
            "record_type": "batch_backtest",
            "title": "批量回测 · AAPL",
            "symbol": "AAPL",
            "strategy": "batch_backtest",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "parameters": {"ranking_metric": "sharpe_ratio"},
            "metrics": {
                "total_return": 0.11,
                "sharpe_ratio": 1.3,
                "total_tasks": 3,
                "successful": 2,
            },
            "result": {
                "summary": {
                    "total_tasks": 3,
                    "successful": 2,
                    "average_return": 0.11,
                    "average_sharpe": 1.3,
                },
                "results": [
                    {"task_id": "task_1", "strategy": "moving_average", "success": True, "metrics": {"total_return": 0.12}},
                ],
            },
        }
    )

    saved = history.get_by_id(record_id)

    assert saved is not None
    assert saved["record_type"] == "batch_backtest"
    assert saved["title"] == "批量回测 · AAPL"
    assert saved["metrics"]["total_tasks"] == 3
    assert saved["result"]["summary"]["successful"] == 2


def test_history_statistics_support_record_type_filter(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    history.save(
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "performance_metrics": {
                "total_return": 0.05,
                "num_trades": 1,
                "final_value": 10500,
            },
        }
    )
    history.save(
        {
            "record_type": "batch_backtest",
            "title": "批量回测 · AAPL",
            "symbol": "AAPL",
            "strategy": "batch_backtest",
            "metrics": {
                "total_return": 0.12,
                "total_tasks": 2,
            },
            "result": {
                "summary": {
                    "total_tasks": 2,
                },
            },
        }
    )

    stats = history.get_statistics(record_type="batch_backtest")
    records = history.get_history(limit=10, record_type="batch_backtest")

    assert stats["total_records"] == 1
    assert stats["record_types"]["batch_backtest"] == 1
    assert len(records) == 1
    assert records[0]["record_type"] == "batch_backtest"


def test_history_persists_sqlite_mirror(tmp_path):
    history = BacktestHistory(storage_path=tmp_path, max_records=10)

    history.save(
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "performance_metrics": {
                "total_return": 0.05,
                "num_trades": 1,
                "final_value": 10500,
            },
        }
    )

    sqlite_file = tmp_path / "history.sqlite3"
    assert sqlite_file.exists()

    with sqlite3.connect(sqlite_file) as connection:
        count = connection.execute("SELECT COUNT(*) FROM backtest_history").fetchone()[0]

    assert count == 1


def test_history_migrates_existing_json_records_into_sqlite(tmp_path):
    history_file = tmp_path / "history.json"
    history_file.write_text(
        json.dumps(
            [
                {
                    "id": "bt_existing",
                    "timestamp": "2026-03-30T10:00:00",
                    "symbol": "AAPL",
                    "strategy": "buy_and_hold",
                    "start_date": "2025-01-01",
                    "end_date": "2025-06-30",
                    "parameters": {},
                    "metrics": {"total_return": 0.12, "num_trades": 1, "total_trades": 1, "final_value": 11200},
                    "result": {
                        "symbol": "AAPL",
                        "strategy": "buy_and_hold",
                        "initial_capital": 10000,
                        "final_value": 11200,
                        "total_return": 0.12,
                        "num_trades": 1,
                        "trades": [],
                        "portfolio_history": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    history = BacktestHistory(storage_path=tmp_path, max_records=10)
    saved = history.get_by_id("bt_existing")

    assert saved is not None
    with sqlite3.connect(tmp_path / "history.sqlite3") as connection:
        count = connection.execute("SELECT COUNT(*) FROM backtest_history").fetchone()[0]
        record_id = connection.execute("SELECT id FROM backtest_history").fetchone()[0]

    assert count == 1
    assert record_id == "bt_existing"
