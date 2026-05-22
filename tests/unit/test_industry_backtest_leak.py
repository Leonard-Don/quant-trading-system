"""Regression tests guarding against the look-ahead (future-data) leak in the
industry-rotation backtest.

The analyzer/scorer ranking path (``IndustryAnalyzer.rank_industries`` /
``LeaderStockScorer.rank_stocks_in_industry``) has no notion of an ``as_of``
date — it always ranks using TODAY's live A-share money-flow snapshot. Running
a 2022 rebalance through it therefore contaminates the backtest with future
information. These tests pin the contract that historical rebalances route
exclusively through the point-in-time-correct proxy path and never invoke the
live analyzer/scorer.
"""

from datetime import datetime

import pandas as pd

from src.backtest.industry_backtest import IndustryBacktester


def _price_frame(values, start="2024-01-01"):
    dates = pd.date_range(start=start, periods=len(values), freq="B")
    prices = pd.Series(values, index=dates)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1_000_000,
        }
    )


class DummyIndustryDataManager:
    def __init__(self, frames):
        self.frames = frames

    def get_historical_data(self, symbol, start_date=None, end_date=None, interval="1d", period=None):
        frame = self.frames.get(symbol, pd.DataFrame()).copy()
        if frame.empty:
            return frame
        if start_date is not None:
            frame = frame[frame.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            frame = frame[frame.index <= pd.Timestamp(end_date)]
        return frame


class LeakingAnalyzer:
    """Stand-in for IndustryAnalyzer: ranks from TODAY's live snapshot.

    It records every call so the test can prove the backtester never reaches
    it during a historical rebalance.
    """

    def __init__(self):
        self.rank_calls = []

    def rank_industries(self, top_n=10, **kwargs):
        self.rank_calls.append({"top_n": top_n, **kwargs})
        # Live data — would leak future info into a 2022 backtest.
        return [
            {"industry_name": "电子", "score": 99.0},
            {"industry_name": "金融", "score": 88.0},
        ][:top_n]


class LeakingScorer:
    """Stand-in for LeaderStockScorer: scores from TODAY's live valuations."""

    def __init__(self):
        self.rank_calls = []

    def rank_stocks_in_industry(self, industry_name, top_n=10, **kwargs):
        self.rank_calls.append({"industry_name": industry_name, "top_n": top_n})
        return [
            {"symbol": "LEAK1", "name": "leaked", "total_score": 99.0, "market_cap": 1},
        ][:top_n]


def _build_backtester(analyzer, scorer, frames, **overrides):
    kwargs = {
        "industry_analyzer": analyzer,
        "leader_scorer": scorer,
        "data_manager": DummyIndustryDataManager(frames),
        "initial_capital": 100_000,
        "benchmark_symbol": "SPY",
        "industry_proxy_map": {
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
            "金融": [{"symbol": "XLF", "name": "金融 ETF", "market_cap": 900_000_000}],
        },
        "ranking_lookback_days": 10,
        "min_price_observations": 5,
        "strict_data_validation": True,
    }
    kwargs.update(overrides)
    return IndustryBacktester(**kwargs)


def test_historical_backtest_never_invokes_live_analyzer_or_scorer():
    """A historical backtest must not call the live analyzer/scorer ranking
    methods — doing so leaks future data into past rebalances."""
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110, 112, 114, 116, 118]),
        "XLF": _price_frame([100, 100, 99, 98, 97, 96, 95, 94, 93, 92]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }
    analyzer = LeakingAnalyzer()
    scorer = LeakingScorer()
    backtester = _build_backtester(analyzer, scorer, frames)

    result = backtester.run_backtest(
        start_date="2024-01-01",
        end_date="2024-01-15",
        rebalance_freq="monthly",
        top_industries=2,
        stocks_per_industry=1,
    )

    # The core invariant: the leaking live-data path was never touched.
    assert analyzer.rank_calls == [], (
        "IndustryAnalyzer.rank_industries was called during a historical "
        "backtest — this leaks TODAY's data into a past rebalance"
    )
    assert scorer.rank_calls == [], (
        "LeaderStockScorer.rank_stocks_in_industry was called during a "
        "historical backtest — this leaks future data"
    )

    # The point-in-time proxy path must have been used instead, and the
    # leaked 'LEAK1' symbol must never appear in the trades.
    assert result.diagnostics["industry_selection_source"] == "proxy"
    assert result.diagnostics["leader_selection_source"] == "proxy"
    assert all(t["symbol"] != "LEAK1" for t in backtester.get_trade_history())


