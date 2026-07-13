"""Data-driven calibration of ComprehensiveScorer dimension weights.

This is a RIGOROUS, reproducible, point-in-time calibration harness. It answers
one question: do better dimension weights for ``ComprehensiveScorer`` exist that
beat the current arbitrary weights OUT-OF-SAMPLE?

Design decisions (read these — they are the difference between honest research
and self-deception):

1. POINT-IN-TIME / NO LOOK-AHEAD. At every rebalance date ``D`` we slice each
   symbol's history to rows with index ``<= D`` BEFORE computing any sub-score,
   and we ``assert`` that the sliced frame's last index is ``<= D``. The label
   is the strictly-forward 20-trading-day return measured from ``D``'s close to
   ``D+20``'s close. There is no overlap between scoring inputs and the label.

2. SCOPE = the 4 PRICE/VOLUME dims only: trend, volume, sentiment, technical.
   ``fundamental`` is EXCLUDED from optimization because
   ``FundamentalAnalyzer`` uses the latest-available fundamentals (NOT
   point-in-time); scoring it on historical dates would inject look-ahead. We
   therefore hold fundamental's share fixed at its current 0.20 and optimize the
   remaining 0.80 across the 4 price/volume dims (each >= 0, the 4 summing to
   0.80). The fundamental contribution is a constant additive term across all
   symbols on a given date, so it does not affect the cross-sectional rank IC of
   the 4-dim weighted score and can be ignored in the IC computation.

3. WE REUSE THE REAL SCORING CODE. We call the actual sub-analyzers
   (``TrendAnalyzer.analyze_trend``, ``VolumePriceAnalyzer.analyze``,
   ``SentimentAnalyzer.analyze``) on the sliced frame and feed their dicts into
   ``ComprehensiveScorer._calculate_{trend,volume,sentiment,technical}_score``.
   We do NOT reimplement the dimensions.

4. METRIC = cross-sectional rank IC. For each rebalance date we compute the
   Spearman correlation between the weighted 4-dim score and the forward return
   ACROSS symbols. We report the mean IC and ICIR (mean / std) over dates.

5. TRAIN/TEST SPLIT. The earlier ~70% of dates train the weights (SLSQP, then a
   coarse simplex grid as a sanity cross-check); the later ~30% are held out and
   evaluated ONCE for both the current and calibrated weights.

DECISION RULE (honest): update ``DEFAULT_WEIGHTS`` only if the calibrated TEST
mean IC beats the current TEST mean IC by >= +0.01 absolute, on the same OOS
dates, and the improvement is not driven by a single date. Otherwise keep the
current weights and report the IC honestly. This script ONLY measures and
reports; it never edits source files.

Usage::

    .venv/bin/python scripts/calibrate_scorer_weights.py
    .venv/bin/python scripts/calibrate_scorer_weights.py --start 2021-06-01 \
        --end 2024-06-01 --horizon 20 --min-history 250

Caveats: mild survivorship bias (the universe is currently-liquid names);
fundamental excluded from optimization (see decision 2); IC is a noisy estimate
on ~40 symbols per date.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.optimize import minimize
from scipy.stats import spearmanr

# Make ``src`` importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.analytics.comprehensive_scorer import ComprehensiveScorer  # noqa: E402
from src.analytics.sentiment_analyzer import SentimentAnalyzer  # noqa: E402
from src.analytics.trend_analyzer import TrendAnalyzer  # noqa: E402
from src.analytics.volume_price_analyzer import VolumePriceAnalyzer  # noqa: E402

logger = logging.getLogger("calibrate_scorer_weights")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 4 price/volume dims we calibrate (fundamental held fixed at 0.20).
DIMS = ("trend", "volume", "sentiment", "technical")

# Their combined budget (1.0 - fundamental's fixed 0.20).
PRICE_VOL_BUDGET = 0.80

# Current weights for the 4 price/volume dims (from comprehensive_scorer.py).
# trend .30 / volume .20 / sentiment .20 / technical .10 (sum = 0.80).
CURRENT_PRICE_VOL_WEIGHTS: dict[str, float] = {
    "trend": 0.30,
    "volume": 0.20,
    "sentiment": 0.20,
    "technical": 0.10,
}

# Fundamental's fixed share (NOT optimized — see module docstring).
FUNDAMENTAL_WEIGHT = 0.20

# Default diversified, currently-liquid A-share universe (~45 names across
# sectors). Survivorship caveat noted in the module docstring.
DEFAULT_UNIVERSE: tuple[str, ...] = (
    # Banks / financials
    "601398.SH", "601288.SH", "600036.SH", "601318.SH", "600030.SH",
    "601166.SH", "000001.SZ",
    # Liquor / consumer staples
    "600519.SH", "000858.SZ", "600887.SH", "603288.SH", "000568.SZ",
    # Tech / electronics / semis
    "002415.SZ", "000725.SZ", "002230.SZ", "603501.SH", "002475.SZ",
    "300750.SZ", "002594.SZ",
    # Pharma / healthcare
    "600276.SH", "300760.SZ", "603259.SH", "000538.SZ", "600196.SH",
    # Energy / utilities
    "601857.SH", "600028.SH", "601088.SH", "600900.SH", "601985.SH",
    # Materials / industrials
    "600019.SH", "601899.SH", "600585.SH", "000333.SZ", "000651.SZ",
    # Autos / machinery
    "601633.SH", "600031.SH", "000625.SZ",
    # Telecom / internet / media
    "600050.SH", "000063.SZ", "002714.SZ",
    # Real estate / construction
    "600048.SH", "601668.SH",
    # Agriculture / retail
    "300498.SZ", "601225.SH",
)

DEFAULT_CACHE_DIR = _REPO_ROOT / "data" / "_calib_cache"


# ---------------------------------------------------------------------------
# Data fetching with on-disk checkpoint cache
# ---------------------------------------------------------------------------


def _cache_path(cache_dir: Path, symbol: str, start: str, end: str) -> Path:
    safe = symbol.replace(".", "_")
    return cache_dir / f"{safe}__{start}__{end}.csv"


def load_or_fetch_history(
    provider: Any,
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    cache_dir: Path,
) -> pd.DataFrame:
    """Return a symbol's daily history, using an on-disk CSV checkpoint.

    On a network blip a rerun loads completed symbols from cache instead of
    refetching. The cache key embeds the symbol and date window.
    """
    start_s = start_date.strftime("%Y-%m-%d")
    end_s = end_date.strftime("%Y-%m-%d")
    path = _cache_path(cache_dir, symbol, start_s, end_s)

    if path.exists():
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            df.index.name = "date"
            if not df.empty:
                logger.info("cache hit  %-12s rows=%d", symbol, len(df))
                return df
        except Exception as exc:  # pragma: no cover - corrupt cache fallback
            logger.warning("cache read failed for %s (%s); refetching", symbol, exc)

    df = provider.get_historical_data(
        symbol, start_date=start_date, end_date=end_date, interval="1d"
    )
    if df is None or df.empty:
        logger.warning("fetch EMPTY %-12s (skipping)", symbol)
        return pd.DataFrame()

    df = df.sort_index()
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    logger.info("fetched    %-12s rows=%d", symbol, len(df))
    return df


# ---------------------------------------------------------------------------
# Point-in-time dimension scoring (reuses the REAL scoring code)
# ---------------------------------------------------------------------------


@dataclass
class _Analyzers:
    """Holds the real sub-analyzers + scorer (instantiated once)."""

    trend: TrendAnalyzer = field(default_factory=TrendAnalyzer)
    volume: VolumePriceAnalyzer = field(default_factory=VolumePriceAnalyzer)
    sentiment: SentimentAnalyzer = field(default_factory=SentimentAnalyzer)
    scorer: ComprehensiveScorer = field(default_factory=ComprehensiveScorer)


def compute_dim_scores_point_in_time(
    history: pd.DataFrame,
    rebalance_date: pd.Timestamp,
    analyzers: _Analyzers,
    symbol: str,
) -> dict[str, float] | None:
    """Compute the 4 price/volume sub-scores using ONLY data <= rebalance_date.

    Returns ``{trend, volume, sentiment, technical}`` in [0, 100], or ``None``
    if there is insufficient history. POINT-IN-TIME: we slice to ``<= D`` and
    assert no look-ahead before scoring.
    """
    sliced = history.loc[history.index <= rebalance_date]
    if len(sliced) < 50:
        return None

    # HARD no-look-ahead assertion: the scoring frame must not contain any bar
    # strictly after the rebalance date.
    assert sliced.index.max() <= rebalance_date, (
        f"look-ahead: {symbol} sliced frame ends {sliced.index.max()} "
        f"> rebalance {rebalance_date}"
    )

    # Call the REAL sub-analyzers on the sliced (point-in-time) frame.
    trend_result = analyzers.trend.analyze_trend(sliced)
    volume_result = analyzers.volume.analyze(sliced)
    sentiment_result = analyzers.sentiment.analyze(sliced, symbol)

    # Feed those into the REAL scorer's per-dimension helpers.
    return {
        "trend": float(analyzers.scorer._calculate_trend_score(trend_result)),
        "volume": float(analyzers.scorer._calculate_volume_score(volume_result)),
        "sentiment": float(analyzers.scorer._calculate_sentiment_score(sentiment_result)),
        "technical": float(analyzers.scorer._calculate_technical_score(trend_result)),
    }


def forward_return(
    history: pd.DataFrame,
    rebalance_date: pd.Timestamp,
    horizon: int,
) -> float | None:
    """Forward ``horizon``-trading-day return measured strictly AFTER D.

    Uses D's close and D+horizon's close: ``close[D+h] / close[D] - 1``.
    Returns ``None`` if D or D+horizon does not exist.
    """
    idx = history.index
    positions = idx.get_indexer([rebalance_date])
    pos = int(positions[0])
    if pos < 0:
        return None
    fwd_pos = pos + horizon
    if fwd_pos >= len(idx):
        return None
    close_d = float(history["close"].iloc[pos])
    close_fwd = float(history["close"].iloc[fwd_pos])
    if close_d <= 0:
        return None
    return close_fwd / close_d - 1.0


# ---------------------------------------------------------------------------
# Rebalance dates
# ---------------------------------------------------------------------------


def build_rebalance_dates(
    histories: dict[str, pd.DataFrame],
    start_date: datetime,
    end_date: datetime,
    min_history: int,
) -> list[pd.Timestamp]:
    """First trading day of each month within the window.

    A date is kept only if at least one symbol has ``>= min_history`` prior bars
    at that date (per-symbol min-history is enforced again during scoring).
    """
    # Union of all trading days across symbols.
    all_days = pd.DatetimeIndex(
        sorted(set().union(*[set(df.index) for df in histories.values()]))
    )
    window = all_days[(all_days >= pd.Timestamp(start_date)) & (all_days <= pd.Timestamp(end_date))]
    if window.empty:
        return []

    # First trading day of each (year, month).
    first_of_month: list[pd.Timestamp] = []
    seen: set[tuple[int, int]] = set()
    for day in window:
        key = (day.year, day.month)
        if key not in seen:
            seen.add(key)
            first_of_month.append(day)

    # Keep only dates where >= 1 symbol has enough prior history.
    kept: list[pd.Timestamp] = []
    for d in first_of_month:
        enough = any((df.index <= d).sum() >= min_history for df in histories.values())
        if enough:
            kept.append(d)
    return kept


# ---------------------------------------------------------------------------
# Panel construction: (date, symbol) -> 4 dim scores + forward return
# ---------------------------------------------------------------------------


def build_panel(
    histories: dict[str, pd.DataFrame],
    rebalance_dates: list[pd.Timestamp],
    horizon: int,
    min_history: int,
) -> pd.DataFrame:
    """Build a tidy panel with one row per (date, symbol).

    Columns: date, symbol, trend, volume, sentiment, technical, fwd_return.
    """
    analyzers = _Analyzers()
    rows: list[dict[str, Any]] = []

    for d in rebalance_dates:
        for symbol, hist in histories.items():
            if (hist.index <= d).sum() < min_history:
                continue
            # Forward return must exist (D and D+horizon both present).
            fwd = forward_return(hist, d, horizon)
            if fwd is None:
                continue
            scores = compute_dim_scores_point_in_time(hist, d, analyzers, symbol)
            if scores is None:
                continue
            rows.append(
                {
                    "date": d,
                    "symbol": symbol,
                    **scores,
                    "fwd_return": fwd,
                }
            )

    panel = pd.DataFrame(rows)
    if not panel.empty:
        panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
    return panel


# ---------------------------------------------------------------------------
# Rank IC metric
# ---------------------------------------------------------------------------


def weighted_score(panel: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted 4-dim score per row (fundamental excluded — constant per date)."""
    score = pd.Series(0.0, index=panel.index)
    for dim in DIMS:
        score = score + panel[dim] * weights[dim]
    return score


