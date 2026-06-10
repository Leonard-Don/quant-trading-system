"""Service that assembles the cached A-share panel and runs the low-vol backtest.

Bridges the network world (Tushare provider + the pickle factor cache under
``data/_factor_cache/``) and the PURE
:func:`src.backtest.low_vol_portfolio.run_low_vol_portfolio_backtest`.

The heavy inputs — per-symbol total-return prices and ``adj_factor`` — are
ALREADY CACHED (CSI300/CSI500 panels, 2018-2024). This service RELIES ON THAT
CACHE and never re-fetches full price histories. The live calls are the light
eligibility lookups (``index_weight`` constituents + ``suspend_d`` suspensions)
per monthly rebalance date, plus one ``adj_factor`` fetch per symbol whose
pickle is missing (via ``build_panel``, when the provider supports it); the
endpoint caches the whole result with a daily TTL so even those run at most
once per universe per day. Symbols still lacking adj data after that are
COUNTED and surfaced (``adj_fallback``), and the run REFUSES above
``MAX_ADJ_FALLBACK_RATIO`` — total-return honesty is enforced, not assumed.

Blocking (touches disk + a few provider calls) — call via a threadpool.
"""

from __future__ import annotations

import pathlib
import time
from typing import Optional

import pandas as pd

from src.backtest.low_vol_portfolio import (
    DEFAULT_COST_RATES,
    run_low_vol_portfolio_backtest,
)
from src.data.factor_panel import (
    FactorPanel,
    build_eligible_by_date,
    build_panel,
    build_survivorship_free_universe,
)

# Cached span — DO NOT widen without re-running the cache build. The CSI300 and
# CSI500 panels + adj_factor for this window already live under the cache dir.
SPAN_START = "20180101"
SPAN_END = "20241231"
VOL_WINDOW = 60
MIN_HISTORY_BARS = 252  # one trading year before the first rebalance counts

# The pure backtester's first honesty invariant is total-return P&L. Symbols
# whose adj_factor is unavailable fall back to the raw close (dividend-free) —
# above this share of the panel, the "总收益复权价" claim is broken and the
# run must refuse instead of silently shipping a wrong-looking-right backtest.
MAX_ADJ_FALLBACK_RATIO = 0.05

DEFAULT_CACHE_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "_factor_cache"


class AdjFallbackMaterialError(RuntimeError):
    """Raised when too many symbols lack adj_factor for an honest total-return run."""


def _monthly_rebalance_dates(trading_dates) -> list[pd.Timestamp]:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]


def _total_return_close_map(
    panel: FactorPanel,
) -> tuple[dict[str, pd.Series], list[str]]:
    """``{symbol -> total-return close}`` from the panel, plus the fallback list.

    ``build_panel`` already loads ``{sym}_adj.pkl`` (and, when the provider
    supports ``get_adj_factor``, fetches + caches missing factors), so
    ``panel.total_return_close`` is the single source of truth. Symbols absent
    from ``panel.adj`` fall back to the raw close — they are RETURNED, not
    hidden, so the caller can account for (or refuse) the degradation.
    """
    adj: dict[str, pd.Series] = {}
    fallback: list[str] = []
    for sym in panel.symbols:
        adj[sym] = panel.total_return_close(sym).rename(sym)
        if sym not in panel.adj:
            fallback.append(sym)
    return adj, sorted(fallback)


def run_low_vol_portfolio_from_cache(
    provider,
    index_code: str,
    *,
    basket_n: int = 30,
    cache_dir: Optional[pathlib.Path] = None,
    window: int = VOL_WINDOW,
    sample_freq_days: int = 90,
    eligibility_chunk: int = 80,
    throttle_sleep: float = 0.0,
    cost_rates: Optional[dict] = None,
    max_adj_fallback_ratio: float = MAX_ADJ_FALLBACK_RATIO,
) -> dict:
    """Assemble the cached panel + eligibility and run the pure backtest.

    Args:
        provider: a Tushare-like provider (constituents + suspensions). Only the
            light eligibility / universe lookups touch it; prices come from cache.
        index_code: e.g. ``"000300.SH"`` (CSI300) or ``"000905.SH"`` (CSI500).
        basket_n: basket size for the low-vol long-only basket.
        cache_dir: factor-cache directory (defaults to ``data/_factor_cache``).
        window: realized-vol lookback (trading days).
        sample_freq_days: universe-sampling cadence for survivorship-free union.
        eligibility_chunk / throttle_sleep: batch the per-date eligibility calls
            with an optional sleep between chunks (0 in tests).
        cost_rates: override the A-share friction profile (defaults applied).

    Returns:
        The pure backtest dict augmented with ``index``, ``span``, ``basket_n``,
        ``window`` and ``cost_rates`` echo fields.
    """
    cache_dir = pathlib.Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    rates = cost_rates or DEFAULT_COST_RATES

    symbols = build_survivorship_free_universe(
        provider, index_code, SPAN_START, SPAN_END, sample_freq_days=sample_freq_days
    )
    # Prices + adj come from cache; build_panel reads {sym}_px.pkl (no refetch
    # when cached). adj is cache-only.
    panel = build_panel(symbols, SPAN_START, SPAN_END, provider, cache_dir=cache_dir)
    if not panel.symbols:
        return {
            "index": index_code,
            "span": f"{SPAN_START}..{SPAN_END}",
            "basket_n": basket_n,
            "window": window,
            "cost_rates": dict(rates),
            "equity_curve": [],
            "metrics": {"gross": {}, "net": {}, "benchmark": {}},
            "avg_annual_turnover": None,
            "n_periods": 0,
            "adj_fallback": {"count": 0, "ratio": 0.0, "symbols": []},
        }

    adj, fallback = _total_return_close_map(panel)
    fallback_ratio = len(fallback) / len(panel.symbols)
    if fallback_ratio > max_adj_fallback_ratio:
        raise AdjFallbackMaterialError(
            f"{len(fallback)}/{len(panel.symbols)} symbols "
            f"({fallback_ratio:.1%}) lack adj_factor data, so the backtest "
            "cannot honestly claim total-return (复权) P&L. Warm the cache "
            "(scripts/research/lowvol_portfolio_backtest.py fetches and caches "
            "{sym}_adj.pkl) or use a provider with get_adj_factor support."
        )

    base_dates = _monthly_rebalance_dates(panel.trading_dates)
    ref = panel.symbols[0]
    dates = [d for d in base_dates if len(panel.history(ref, d)) >= MIN_HISTORY_BARS]

    eligible_by_date: dict = {}
    for i in range(0, len(dates), eligibility_chunk):
        if hasattr(provider, "reset_throttle"):
            provider.reset_throttle()
        eligible_by_date.update(
            build_eligible_by_date(provider, index_code, dates[i : i + eligibility_chunk])
        )
        if throttle_sleep and i + eligibility_chunk < len(dates):
            time.sleep(throttle_sleep)

    result = run_low_vol_portfolio_backtest(
        panel,
        adj,
        dates,
        eligible_by_date,
        window=window,
        basket_n=basket_n,
        cost_rates=rates,
    )
    result.update(
        {
            "index": index_code,
            "span": f"{SPAN_START}..{SPAN_END}",
            "basket_n": basket_n,
            "window": window,
            "cost_rates": dict(rates),
            "adj_fallback": {
                "count": len(fallback),
                "ratio": fallback_ratio,
                "symbols": fallback[:20],
            },
        }
    )
    return result
