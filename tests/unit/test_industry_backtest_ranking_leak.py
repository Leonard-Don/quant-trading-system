"""Regression test for the look-ahead (future-data) leak in the proxy-ranking
path of the industry-rotation backtest.

``_load_symbol_frame`` fetches history with a ``+5 calendar-day`` buffer past
the rebalance ``anchor_date`` (so the anchor landing on a non-trading day still
resolves). ``_score_proxy_frame`` then scored ``frame.tail(lookback)`` WITHOUT
slicing to ``index <= anchor_date`` — so the few bars AFTER the anchor leaked
into the momentum/vol ranking decision made AT the anchor.

This test pins the contract that the ranking score is identical whether or not
post-anchor bars exist in the fetched frame. Before the fix the scores differ
(future bars move the score); after the fix they are equal.
"""

from datetime import datetime

import pandas as pd

from src.backtest.industry_backtest import IndustryBacktester


def _price_frame(values, start="2024-01-01"):
    dates = pd.date_range(start=start, periods=len(values), freq="B")
    prices = pd.Series(values, index=dates, dtype="float64")
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1_000_000,
        }
    )


class _DummyDataManager:
    def __init__(self, frames):
        self.frames = frames

    def get_historical_data(
        self, symbol, start_date=None, end_date=None, interval="1d", period=None
    ):
        frame = self.frames.get(symbol, pd.DataFrame()).copy()
        if frame.empty:
            return frame
        if start_date is not None:
            frame = frame[frame.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            frame = frame[frame.index <= pd.Timestamp(end_date)]
        return frame


def _make_backtester(frames):
    return IndustryBacktester(
        industry_analyzer=None,
        leader_scorer=None,
        data_manager=_DummyDataManager(frames),
        initial_capital=100_000,
        benchmark_symbol="SPY",
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
        ranking_lookback_days=10,
        min_price_observations=5,
        strict_data_validation=True,
    )


def test_ranking_score_ignores_post_anchor_future_bars():
    """The ranking score computed at ``anchor_date`` must be identical whether
    or not the fetched frame contains an EXTREME spike in the bars AFTER the
    anchor. The +5-day fetch buffer must not leak future data into the score."""
    anchor = datetime(2024, 1, 31)

    # 30 business days of calm, gently rising prices up to and past the anchor.
    base_values = [100.0 + i for i in range(30)]
    calm = _price_frame(base_values)

    # Identical frame, but inject an EXTREME spike into the few bars that fall
    # strictly AFTER the anchor (the +5 calendar-day fetch buffer region).
    spiked = calm.copy()
    post_anchor_mask = spiked.index > pd.Timestamp(anchor)
    assert post_anchor_mask.any(), "test setup must include post-anchor bars"
    for col in ("open", "high", "low", "close"):
        spiked.loc[post_anchor_mask, col] = 10_000.0

    score_calm = _make_backtester({"XLK": calm})._score_proxy_frame(
        _make_backtester({"XLK": calm})._load_symbol_frame("XLK", anchor),
        anchor,
    )
    score_spiked = _make_backtester({"XLK": spiked})._score_proxy_frame(
        _make_backtester({"XLK": spiked})._load_symbol_frame("XLK", anchor),
        anchor,
    )

    assert score_calm is not None
    assert score_spiked is not None
    assert score_calm == score_spiked, (
        "Look-ahead leak: post-anchor (future) bars changed the ranking score. "
        f"calm={score_calm} spiked={score_spiked}"
    )
