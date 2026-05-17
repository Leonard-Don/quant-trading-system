"""Historical replay harness for the ETF rotation strategy.

This module closes the research loop for the ETF rotation strategy: rather
than analysing whatever audit log happens to be on disk, it walks an
arbitrary historical window of close-price data, asks the production
``EtfRotationStrategy`` for its planned weights at each rebalance, and
measures the realised P&L of holding those weights into the next
rebalance bar.

Look-ahead semantics
--------------------
The strategy itself already lags signals by ``lag_days=1`` (see
``EtfRotationStrategy.generate_signals`` docstring), so the weight applied
on bar ``t`` was computed from the close on bar ``t - 1``. The harness
honours that contract: at each rebalance, we look up the **next-day**
weight from the lagged matrix and hold it until the next rebalance bar.
No same-bar close-to-close fills sneak in.

v0.1 caveats
------------
* **No transaction costs.** The harness does NOT model commission or any
  per-trade fee. Live trading costs (CN ETF brokerage typically 0.012%–
  0.03% one-way) will degrade the realised returns.
* **No bid-ask spread / slippage.** All fills happen at the next bar's
  close. In practice ETF spreads in CN are 1–3 bps for the popular tickers
  and meaningfully wider for low-volume QDII; expect 2–10 bps drag.
* **No market impact.** Position sizes here are notional. A real desk
  trading >5% of an ETF's ADV would push prices around.
* **Strict next-bar fills.** No partial fills, no execution delay beyond
  the one-bar lag the strategy enforces. Real fills can take minutes to
  hours on illiquid CN ETFs.
* **No survivorship handling.** The price matrix is whatever the caller
  supplies; if an ETF de-listed mid-period the harness would just drop
  the column from the universe.

Use the harness to answer "does the scoring layer have any edge at all
over the period?". Use the live audit log + attribution module to measure
realised production results with execution costs baked in.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from src.strategy.etf_rotation_strategy import (
    TRADING_DAYS_PER_YEAR,
    EtfRotationConfig,
    EtfRotationStrategy,
)

logger = logging.getLogger(__name__)


# Defaults intentionally mild — backtests should explore the strategy's
# raw behaviour, leaving execution friction to the live attribution path.
DEFAULT_REBALANCE_FREQ_DAYS = 5  # weekly cadence in business days
DEFAULT_INITIAL_CAPITAL = 100_000.0


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestReport:
    """Structured performance summary returned by :class:`EtfRotationBacktester`.

    Field semantics
    ---------------
    * ``total_return_pct`` — geometric total return over the window
      (``final_equity / initial_capital - 1``), expressed in percent.
    * ``sharpe_ratio`` — annualised mean(daily return) / std(daily return)
      using sample std (ddof=1). Zero when fewer than 2 daily returns or
      when std is zero.
    * ``max_drawdown_pct`` — deepest peak-to-trough drop on the equity
      curve, as a positive percent (e.g. ``8.5`` means 8.5% drawdown).
    * ``calmar_ratio`` — annualised return / max_drawdown_pct/100. ``None``
      when max_drawdown_pct is zero (monotonic up — Calmar undefined).
    * ``avg_turnover_pct`` — mean per-rebalance turnover, where turnover is
      ``sum(|w_new - w_old|) / 2`` (a fully-rotated portfolio = 1.0 = 100%).
    * ``n_rebalances`` — count of rebalance events fired (excludes the
      initial entry day so a 1-rebalance backtest still gets credit for
      ``n_rebalances=1``).
    * ``win_rate`` — fraction of rebalance holding-periods that produced a
      positive period return (excludes the trailing partial period).
    * ``comparable_buy_hold_return_pct`` — equal-weight buy-and-hold return
      over the same window using the same universe. The "comparable" qualifier
      flags this is a simple benchmark, not the index the strategy claims to
      beat.

    Everything is JSON-serialisable via :meth:`to_dict` so the backend
    endpoint can hand it back to the frontend unchanged.
    """

    period_start: Optional[str]
    period_end: Optional[str]
    n_bars: int
    n_assets: int
    n_rebalances: int
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    calmar_ratio: Optional[float]
    avg_turnover_pct: float
    win_rate: float
    comparable_buy_hold_return_pct: float
    policy_signal_factor_enabled: bool
    rebalance_freq_days: int
    # Per-rebalance breakdown for downstream consumers (UI, audits).
    rebalance_log: list[dict[str, Any]] = field(default_factory=list)
    # Free-form caveats so consumers know what hasn't been modeled.
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serialisable dict mirroring the dataclass."""

        payload = asdict(self)
        # asdict() handles nested dicts/lists; just guarantee no NaN/inf
        # sneaks into the JSON payload because the FastAPI default JSON
        # encoder will reject them.
        return _sanitize_for_json(payload)


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------


