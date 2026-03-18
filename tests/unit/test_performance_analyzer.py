from src.analytics.dashboard import PerformanceAnalyzer


def test_performance_analyzer_only_returns_extension_metrics():
    analyzer = PerformanceAnalyzer(
        {
            "profit_factor": 1.8,
            "trades": [
                {"date": "2024-01-01", "type": "BUY", "price": 100, "shares": 10, "cost": 1000},
                {"date": "2024-01-02", "type": "SELL", "price": 110, "shares": 10, "revenue": 1100, "pnl": 100},
                {"date": "2024-01-03", "type": "BUY", "price": 120, "shares": 5, "cost": 600},
                {"date": "2024-01-04", "type": "SELL", "price": 114, "shares": 5, "revenue": 570, "pnl": -30},
            ],
        }
    )

    metrics = analyzer.calculate_metrics()

    assert "profit_factor" not in metrics
    assert "total_return" not in metrics
    assert metrics["avg_win"] == 100
    assert metrics["avg_loss"] == -30
    assert metrics["loss_rate"] == 0.5
    assert metrics["total_profit"] == 100
    assert metrics["total_loss"] == -30
