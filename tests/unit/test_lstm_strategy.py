"""Out-of-sample correctness tests for the LSTM strategy.

Same defect class as the ML strategies: ``LSTMStrategy`` used to train on the
full series then predict the same series. ``generate_signals`` must instead
walk forward — fitting on history strictly before each predicted segment — so
a backtest driven by these signals is genuinely out-of-sample.

In environments without TensorFlow the strategy falls back to a sklearn MLP;
the walk-forward contract must hold on either backend.
"""

import numpy as np
import pandas as pd

from src.strategy.lstm_strategy import LSTMStrategy


def _ohlcv(n=400, seed=1):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2021-01-01", periods=n, freq="D")
    returns = rng.normal(0.0004, 0.018, n)
    close = 100 * np.cumprod(1 + returns)
    close = pd.Series(close, index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * (1 + np.abs(rng.normal(0, 0.004, n))),
            "low": close * (1 - np.abs(rng.normal(0, 0.004, n))),
            "close": close,
            "volume": pd.Series(rng.integers(1_000_000, 5_000_000, n), index=index),
        }
    )


class TestLSTMWalkForward:
    def test_generate_signals_runs_without_external_train(self):
        """generate_signals must self-train walk-forward and emit signals
        without the caller pre-fitting the model."""
        data = _ohlcv()
        strategy = LSTMStrategy(sequence_length=20, retrain_interval=40)

        signals = strategy.generate_signals(data)

        assert len(signals) == len(data)
        assert set(signals.dropna().unique()).issubset({-1, 0, 1})
        assert (signals != 0).any(), "walk-forward produced no signals at all"

    def test_warmup_bars_have_no_signal(self):
        """Before the first trained model exists, bars stay flat (0)."""
        data = _ohlcv()
        strategy = LSTMStrategy(sequence_length=20, retrain_interval=40)

        signals = strategy.generate_signals(data)

        # The first segment cannot be predicted before a model is fit; the
        # opening sequence_length bars in particular can never be predicted.
        assert (signals.iloc[:20] == 0).all()

    def test_model_never_trains_on_a_bar_it_later_predicts(self):
        """Spy on each walk-forward fold fit: every fold must train on a
        sequence count strictly below the maximum achievable from the full
        series — the in-sample 'fit-on-everything' path is the defect being
        removed."""
        data = _ohlcv()
        strategy = LSTMStrategy(sequence_length=20, retrain_interval=40)

        fit_sizes = []
        real_fit_segment = strategy._fit_segment

        def spy_fit_segment(train_x, train_y):
            fit_sizes.append(len(train_x))
            return real_fit_segment(train_x, train_y)

        strategy._fit_segment = spy_fit_segment
        signals = strategy.generate_signals(data)

        assert (signals != 0).any()
        assert fit_sizes, "walk-forward never fit a model"
        # Every fold trains on a sequence count strictly below the maximum
        # achievable from the full series.
        max_possible_sequences = len(data) - strategy.sequence_length
        assert max(fit_sizes) < max_possible_sequences, (
            "a fold trained on the whole series — the in-sample defect"
        )

    def test_retrains_proportionately_not_every_bar(self):
        """The walk-forward must retrain a bounded number of times, far fewer
        than once per predicted bar."""
        data = _ohlcv(n=400)
        retrain_interval = 60
        strategy = LSTMStrategy(sequence_length=20, retrain_interval=retrain_interval)

        fit_count = []
        real_fit_segment = strategy._fit_segment

        def spy_fit_segment(train_x, train_y):
            fit_count.append(1)
            return real_fit_segment(train_x, train_y)

        strategy._fit_segment = spy_fit_segment
        strategy.generate_signals(data)

        assert 1 <= len(fit_count) <= (len(data) / retrain_interval) + 2

    def test_short_series_returns_flat_signal(self):
        """Below the minimum training size the strategy returns an all-flat
        series rather than raising."""
        data = _ohlcv(n=40)
        strategy = LSTMStrategy(sequence_length=20, retrain_interval=40)

        signals = strategy.generate_signals(data)

        assert len(signals) == len(data)
        assert (signals == 0).all()
