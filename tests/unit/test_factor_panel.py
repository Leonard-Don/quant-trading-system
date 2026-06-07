import pandas as pd

from src.data.factor_panel import FactorPanel


def _ohlcv(dates, start=10.0):
    n = len(dates)
    return pd.DataFrame(
        {
            "open": [start + i * 0.1 for i in range(n)],
            "high": [start + i * 0.1 + 0.5 for i in range(n)],
            "low": [start + i * 0.1 - 0.5 for i in range(n)],
            "close": [start + i * 0.1 for i in range(n)],
            "volume": [1_000_000 + i for i in range(n)],
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )


def test_history_is_point_in_time():
    dates = pd.bdate_range("2024-01-01", periods=10)
    panel = FactorPanel(prices={"AAA": _ohlcv(dates)})
    h = panel.history("AAA", as_of=dates[4])
    assert h.index.max() == dates[4]  # nothing after as_of
    assert len(h) == 5


def test_symbols_and_trading_dates():
    dates = pd.bdate_range("2024-01-01", periods=6)
    panel = FactorPanel(prices={"AAA": _ohlcv(dates), "BBB": _ohlcv(dates, 20.0)})
    assert set(panel.symbols) == {"AAA", "BBB"}
    assert list(panel.trading_dates) == list(dates)


def test_fundamentals_gated_by_ann_date():
    dates = pd.bdate_range("2024-01-01", periods=10)
    funda = pd.DataFrame(
        {
            "ann_date": pd.to_datetime(["2024-01-03", "2024-01-08"]),
            "end_date": pd.to_datetime(["2023-09-30", "2023-12-31"]),
            "roe": [10.0, 12.0],
        }
    )
    panel = FactorPanel(prices={"AAA": _ohlcv(dates)}, fundamentals={"AAA": funda})
    # as_of before 2nd announcement -> only first report visible
    row = panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-05"))
    assert row["roe"] == 10.0
    # as_of after 2nd announcement -> newer report visible
    row2 = panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-09"))
    assert row2["roe"] == 12.0
    # as_of before any announcement -> None
    assert panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-02")) is None