class EtfRotationBacktester:
    """Walk-forward replay of ``EtfRotationStrategy`` against historical prices.

    Usage::

        report = EtfRotationBacktester(
            config=build_strategy_config(...),
            price_history=price_matrix,
            period_start="2024-06-01",
            period_end="2024-09-01",
            policy_signal_factor_enabled=False,
        ).run()

    The harness is deterministic: given identical inputs (config + price
    matrix + period bounds + rebalance cadence) it will always produce the
    same report. No environment knobs, no live data fetching.

    The strategy's ``generate_signals`` always lags weights by one bar, so
    we apply the weight series to the **next** bar's returns. That keeps
    the backtest causal — bar ``t``'s signal cannot use bar ``t``'s
    close.
    """

    def __init__(
        self,
        config: EtfRotationConfig,
        price_history: pd.DataFrame,
        *,
        period_start: Optional[Union[str, datetime, pd.Timestamp]] = None,
        period_end: Optional[Union[str, datetime, pd.Timestamp]] = None,
        audit_history: Optional[Sequence[Mapping[str, Any]]] = None,
        policy_signal_factor_enabled: bool = False,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
        rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    ) -> None:
        if rebalance_freq_days < 1:
            raise ValueError("rebalance_freq_days must be >= 1")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")

        self._period_start = _to_timestamp(period_start)
        self._period_end = _to_timestamp(period_end)
        self._rebalance_freq_days = int(rebalance_freq_days)
        self._initial_capital = float(initial_capital)
        self._policy_factor_enabled = bool(policy_signal_factor_enabled)
        self._industry_signals = dict(industry_signals) if industry_signals else None
        self._etf_industry_map = dict(etf_industry_map) if etf_industry_map else None
        # Audit history is currently passed through unchanged — the harness
        # does NOT use it for anything in v0.1, but storing it lets the
        # report carry a "n_audit_entries" hint and lets future revisions
        # cross-check live vs replayed signals on overlapping windows.
        self._audit_history = list(audit_history) if audit_history is not None else []
        # Override the policy-factor toggle on the config so the strategy
        # constructor sees the effective setting regardless of what the
        # caller passed. Same trick used by ``daily_etf_signal.generate_plan``.
        effective_config = config
        if config.policy_signal_factor_enabled != self._policy_factor_enabled:
            effective_config = replace(
                config,
                policy_signal_factor_enabled=self._policy_factor_enabled,
            )
        self._config = effective_config
        self._prices = self._prepare_prices(price_history)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> BacktestReport:
        """Replay the strategy and return performance metrics.

        Returns a :class:`BacktestReport` even for empty windows — the
        caller is expected to inspect ``n_bars`` / ``n_rebalances`` rather
        than rely on the function raising.
        """

        prices = self._prices
        if prices.empty:
            return self._empty_report("no_price_data")

        # The strategy needs warmup_days of history BEFORE we can read any
        # signal. We surface that to the caller via a 'warmup_skipped'
        # caveat if the supplied window doesn't have it, so they don't
        # silently get a flat report.
        warmup = self._config.warmup_days
        if len(prices) <= warmup:
            return self._empty_report(
                f"insufficient_history(have={len(prices)}, need>{warmup})"
            )

        strategy = EtfRotationStrategy(self._config)
        target_weights = strategy.generate_signals(
            prices,
            lag_days=1,
            industry_signals=self._industry_signals if self._policy_factor_enabled else None,
            etf_industry_map=self._etf_industry_map if self._policy_factor_enabled else None,
        )

        # Slice both prices and target weights to the requested window. We
        # do this AFTER generate_signals so the strategy still sees the
        # full warmup history — slicing first would either lose the warmup
        # or force the caller to pre-pad. Honour inclusive bounds: a
        # ``period_start = '2024-06-01'`` includes 2024-06-01 itself, and a
        # ``period_end = '2024-09-01'`` includes 2024-09-01 (close-to-close
        # convention).
        window_mask = pd.Series(True, index=prices.index)
        if self._period_start is not None:
            window_mask &= prices.index >= self._period_start
        if self._period_end is not None:
            window_mask &= prices.index <= self._period_end
        window_prices = prices.loc[window_mask]
        window_weights = target_weights.loc[window_mask]

        if window_prices.empty or len(window_prices) < 2:
            return self._empty_report("window_too_small_after_filtering")

        # The first window bar is reserved for "set initial weights and
        # mark equity". Returns start accruing from the *next* bar.
        equity, rebalance_log, win_rate, avg_turnover = self._simulate(
            window_prices, window_weights,
        )

        # If only one bar made it in, simulate() returns a trivial equity
        # of length 1 — bail out with a metrics-empty report.
        if len(equity) < 2:
            return self._empty_report("not_enough_bars_for_returns")

        metrics = self._compute_metrics(equity, win_rate, avg_turnover)
        bh_return = self._comparable_buy_hold_return(window_prices)

        return BacktestReport(
            period_start=str(window_prices.index[0].date()),
            period_end=str(window_prices.index[-1].date()),
            n_bars=len(window_prices),
            n_assets=window_prices.shape[1],
            n_rebalances=len(rebalance_log),
            initial_capital=self._initial_capital,
            final_equity=float(equity.iloc[-1]),
            total_return_pct=metrics["total_return_pct"],
            annualized_return_pct=metrics["annualized_return_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            calmar_ratio=metrics["calmar_ratio"],
            avg_turnover_pct=metrics["avg_turnover_pct"],
            win_rate=metrics["win_rate"],
            comparable_buy_hold_return_pct=bh_return,
            policy_signal_factor_enabled=self._policy_factor_enabled,
            rebalance_freq_days=self._rebalance_freq_days,
            rebalance_log=rebalance_log,
            caveats=self._build_caveats(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_prices(self, price_history: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(price_history, pd.DataFrame):
            raise ValueError("price_history must be a pandas DataFrame")
        if price_history.empty:
            return price_history.copy()
        prices = price_history.apply(pd.to_numeric, errors="coerce").sort_index()
        prices = prices.ffill().dropna(how="all")
        # Trim columns that aren't in the configured universe so the
        # strategy doesn't choke on unrelated tickers if a user hands us a
        # broader matrix.
        configured = self._config.asset_map().keys()
        keep = [c for c in prices.columns if c in configured]
        if not keep:
            logger.warning(
                "etf_rotation_backtest: none of the price_history columns "
                "(%s) match the configured universe (%s); returning empty.",
                list(prices.columns), list(configured),
            )
            return pd.DataFrame(index=prices.index)
        return prices[keep]

    def _simulate(
        self,
        prices: pd.DataFrame,
        target_weights: pd.DataFrame,
    ) -> tuple[pd.Series, list[dict[str, Any]], float, float]:
        """Walk forward bar-by-bar to compute the equity curve.

        Returns ``(equity_curve, rebalance_log, win_rate, avg_turnover)``.

        The equity curve is denominated in the same units as
        ``initial_capital``. Rebalances fire every ``rebalance_freq_days``
        bars from the first window bar. Between rebalances the held
        weights drift naturally with prices (no continuous re-balancing).
        """

        idx = prices.index
        equity = pd.Series(self._initial_capital, index=idx, dtype=float)

        # Active weights held into the next bar. We rebalance to the
        # strategy's *target* (post-lag) weight at each rebalance bar.
        active_weights = pd.Series(0.0, index=prices.columns, dtype=float)

        rebalance_log: list[dict[str, Any]] = []
        positive_period_count = 0
        period_count = 0
        turnover_sum = 0.0

        # Pre-compute simple returns so the inner loop is index-light.
        returns = prices.pct_change().fillna(0.0)

        last_rebalance_equity = self._initial_capital

        for bar_position, dt in enumerate(idx):
            row_return = returns.loc[dt]
            # Apply the weights' P&L to today's equity. Bar 0 has 0% return
            # by construction (pct_change → NaN → 0), so we don't add any
            # spurious drift before the first rebalance.
            if bar_position == 0:
                equity.iat[bar_position] = self._initial_capital
            else:
                period_return = float((active_weights * row_return).sum())
                # Cash bucket implicitly earns 0% — gross_cap < 1 leaves the
                # remainder un-allocated, which is exactly the strategy's
                # invariant.
                equity.iat[bar_position] = float(equity.iat[bar_position - 1]) * (
                    1.0 + period_return
                )

            # Rebalance: on the first bar AND on every cadence step
            # thereafter, slot in the strategy's lagged target weights.
            if bar_position % self._rebalance_freq_days == 0:
                desired = target_weights.loc[dt].reindex(prices.columns).fillna(0.0)
                turnover = float((desired - active_weights).abs().sum()) / 2.0
                turnover_sum += turnover

                # Period P&L since the prior rebalance — credits the win-rate
                # accounting. Skip the very first bar because there's no
                # holding period yet.
                if bar_position > 0:
                    period_return_pct = (
                        float(equity.iat[bar_position]) / last_rebalance_equity - 1.0
                    )
                    if period_return_pct > 0:
                        positive_period_count += 1
                    period_count += 1
                    rebalance_log.append(
                        {
                            "date": str(dt.date()),
                            "weights": {
                                k: float(v) for k, v in desired.items() if v > 1e-9
                            },
                            "turnover": float(turnover),
                            "period_return_pct": float(period_return_pct * 100.0),
                            "equity_after": float(equity.iat[bar_position]),
                        }
                    )
                else:
                    rebalance_log.append(
                        {
                            "date": str(dt.date()),
                            "weights": {
                                k: float(v) for k, v in desired.items() if v > 1e-9
                            },
                            "turnover": float(turnover),
                            "period_return_pct": 0.0,
                            "equity_after": float(equity.iat[bar_position]),
                        }
                    )

                active_weights = desired.copy()
                last_rebalance_equity = float(equity.iat[bar_position])

        n_rebalances = max(len(rebalance_log), 1)
        avg_turnover = turnover_sum / n_rebalances
        win_rate = positive_period_count / period_count if period_count else 0.0
        return equity, rebalance_log, win_rate, avg_turnover

    def _compute_metrics(
        self,
        equity: pd.Series,
        win_rate: float,
        avg_turnover: float,
    ) -> dict[str, Any]:
        """Turn a portfolio equity curve into the headline performance metrics."""

        initial = float(equity.iloc[0])
        final = float(equity.iloc[-1])
        if initial <= 0:
            return {
                "total_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "calmar_ratio": None,
                "avg_turnover_pct": 0.0,
                "win_rate": 0.0,
            }

        total_return = final / initial - 1.0
        n_bars = len(equity)
        years = max(n_bars / TRADING_DAYS_PER_YEAR, 1.0 / TRADING_DAYS_PER_YEAR)
        annualized_return = (1.0 + total_return) ** (1.0 / years) - 1.0

        daily_returns = equity.pct_change().dropna().to_numpy(dtype=float)
        if daily_returns.size >= 2:
            std = float(daily_returns.std(ddof=1))
            mean = float(daily_returns.mean())
            sharpe = (mean / std) * math.sqrt(TRADING_DAYS_PER_YEAR) if std > 1e-15 else 0.0
        else:
            sharpe = 0.0

        # Max drawdown: running max -> drop from peak. Expressed as a
        # positive percent (e.g. 8.5 means 8.5% drawdown).
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_dd = float(drawdown.min())  # negative number, e.g. -0.085
        max_dd_pct = float(abs(max_dd) * 100.0)

        calmar: Optional[float]
        if max_dd_pct > 1e-9:
            calmar = float(annualized_return / (max_dd_pct / 100.0))
        else:
            calmar = None

        return {
            "total_return_pct": float(total_return * 100.0),
            "annualized_return_pct": float(annualized_return * 100.0),
            "sharpe_ratio": float(sharpe),
            "max_drawdown_pct": float(max_dd_pct),
            "calmar_ratio": calmar,
            "avg_turnover_pct": float(avg_turnover * 100.0),
            "win_rate": float(win_rate),
        }

    def _comparable_buy_hold_return(self, window_prices: pd.DataFrame) -> float:
        """Equal-weight buy-and-hold over the window for the same universe.

        We use the configured universe (not the full price matrix) and
        equal-weight what's available. This gives the strategy a
        deliberately *naive* benchmark — beating it isn't a high bar, but
        underperforming it definitively means the rotation logic is
        hurting.
        """

        if window_prices.empty or len(window_prices) < 2:
            return 0.0
        first = window_prices.iloc[0]
        last = window_prices.iloc[-1]
        per_asset_return = (last / first) - 1.0
        # NaN-guard: drop any asset that didn't trade at the bounds.
        per_asset_return = per_asset_return.replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if per_asset_return.empty:
            return 0.0
        return float(per_asset_return.mean() * 100.0)

    def _build_caveats(self) -> list[str]:
        return [
            "no_transaction_costs_modeled",
            "no_bid_ask_spread_or_slippage",
            "no_market_impact",
            "next_bar_close_fills_only",
            "equal_weight_buy_hold_benchmark",
            "ignores_survivorship_bias",
            f"rebalance_cadence_fixed_at_{self._rebalance_freq_days}_bar(s)",
        ]

    def _empty_report(self, reason: str) -> BacktestReport:
        return BacktestReport(
            period_start=(
                str(self._period_start.date()) if self._period_start is not None else None
            ),
            period_end=(
                str(self._period_end.date()) if self._period_end is not None else None
            ),
            n_bars=0,
            n_assets=0,
            n_rebalances=0,
            initial_capital=self._initial_capital,
            final_equity=self._initial_capital,
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            sharpe_ratio=0.0,
            max_drawdown_pct=0.0,
            calmar_ratio=None,
            avg_turnover_pct=0.0,
            win_rate=0.0,
            comparable_buy_hold_return_pct=0.0,
            policy_signal_factor_enabled=self._policy_factor_enabled,
            rebalance_freq_days=self._rebalance_freq_days,
            rebalance_log=[],
            caveats=[*self._build_caveats(), f"empty_report:{reason}"],
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _to_timestamp(
    value: Optional[Union[str, datetime, pd.Timestamp]],
) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert NaN/inf to None and numpy scalars to native types.

    FastAPI's default JSON encoder errors on non-finite floats. We pre-walk
    the report dict to swap them for ``None`` so the wire payload stays
    valid JSON without the caller having to remember to call ``json.dumps(..., allow_nan=False)``.
    """

    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if not math.isfinite(v) else v
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    return obj


__all__ = [
    "DEFAULT_INITIAL_CAPITAL",
    "DEFAULT_REBALANCE_FREQ_DAYS",
    "BacktestReport",
    "EtfRotationBacktester",
]