def per_date_rank_ic(panel: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Cross-sectional Spearman rank IC per date.

    For each date, correlate the weighted score against the forward return
    across symbols. Dates with < 3 symbols or zero score-variance are skipped.
    """
    scores = weighted_score(panel, weights)
    work = panel.copy()
    work["_score"] = scores
    ics: dict[pd.Timestamp, float] = {}
    for d, grp in work.groupby("date"):
        if len(grp) < 3:
            continue
        if grp["_score"].nunique() < 2 or grp["fwd_return"].nunique() < 2:
            continue
        ic, _ = spearmanr(grp["_score"], grp["fwd_return"])
        if not np.isnan(ic):
            ics[d] = float(ic)
    return pd.Series(ics).sort_index()


@dataclass
class ICStats:
    mean_ic: float
    icir: float
    std_ic: float
    n_dates: int

    def __str__(self) -> str:
        return (
            f"mean_IC={self.mean_ic:+.4f}  ICIR={self.icir:+.3f}  "
            f"std={self.std_ic:.4f}  n_dates={self.n_dates}"
        )


def ic_stats(panel: pd.DataFrame, weights: dict[str, float]) -> ICStats:
    ics = per_date_rank_ic(panel, weights)
    if ics.empty:
        return ICStats(mean_ic=float("nan"), icir=float("nan"), std_ic=float("nan"), n_dates=0)
    mean_ic = float(ics.mean())
    std_ic = float(ics.std(ddof=1)) if len(ics) > 1 else float("nan")
    icir = mean_ic / std_ic if std_ic and not np.isnan(std_ic) and std_ic > 0 else float("nan")
    return ICStats(mean_ic=mean_ic, icir=icir, std_ic=std_ic, n_dates=len(ics))


# ---------------------------------------------------------------------------
# Weight optimization (maximize TRAIN mean rank IC)
# ---------------------------------------------------------------------------


def _normalize_to_budget(raw: np.ndarray) -> dict[str, float]:
    """Map a non-negative raw vector to dim weights summing to PRICE_VOL_BUDGET."""
    raw = np.clip(raw, 0.0, None)
    total = raw.sum()
    if total <= 0:
        raw = np.ones_like(raw)
        total = raw.sum()
    scaled = raw / total * PRICE_VOL_BUDGET
    return {dim: float(w) for dim, w in zip(DIMS, scaled, strict=False)}


def optimize_weights(train_panel: pd.DataFrame) -> dict[str, float]:
    """Maximize TRAIN mean rank IC over the 4 dims (>=0, sum == budget).

    Uses SLSQP from multiple starts, cross-checked against a coarse simplex grid.
    Returns the best dim-weight dict.
    """

    def neg_mean_ic(raw: np.ndarray) -> float:
        weights = _normalize_to_budget(raw)
        ics = per_date_rank_ic(train_panel, weights)
        if ics.empty:
            return 1.0
        return -float(ics.mean())

    best_raw: np.ndarray | None = None
    best_val = np.inf

    # Multi-start SLSQP (raw vector on the simplex; bounds keep it non-negative).
    starts = [
        np.array([0.30, 0.20, 0.20, 0.10]),  # current
        np.array([0.20, 0.20, 0.20, 0.20]),  # equal
        np.array([0.40, 0.20, 0.10, 0.10]),
        np.array([0.10, 0.30, 0.30, 0.10]),
        np.array([0.25, 0.25, 0.15, 0.15]),
    ]
    bounds = [(0.0, 1.0)] * len(DIMS)
    constraints = ({"type": "eq", "fun": lambda r: float(np.sum(r) - PRICE_VOL_BUDGET)},)
    for s in starts:
        res = minimize(
            neg_mean_ic,
            s,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 200, "ftol": 1e-6},
        )
        if res.fun < best_val:
            best_val = float(res.fun)
            best_raw = np.asarray(res.x, dtype=float)

    # Coarse simplex grid sanity cross-check (step 0.05 over the budget).
    step = 0.05
    n_steps = round(PRICE_VOL_BUDGET / step)
    for a in range(n_steps + 1):
        for b in range(n_steps + 1 - a):
            for c in range(n_steps + 1 - a - b):
                d = n_steps - a - b - c
                raw = np.array([a, b, c, d], dtype=float) * step
                val = neg_mean_ic(raw)
                if val < best_val:
                    best_val = val
                    best_raw = raw

    assert best_raw is not None
    return _normalize_to_budget(best_raw)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _full_weights(price_vol: dict[str, float]) -> dict[str, float]:
    """Combine 4 dim weights with the fixed fundamental share -> 5 weights."""
    out = dict(price_vol)
    out["fundamental"] = FUNDAMENTAL_WEIGHT
    return out


def make_decision(
    current_test: ICStats,
    calibrated_test: ICStats,
    calibrated_ics_test: pd.Series,
    current_ics_test: pd.Series,
    margin: float,
) -> tuple[bool, str]:
    """Apply the honest decision rule. Returns (should_update, rationale)."""
    if calibrated_test.n_dates == 0 or current_test.n_dates == 0:
        return False, "No usable OOS dates — cannot validate. KEEP current weights."

    delta = calibrated_test.mean_ic - current_test.mean_ic
    if delta < margin:
        return (
            False,
            f"OOS improvement {delta:+.4f} < required margin {margin:+.4f}. "
            "KEEP current weights.",
        )

    # Robustness: ensure the win is not driven by a single date. Recompute the
    # OOS delta with the single most-favorable date dropped.
    aligned = pd.concat(
        [calibrated_ics_test.rename("cal"), current_ics_test.rename("cur")], axis=1
    ).dropna()
    if len(aligned) >= 3:
        per_date_delta = aligned["cal"] - aligned["cur"]
        drop_best = per_date_delta.drop(per_date_delta.idxmax())
        robust_delta = float(drop_best.mean())
        if robust_delta < margin:
            return (
                False,
                f"OOS improvement {delta:+.4f} passes margin but collapses to "
                f"{robust_delta:+.4f} after dropping the single best date "
                "(single-date artifact). KEEP current weights.",
            )

    return (
        True,
        f"OOS improvement {delta:+.4f} >= margin {margin:+.4f} and survives "
        "single-date drop. UPDATE weights.",
    )


def print_report(
    panel: pd.DataFrame,
    train_panel: pd.DataFrame,
    test_panel: pd.DataFrame,
    calibrated: dict[str, float],
    margin: float,
) -> None:
    cur = CURRENT_PRICE_VOL_WEIGHTS

    cur_train = ic_stats(train_panel, cur)
    cur_test = ic_stats(test_panel, cur)
    cal_train = ic_stats(train_panel, calibrated)
    cal_test = ic_stats(test_panel, calibrated)

    cal_ics_test = per_date_rank_ic(test_panel, calibrated)
    cur_ics_test = per_date_rank_ic(test_panel, cur)

    should_update, rationale = make_decision(
        cur_test, cal_test, cal_ics_test, cur_ics_test, margin
    )

    n_dates = panel["date"].nunique()
    n_symbols = panel["symbol"].nunique()
    n_obs = len(panel)

    print("\n" + "=" * 72)
    print("COMPREHENSIVE SCORER WEIGHT CALIBRATION REPORT")
    print("=" * 72)
    print(f"\nData: {n_symbols} symbols x {n_dates} rebalance dates = {n_obs} observations")
    print(f"  Train dates: {train_panel['date'].nunique()}  |  Test dates: {test_panel['date'].nunique()}")
    print("  Forward-return horizon: 20 trading days (label measured AFTER D)")

    print("\nWEIGHTS (4 price/volume dims; fundamental fixed at 0.20):")
    print(f"  {'dim':<12}{'current':>10}{'calibrated':>14}")
    for dim in DIMS:
        print(f"  {dim:<12}{cur[dim]:>10.3f}{calibrated[dim]:>14.3f}")
    print(f"  {'(sum)':<12}{sum(cur.values()):>10.3f}{sum(calibrated.values()):>14.3f}")
    print(f"  {'fundamental':<12}{FUNDAMENTAL_WEIGHT:>10.3f}{FUNDAMENTAL_WEIGHT:>14.3f}  (fixed)")

    print("\nMEAN RANK IC (cross-sectional Spearman, per date):")
    print("  current weights:")
    print(f"    IN-SAMPLE  (train): {cur_train}")
    print(f"    OUT-SAMPLE (test) : {cur_test}")
    print("  calibrated weights:")
    print(f"    IN-SAMPLE  (train): {cal_train}")
    print(f"    OUT-SAMPLE (test) : {cal_test}")

    if cal_test.n_dates and cur_test.n_dates:
        print(f"\n  OOS mean-IC delta (calibrated - current): {cal_test.mean_ic - cur_test.mean_ic:+.4f}")

    print("\nDECISION:")
    print(f"  {'UPDATE WEIGHTS' if should_update else 'KEEP CURRENT WEIGHTS'}")
    print(f"  {rationale}")

    if should_update:
        full = _full_weights(calibrated)
        print("\n  Proposed DEFAULT_WEIGHTS (renormalized, all 5 sum to 1.0):")
        for k, v in full.items():
            print(f"    {k:<12}{v:.4f}")
        print(f"    (sum = {sum(full.values()):.4f})")

    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", default="2021-06-01", help="rebalance window start (YYYY-MM-DD)")
    p.add_argument("--end", default="2024-06-01", help="rebalance window end (YYYY-MM-DD)")
    p.add_argument("--horizon", type=int, default=20, help="forward-return horizon in trading days")
    p.add_argument("--min-history", type=int, default=250, help="min prior bars required at each date")
    p.add_argument("--train-frac", type=float, default=0.70, help="fraction of dates used for training")
    p.add_argument("--margin", type=float, default=0.01, help="required OOS mean-IC improvement to update")
    p.add_argument("--universe", nargs="*", default=None, help="override symbol list")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="checkpoint cache directory")
    p.add_argument("--min-symbols", type=int, default=15, help="stop if fewer usable symbols")
    p.add_argument("--fetch-pad-days", type=int, default=420, help="extra days fetched before --start for history")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # Load .env from the repo root, then fall back to the current working
    # directory (covers worktree checkouts where .env lives in the primary tree
    # or alongside the invocation). Existing env vars always take precedence.
    load_dotenv(_REPO_ROOT / ".env")
    load_dotenv(".env")

    universe = tuple(args.universe) if args.universe else DEFAULT_UNIVERSE
    cache_dir = Path(args.cache_dir)
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")

    # Fetch from before --start so that the first rebalance dates already have
    # >= min-history prior bars, plus past --end so forward returns exist.
    fetch_start = start_date - pd.Timedelta(days=args.fetch_pad_days)
    fetch_end = end_date + pd.Timedelta(days=60)

    # Lazy import so --help works without a token / network.
    from src.data.providers.tushare_provider import TushareProvider

    provider = TushareProvider()

    print(f"Fetching {len(universe)} symbols ({fetch_start.date()} -> {fetch_end.date()}) ...")
    histories: dict[str, pd.DataFrame] = {}
    for symbol in universe:
        try:
            df = load_or_fetch_history(provider, symbol, fetch_start, fetch_end, cache_dir)
        except Exception as exc:  # per-symbol failure: skip + log, keep going
            logger.warning("fetch FAILED %-12s (%s); skipping", symbol, exc)
            continue
        if df.empty or "close" not in df.columns:
            continue
        histories[symbol] = df

    print(f"Usable symbols: {len(histories)}/{len(universe)}")
    if len(histories) < args.min_symbols:
        print(
            f"\nINSUFFICIENT DATA — only {len(histories)} usable symbols "
            f"(< {args.min_symbols}). Harness delivered; run later with more data."
        )
        return 2

    rebalance_dates = build_rebalance_dates(histories, start_date, end_date, args.min_history)
    print(f"Rebalance dates: {len(rebalance_dates)}")
    if len(rebalance_dates) < 6:
        print(
            f"\nINSUFFICIENT DATA — only {len(rebalance_dates)} rebalance dates. "
            "Harness delivered; run later with a wider window."
        )
        return 2

    print("Building point-in-time panel (this calls the real sub-analyzers) ...")
    panel = build_panel(histories, rebalance_dates, args.horizon, args.min_history)
    if panel.empty or panel["date"].nunique() < 6:
        print("\nINSUFFICIENT DATA — panel too small. Harness delivered; run later.")
        return 2

    # Chronological train/test split on the date axis.
    dates_sorted = sorted(panel["date"].unique())
    split_idx = max(1, round(len(dates_sorted) * args.train_frac))
    train_dates = set(dates_sorted[:split_idx])
    test_dates = set(dates_sorted[split_idx:])
    train_panel = panel[panel["date"].isin(train_dates)].copy()
    test_panel = panel[panel["date"].isin(test_dates)].copy()

    if test_panel["date"].nunique() < 2:
        print("\nINSUFFICIENT DATA — fewer than 2 OOS dates. Harness delivered; run later.")
        return 2

    print("Optimizing weights on TRAIN (SLSQP + simplex grid) ...")
    calibrated = optimize_weights(train_panel)

    print_report(panel, train_panel, test_panel, calibrated, args.margin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
