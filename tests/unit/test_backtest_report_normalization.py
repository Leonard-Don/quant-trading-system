import pandas as pd

from src.reporting.pdf_generator import PDFGenerator
from src.utils.data_validation import ensure_json_serializable


def test_pdf_generator_uses_num_trades_alias_in_fallback_report():
    generator = PDFGenerator()

    content = generator._generate_fallback_report(
        {
            "num_trades": 2,
            "total_return": 0.15,
            "annualized_return": 0.2,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.05,
            "win_rate": 0.5,
            "initial_capital": 10000,
            "final_value": 11500,
        },
        symbol="AAPL",
        strategy="moving_average",
    ).decode("utf-8")

    assert "总交易次数: 2" in content


def test_pdf_generator_normalizes_trade_fields_for_rendering():
    generator = PDFGenerator()

    trades = generator._resolve_trades(
        {
            "trades": [
                {
                    "date": "2024-01-01",
                    "type": "BUY",
                    "price": 100,
                    "shares": 10,
                    "cost": 1000,
                },
                {
                    "date": "2024-01-02",
                    "type": "SELL",
                    "price": 105,
                    "shares": 10,
                    "revenue": 1050,
                },
            ]
        }
    )

    assert trades[0]["action"] == "buy"
    assert trades[0]["quantity"] == 10
    assert trades[0]["value"] == 1000
    assert trades[1]["action"] == "sell"
    assert trades[1]["quantity"] == 10
    assert trades[1]["value"] == 1050


def test_ensure_json_serializable_preserves_dataframe_dates_in_records():
    payload = ensure_json_serializable(
        {
            "portfolio_history": pd.DataFrame(
                {
                    "total": [10000, 10100],
                    "signal": [0, 1],
                },
                index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            )
        }
    )

    assert payload["portfolio_history"][0]["date"].startswith("2024-01-02")
    assert payload["portfolio_history"][1]["date"].startswith("2024-01-03")


def test_ensure_json_serializable_replaces_infinite_numbers():
    payload = ensure_json_serializable(
        {
            "metrics": {
                "calmar_ratio": float("inf"),
                "profit_factor": float("-inf"),
            }
        }
    )

    assert payload["metrics"]["calmar_ratio"] == 0.0
    assert payload["metrics"]["profit_factor"] == 0.0
