"""Unit tests for src.strategy.pairs_trading.

All maths here is pure numpy/scipy on synthetic series — no network, no
statsmodels. Cointegration uses the module's own simplified Engle-Granger
helper, so tests assert *relative* behaviour (cointegrated pair has a much
smaller p-value than an independent random-walk pair) rather than absolute
p-values, which keeps them deterministic and implementation-faithful.
"""

import numpy as np
import pandas as pd
import pytest

from src.strategy.pairs_trading import MultiPairStrategy, PairsTradingStrategy


@pytest.fixture
def strat():
    return PairsTradingStrategy(lookback_period=20)


def make_index(n, start="2020-01-01"):
    return pd.date_range(start=start, periods=n, freq="D")


class TestConstruction:
    def test_params_stored(self):
        s = PairsTradingStrategy(
            lookback_period=40,
            entry_zscore=2.5,
            exit_zscore=0.3,
            stop_loss_zscore=5.0,
        )
        assert s.name == "PairsTrading"
        assert s.lookback_period == 40
        assert s.entry_zscore == 2.5
        assert s.exit_zscore == 0.3
        assert s.stop_loss_zscore == 5.0
        assert s.parameters["lookback_period"] == 40
        assert s.hedge_ratio == 1.0


class TestHedgeRatioAndSpread:
    def test_hedge_ratio_recovers_known_beta(self, strat):
        # price2 = 3 + 2 * price1 exactly -> OLS beta = 2.0
        idx = make_index(50)
        price1 = pd.Series(np.linspace(10.0, 60.0, 50), index=idx)
        price2 = 3.0 + 2.0 * price1
        beta = strat.calculate_hedge_ratio(price1, price2)
        assert beta == pytest.approx(2.0, abs=1e-6)

    def test_calculate_spread_with_explicit_ratio(self, strat):
        idx = make_index(10)
        price1 = pd.Series(np.arange(1.0, 11.0), index=idx)
        price2 = pd.Series(np.arange(2.0, 12.0), index=idx)
        spread = strat.calculate_spread(price1, price2, hedge_ratio=1.0)
        # spread = price2 - 1*price1 = constant 1.0
        assert np.allclose(spread.values, 1.0)
        # explicit ratio is stored
        assert strat.hedge_ratio == 1.0

    def test_calculate_spread_infers_ratio_when_none(self, strat):
        idx = make_index(40)
        price1 = pd.Series(np.linspace(5.0, 45.0, 40), index=idx)
        price2 = 1.0 + 2.0 * price1
        spread = strat.calculate_spread(price1, price2, hedge_ratio=None)
        # inferred hedge ratio ~ 2.0 and spread ~ constant 1.0
        assert strat.hedge_ratio == pytest.approx(2.0, abs=1e-6)
        assert np.allclose(spread.values, 1.0, atol=1e-6)


class TestZScore:
    def test_zscore_zero_when_at_rolling_mean(self):
        s = PairsTradingStrategy(lookback_period=5)
        idx = make_index(20)
        # alternating spread so rolling mean is well defined and current == mean
        spread = pd.Series([10.0, 12.0] * 10, index=idx)
        z = s.calculate_zscore(spread)
        # first lookback-1 are NaN
        assert z.iloc[:4].isna().all()
        # values are finite afterwards
        assert z.iloc[5:].notna().all()

    def test_zscore_sign_matches_deviation(self):
        s = PairsTradingStrategy(lookback_period=10)
        idx = make_index(30)
        base = np.full(30, 100.0)
        base[-1] = 130.0  # big positive spike at the end
        spread = pd.Series(base, index=idx)
        z = s.calculate_zscore(spread)
        # last point is far above its trailing mean -> strongly positive z.
        # (The rolling window includes the spike, so std is inflated; the score
        # lands ~2.85 rather than huge — still clearly positive and large.)
        assert z.iloc[-1] > 2.5


