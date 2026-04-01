import pandas as pd
import pytest

from src.backtest.portfolio_backtester import PortfolioBacktester
from src.backtest.signal_adapter import SignalAdapter


class LongShortStrategy:
    def generate_signals(self, price_matrix: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "AAA": [0.5, 0.5, 0.5, 0.5],
                "BBB": [-0.5, -0.5, -0.5, -0.5],
            },
            index=price_matrix.index,
        )


def test_signal_adapter_normalizes_target_weights_and_caps_gross_exposure():
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    raw = pd.DataFrame({"AAA": [1.0, 1.0], "BBB": [1.0, -1.0]}, index=index)

    normalized = SignalAdapter.normalize_target_weights(
        raw,
        index=index,
        columns=["AAA", "BBB"],
        max_gross_exposure=1.0,
    )

    assert normalized.abs().sum(axis=1).max() == pytest.approx(1.0)


def test_portfolio_backtester_supports_long_short_target_weights():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    prices = pd.DataFrame(
        {
            "AAA": [100, 105, 110, 115],
            "BBB": [100, 95, 90, 85],
        },
        index=dates,
    )

    result = PortfolioBacktester(
        initial_capital=10000,
        commission=0,
        slippage=0,
        allow_fractional_shares=True,
        max_gross_exposure=1.0,
    ).run(LongShortStrategy(), prices)

    assert result["num_trades"] > 0
    assert result["final_value"] > result["initial_capital"]
    assert "positions_history" in result
    last_positions = result["positions_history"][-1]
    assert last_positions["AAA"] > 0
    assert last_positions["BBB"] < 0
    assert set(result["assets"]) == {"AAA", "BBB"}