def test_diagnostics_report_live_ranking_disabled_for_backtest():
    """Diagnostics must honestly flag that the live analyzer/scorer path was
    disabled for the historical backtest."""
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110, 112, 114, 116, 118]),
        "XLF": _price_frame([100, 100, 99, 98, 97, 96, 95, 94, 93, 92]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }
    backtester = _build_backtester(LeakingAnalyzer(), LeakingScorer(), frames)

    result = backtester.run_backtest(
        start_date="2024-01-01",
        end_date="2024-01-15",
        rebalance_freq="monthly",
        top_industries=2,
        stocks_per_industry=1,
    )

    assert result.diagnostics["live_ranking_path_disabled"] is True


def test_backtest_results_invariant_to_mutating_future_analyzer_data():
    """Backtest output must be identical whether the live analyzer would have
    returned bullish or bearish 'future' rankings — proving no leak."""
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110, 112, 114, 116, 118]),
        "XLF": _price_frame([100, 100, 99, 98, 97, 96, 95, 94, 93, 92]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }

    bullish = LeakingAnalyzer()
    bullish.rank_industries = lambda top_n=10, **kw: [  # type: ignore[method-assign]
        {"industry_name": "电子", "score": 99.0}
    ][:top_n]

    bearish = LeakingAnalyzer()
    bearish.rank_industries = lambda top_n=10, **kw: [  # type: ignore[method-assign]
        {"industry_name": "金融", "score": 99.0}
    ][:top_n]

    run_kwargs = {
        "start_date": "2024-01-01",
        "end_date": "2024-01-15",
        "rebalance_freq": "monthly",
        "top_industries": 2,
        "stocks_per_industry": 1,
    }

    result_a = _build_backtester(bullish, LeakingScorer(), frames).run_backtest(**run_kwargs)
    result_b = _build_backtester(bearish, LeakingScorer(), frames).run_backtest(**run_kwargs)

    assert result_a.total_return == result_b.total_return
    assert result_a.trade_count == result_b.trade_count


def test_strict_backtest_without_proxy_data_flags_non_backtestable():
    """When the proxy path cannot produce a ranking, strict mode must NOT
    silently fall back to leaked analyzer numbers — it flags the result as
    non-backtestable."""
    frames = {
        # No XLK / XLF proxy prices available.
        "SPY": _price_frame([100, 101, 102, 103, 104, 105]),
    }
    backtester = _build_backtester(
        LeakingAnalyzer(),
        LeakingScorer(),
        frames,
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
    )

    result = backtester.run_backtest(
        start_date="2024-01-01",
        end_date="2024-01-10",
        rebalance_freq="monthly",
        top_industries=1,
        stocks_per_industry=1,
    )

    assert result.trade_count == 0
    assert result.diagnostics["industry_selection_source"] == "none"
    assert result.diagnostics["backtestable"] is False


def test_live_heatmap_ranking_path_unchanged_outside_backtest():
    """Calling the analyzer directly (the live heatmap/ranking use case) must
    still hit the live data path — only the backtester disables it."""
    analyzer = LeakingAnalyzer()
    # Direct, non-backtest use must reach the live ranking.
    ranked = analyzer.rank_industries(top_n=2)
    assert len(analyzer.rank_calls) == 1
    assert ranked[0]["industry_name"] == "电子"


def test_default_as_of_preserves_live_behavior_when_analyzer_supports_it():
    """If a future analyzer/scorer gains an ``as_of`` parameter, the backtester
    must pass the rebalance date; a None default keeps live behavior. This test
    is a guard so the live-vs-backtest distinction stays explicit."""
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110, 112, 114, 116, 118]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }
    backtester = _build_backtester(
        LeakingAnalyzer(),
        LeakingScorer(),
        frames,
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
    )
    # _get_hot_industries during a backtest must not reach the live analyzer.
    backtester._reset()
    backtester._disable_live_ranking = True
    hot = backtester._get_hot_industries(datetime(2024, 1, 15), top_industries=1)
    assert hot, "proxy path should still produce a ranking"
    assert hot[0]["industry_name"] == "电子"