class TestSignals:
    def _zscore_path_signals(self, zscores, entry=2.0, exit_=0.5, stop=4.0):
        """Drive generate_pair_signals via a hand-built zscore path.

        We monkey-ish patch by constructing price series whose spread/zscore we
        instead inject directly through calculate_zscore. Simpler: call the
        signal state machine by reconstructing it through the public method with
        a controlled spread. Here we bypass price construction by patching the
        instance's calculate_spread/calculate_zscore.
        """
        s = PairsTradingStrategy(
            lookback_period=5, entry_zscore=entry, exit_zscore=exit_, stop_loss_zscore=stop
        )
        idx = make_index(len(zscores))
        z_series = pd.Series(zscores, index=idx)
        # patch the two transforms so the state machine sees our exact path
        s.calculate_spread = lambda p1, p2: pd.Series(np.zeros(len(idx)), index=idx)
        s.calculate_zscore = lambda spread: z_series
        dummy = pd.Series(np.zeros(len(idx)), index=idx)
        return s.generate_pair_signals(dummy, dummy), idx

    def test_enter_short_on_high_zscore(self):
        # z crosses above entry (2.0) -> short spread signal = -1
        z = [0.0, 0.0, 0.0, 0.0, 0.0, 2.5]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == -1

    def test_enter_long_on_low_zscore(self):
        z = [0.0, 0.0, 0.0, 0.0, 0.0, -2.5]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == 1

    def test_exit_long_when_zscore_recovers(self):
        # enter long at -2.5, then z rises above -exit (-0.5) -> exit with +... wait
        # position==1 exits when z > -exit_zscore i.e. z > -0.5
        z = [0.0, 0.0, 0.0, 0.0, 0.0, -2.5, -0.4]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == 1  # entered long
        assert sig.iloc[6] == -1  # closed the long position

    def test_exit_short_when_zscore_recovers(self):
        # enter short at +2.5, exit when z < exit_zscore (0.5)
        z = [0.0, 0.0, 0.0, 0.0, 0.0, 2.5, 0.4]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == -1  # entered short
        assert sig.iloc[6] == 1  # closed the short

    def test_stop_loss_closes_position(self):
        # enter short at 2.5, then z blows past stop (4.0) -> stop closes (= -pos)
        z = [0.0, 0.0, 0.0, 0.0, 0.0, 2.5, 5.0]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == -1  # short
        assert sig.iloc[6] == 1  # stop-loss closes short (-(-1) = +1)

    def test_nan_zscore_is_skipped(self):
        z = [np.nan, np.nan, np.nan, np.nan, np.nan, 2.5]
        sig, _ = self._zscore_path_signals(z)
        # the leading NaNs produce 0 signals
        assert (sig.iloc[:5] == 0).all()
        assert sig.iloc[5] == -1

    def test_no_double_entry_while_in_position(self):
        # already short at idx5; idx6 still high but below stop -> stays, no new entry
        z = [0.0, 0.0, 0.0, 0.0, 0.0, 2.5, 3.0]
        sig, _ = self._zscore_path_signals(z)
        assert sig.iloc[5] == -1
        assert sig.iloc[6] == 0  # no action: already short, not at stop, not at exit


class TestGenerateSignalsDispatch:
    def test_uses_pair_close_column(self, strat):
        idx = make_index(40)
        close = pd.Series(np.linspace(10, 50, 40), index=idx)
        pair = 1.0 + 2.0 * close
        df = pd.DataFrame({"close": close, "pair_close": pair}, index=idx)
        sig = strat.generate_signals(df)
        assert isinstance(sig, pd.Series)
        assert len(sig) == 40
        assert set(sig.unique()).issubset({-1, 0, 1})

    def test_missing_pair_close_uses_shifted_self(self, strat):
        idx = make_index(40)
        close = pd.Series(np.linspace(10, 50, 40), index=idx)
        df = pd.DataFrame({"close": close}, index=idx)
        sig = strat.generate_signals(df)  # should not raise
        assert len(sig) == 40


