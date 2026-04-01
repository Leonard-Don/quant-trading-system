import pandas as pd
import pytest

from src.backtest.execution_engine import PortfolioExecutionConfig, PortfolioExecutionEngine


def make_price_frame():
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame(
        {
            "AAA": [100.0, 102.0, 104.0],
            "BBB": [50.0, 49.0, 48.0],
        },
        index=index,
    )


def test_portfolio_execution_engine_skips_trades_below_min_trade_value():
    engine = PortfolioExecutionEngine(
        initial_capital=1_000,
        commission=0.0,
        slippage=0.0,
        config=PortfolioExecutionConfig(
            allow_fractional_shares=False,
            min_trade_value=2_000,
        ),
    )

    result = engine.execute(
        price_data=make_price_frame().iloc[:1],
        target_weights=pd.DataFrame({"AAA": [0.5], "BBB": [0.0]}, index=make_price_frame().index[:1]),
    )

    assert result["trades"] == []
    assert result["portfolio_history"]["total"].iloc[0] == pytest.approx(1_000.0)


def test_portfolio_execution_engine_respects_min_rebalance_weight_delta():
    prices = make_price_frame().iloc[:2]
    weights = pd.DataFrame({"AAA": [0.50, 0.53], "BBB": [0.0, 0.0]}, index=prices.index)
    engine = PortfolioExecutionEngine(
        initial_capital=10_000,
        commission=0.0,
        slippage=0.0,
        config=PortfolioExecutionConfig(
            min_rebalance_weight_delta=0.05,
        ),
    )

    result = engine.execute(price_data=prices, target_weights=weights)

    assert len(result["trades"]) == 1


def test_portfolio_execution_engine_caps_turnover_per_rebalance():
    prices = make_price_frame().iloc[:2]
    weights = pd.DataFrame({"AAA": [1.0, 0.0], "BBB": [0.0, 1.0]}, index=prices.index)
    engine = PortfolioExecutionEngine(
        initial_capital=10_000,
        commission=0.0,
        slippage=0.0,
        config=PortfolioExecutionConfig(
            allow_fractional_shares=False,
            max_turnover_per_rebalance=0.2,
        ),
    )

    result = engine.execute(price_data=prices, target_weights=weights)
    second_day_trades = [trade for trade in result["trades"] if trade["date"] == prices.index[1]]

    assert second_day_trades
    total_turnover = sum(abs(trade["shares"] * trade["price"]) for trade in second_day_trades)
    assert total_turnover <= 2_300.0


def test_portfolio_execution_engine_supports_short_weights_and_exposure_metrics():
    prices = make_price_frame().iloc[:1]
    weights = pd.DataFrame({"AAA": [0.6], "BBB": [-0.4]}, index=prices.index)
    engine = PortfolioExecutionEngine(
        initial_capital=10_000,
        commission=0.0,
        slippage=0.0,
        config=PortfolioExecutionConfig(allow_fractional_shares=True, max_gross_exposure=1.2),
    )

    result = engine.execute(price_data=prices, target_weights=weights)

    history = result["portfolio_history"]
    positions = result["positions"]

    assert positions.loc[prices.index[0], "BBB"] < 0
    assert history["gross_exposure"].iloc[0] > 0
    assert history["net_exposure"].iloc[0] != 0
