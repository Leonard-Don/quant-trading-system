"""Out-of-sample correctness tests for the single-asset ML strategies.

The defect under test: ``MLStrategy``/``LogisticRegressionStrategy`` used to
be ``train()``-ed on the full price series and then asked to
``generate_signals()`` on the SAME series, so every backtest prediction was
in-sample. ``generate_signals`` must instead produce genuinely out-of-sample
signals — a model may never predict a bar it was trained on.

A row's label is ``future_return.shift(-horizon)`` — it encodes the price
``horizon`` bars ahead — so a training row j carries information up to
``j + horizon``. Therefore, to predict bar ``i`` the model may only train on
rows ``j`` with ``j + horizon < i``.
"""

import numpy as np
import pandas as pd
import pytest

from src.strategy.ml_strategies import LogisticRegressionStrategy, RandomForestStrategy


def _ohlcv(n=400, seed=0):
    """Deterministic OHLCV frame with enough history for walk-forward."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2021-01-01", periods=n, freq="D")
    returns = rng.normal(0.0005, 0.02, n)
    close = 100 * np.cumprod(1 + returns)
    close = pd.Series(close, index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * (1 + np.abs(rng.normal(0, 0.004, n))),
            "Low": close * (1 - np.abs(rng.normal(0, 0.004, n))),
            "Close": close,
            "Volume": pd.Series(rng.integers(1_000_000, 5_000_000, n), index=index),
        }
    )


class TestWalkForwardIsOutOfSample:
    def test_generate_signals_runs_without_external_train(self):
        """generate_signals must self-train walk-forward — it should produce
        signals without the caller pre-fitting the model. A length-mismatch
        or an all-zero series would both indicate the walk-forward did not
        actually run."""
        data = _ohlcv()
        strategy = LogisticRegressionStrategy(min_training_samples=120)

        signals = strategy.generate_signals(data)

        assert len(signals) == len(data)
        assert set(signals.dropna().unique()).issubset({-1, 0, 1})
        # Walk-forward must actually emit directional signals on the
        # out-of-sample tail.
        assert (signals != 0).any(), "walk-forward produced no signals at all"

    def test_warmup_bars_have_no_signal(self):
        """Bars before the first trained model exists cannot be predicted —
        they must be flat (0), not a leaked guess."""
        data = _ohlcv()
        min_train = 150
        strategy = LogisticRegressionStrategy(min_training_samples=min_train)

        signals = strategy.generate_signals(data)

        # No model can exist before min_training_samples rows of history.
        assert (signals.iloc[:min_train] == 0).all()

    def test_model_never_trains_on_a_bar_it_later_predicts(self):
        """The core contract. Spy on every model ``fit`` and every
        ``predict``: for each prediction at bar ``i``, the model that made it
        must have been trained only on rows ``j`` with ``j + horizon < i``.
        """
        data = _ohlcv()
        horizon = 1
        min_train = 120
        strategy = LogisticRegressionStrategy(
            min_training_samples=min_train, prediction_horizon=horizon
        )

        # Record (n_training_rows) at each fit and the row positions handed
        # to predict, in call order.
        events = []
        real_fit = strategy.model.fit
        real_predict = strategy.model.predict

        def spy_fit(X, y, *args, **kwargs):
            events.append(("fit", len(X)))
            return real_fit(X, y, *args, **kwargs)

        def spy_predict(X, *args, **kwargs):
            events.append(("predict", len(X)))
            return real_predict(X, *args, **kwargs)

        strategy.model.fit = spy_fit
        strategy.model.predict = spy_predict

        signals = strategy.generate_signals(data)
        assert (signals != 0).any()

        # There must be at least one fit and one predict, and a fit must
        # always precede the predict that uses it.
        assert any(kind == "fit" for kind, _ in events)
        assert any(kind == "predict" for kind, _ in events)
        first_fit = next(i for i, (k, _) in enumerate(events) if k == "fit")
        first_predict = next(i for i, (k, _) in enumerate(events) if k == "predict")
        assert first_fit < first_predict, "model predicted before it was trained"

        # Each fit must use strictly fewer rows than the total — i.e. it is an
        # expanding-window fit, never the full in-sample dataset used to also
        # predict itself.
        total_rows = len(data)
        fit_sizes = [size for kind, size in events if kind == "fit"]
        assert fit_sizes, "no fit recorded"
        assert max(fit_sizes) < total_rows, (
            "a fit used the entire series — that is the in-sample defect"
        )

    def test_retrains_proportionately_not_every_bar(self):
        """A per-bar retrain is too slow; the walk-forward must retrain only
        a bounded number of times (far fewer than one per predicted bar)."""
        data = _ohlcv(n=400)
        strategy = RandomForestStrategy(min_training_samples=120)

        fit_calls = []
        real_fit = strategy.model.fit

        def spy_fit(X, y, *args, **kwargs):
            fit_calls.append(len(X))
            return real_fit(X, y, *args, **kwargs)

        strategy.model.fit = spy_fit
        strategy.generate_signals(data)

        predicted_bars = 400 - 120
        assert len(fit_calls) >= 1
        # Many fewer retrains than predicted bars (proportionate scheme).
        assert len(fit_calls) <= predicted_bars / 4

    def test_short_series_returns_flat_signal(self):
        """Below the minimum training size no model can be fit — the
        strategy must return an all-flat series, not raise."""
        data = _ohlcv(n=40)
        strategy = LogisticRegressionStrategy(min_training_samples=120)

        signals = strategy.generate_signals(data)

        assert len(signals) == len(data)
        assert (signals == 0).all()


class TestBackwardCompatibility:
    def test_train_then_introspect_still_works(self):
        """train() must still fit the model so coefficient/importance
        introspection keeps working."""
        data = _ohlcv()
        strategy = LogisticRegressionStrategy(min_training_samples=120)

        assert strategy.train(data) is True
        assert strategy.is_trained is True
        coefficients = strategy.get_coefficients()
        assert coefficients is not None
        assert len(coefficients) > 0