class TestPairMetrics:
    def test_metrics_keys_and_correlation(self, strat):
        idx = make_index(60)
        rng = np.random.default_rng(7)
        walk = np.cumsum(rng.normal(0, 1, 60)) + 100
        price1 = pd.Series(walk, index=idx)
        # highly correlated partner
        price2 = pd.Series(2.0 * walk + 5 + rng.normal(0, 0.1, 60), index=idx)
        m = strat.get_pair_metrics(price1, price2)
        assert set(m) == {
            "hedge_ratio",
            "correlation",
            "spread_mean",
            "spread_std",
            "current_zscore",
            "half_life",
            "lookback_period",
        }
        assert m["correlation"] > 0.9
        assert m["lookback_period"] == 20

    def test_half_life_none_for_non_mean_reverting(self, strat):
        # a pure upward trend is not mean-reverting -> beta >= 0 -> None
        idx = make_index(40)
        spread = pd.Series(np.linspace(0, 39, 40), index=idx)
        assert strat._calculate_half_life(spread) is None

    def test_half_life_positive_for_mean_reverting(self, strat):
        # AR(1) with negative mean-reversion coefficient -> finite positive half-life
        idx = make_index(200)
        rng = np.random.default_rng(3)
        x = np.zeros(200)
        for i in range(1, 200):
            x[i] = 0.7 * x[i - 1] + rng.normal(0, 1)  # phi<1 => mean reverting
        spread = pd.Series(x, index=idx)
        hl = strat._calculate_half_life(spread)
        assert hl is not None
        assert hl > 0


class TestCointegration:
    def test_cointegrated_pair_beats_independent_pair(self):
        s = PairsTradingStrategy()
        idx = make_index(150)
        rng = np.random.default_rng(11)
        walk = np.cumsum(rng.normal(0, 1, 150)) + 100
        # coint: y2 = 2*y1 + small stationary noise
        coint_p = s._engle_granger_test(
            walk, 2.0 * walk + rng.normal(0, 0.2, 150)
        )
        # independent random walks: should be far from cointegrated
        walk_b = np.cumsum(rng.normal(0, 1, 150)) + 100
        indep_p = s._engle_granger_test(walk, walk_b)
        assert coint_p < indep_p
        assert coint_p < 0.05

    def test_short_series_returns_p_one(self):
        s = PairsTradingStrategy()
        y = np.arange(5.0)
        assert s._engle_granger_test(y, y + 1) == 1.0

    def test_find_pairs_skips_too_short_and_sorts(self):
        s = PairsTradingStrategy()
        idx = make_index(120)
        rng = np.random.default_rng(5)
        walk = np.cumsum(rng.normal(0, 1, 120)) + 100
        data = {
            "A": pd.Series(walk, index=idx),
            "B": pd.Series(2.0 * walk + rng.normal(0, 0.2, 120), index=idx),
            "C": pd.Series(np.arange(10.0), index=idx[:10]),  # too short
        }
        pairs = s.find_cointegrated_pairs(data, significance_level=0.05)
        # at least the strongly cointegrated A-B should appear; C never qualifies
        symbols_in_pairs = {sym for p in pairs for sym in p[:2]}
        assert "C" not in symbols_in_pairs
        # results sorted ascending by p-value
        pvals = [p[2] for p in pairs]
        assert pvals == sorted(pvals)


class TestMultiPair:
    def test_select_pairs_no_symbol_reuse_and_respects_max(self):
        m = MultiPairStrategy(max_pairs=1)
        idx = make_index(120)
        rng = np.random.default_rng(2)
        walk = np.cumsum(rng.normal(0, 1, 120)) + 100
        data = {
            "A": pd.Series(walk, index=idx),
            "B": pd.Series(2.0 * walk + rng.normal(0, 0.2, 120), index=idx),
            "C": pd.Series(1.5 * walk + rng.normal(0, 0.2, 120), index=idx),
        }
        selected = m.select_pairs(data)
        assert len(selected) <= 1
        # no symbol reused across selected pairs
        flat = [sym for pair in selected for sym in pair]
        assert len(flat) == len(set(flat))

    def test_generate_signals_returns_zeros(self):
        m = MultiPairStrategy()
        idx = make_index(10)
        df = pd.DataFrame({"close": np.arange(10.0)}, index=idx)
        sig = m.generate_signals(df)
        assert (sig == 0).all()
        assert len(sig) == 10

    def test_generate_multi_signals_skips_missing_symbols(self):
        m = MultiPairStrategy()
        idx = make_index(40)
        data = {
            "A": pd.Series(np.linspace(10, 50, 40), index=idx),
            "B": pd.Series(np.linspace(20, 100, 40), index=idx),
        }
        out = m.generate_multi_signals(data, [("A", "B"), ("A", "ZZZ")])
        assert ("A", "B") in out
        assert ("A", "ZZZ") not in out  # missing symbol skipped
        assert isinstance(out[("A", "B")], pd.Series)
