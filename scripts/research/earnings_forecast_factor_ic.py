"""Point-in-time IC probe for an earnings-expectation factor (业绩预告).

RESEARCH PROBE (not scorer integration). Question: does the profit-growth
implied by 业绩预告 (earnings preannouncements) predict forward returns on
CSI 300?

Factor — ``earnings_forecast_growth``:
    For each stock, take the LATEST 业绩预告 with ``ann_date <= as_of`` and use
    the midpoint of its forecast net-profit YoY change range
    ``(p_change_min, p_change_max)`` as the factor value. ``direction = +1``
    (higher expected growth -> bullish).

Point-in-time is CRITICAL: only forecasts ANNOUNCED on/before the rebalance
date (``ann_date <= as_of``) are visible. Stocks with no visible forecast are
simply absent that date — IC is computed on the subset that has one, which is
realistic.

Data: Tushare ``pro.forecast`` fetched PER STOCK over the window (the endpoint
rejects a bare ``period`` query — it requires ``ann_date`` or ``ts_code``), then
cached to ``data/_factor_cache/forecast/<ts_code>.pkl``.

Reuses the existing IC machinery (``build_panel`` / ``evaluate_factor`` /
``monthly_rebalance_dates``) — IC is NOT reimplemented here.

Run:
    .venv/bin/python scripts/research/earnings_forecast_factor_ic.py
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

# Source tree this file lives in (worktree or shared checkout).
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# The .env and the (already-warm) price/fundamental cache live in the shared
# checkout. Fall back to PROJECT_ROOT when running from the shared checkout
# directly (so the probe is portable).
SHARED_ROOT = pathlib.Path("/Users/leonardodon/quant-trading-system")
DATA_ROOT = SHARED_ROOT if (SHARED_ROOT / "data/_factor_cache").exists() else PROJECT_ROOT
ENV_ROOT = SHARED_ROOT if (SHARED_ROOT / ".env").exists() else PROJECT_ROOT

CACHE_DIR = DATA_ROOT / "data/_factor_cache"
FORECAST_CACHE_DIR = CACHE_DIR / "forecast"
START = "20190101"
END = "20240101"
HORIZONS = [5, 20, 60, 120]
# Forecast columns that matter for the point-in-time factor.
_FORECAST_COLS = ["ts_code", "ann_date", "end_date", "p_change_min", "p_change_max"]


def load_forecast_for_symbol(
    symbol: str, provider, *, start: str = START, end: str = END
) -> pd.DataFrame:
    """Return the 业绩预告 history for ``symbol`` (cached pickle, fetched once).

    The frame is normalised to the columns we need with ``ann_date``/``end_date``
    as ``datetime64`` and a numeric ``forecast_growth`` midpoint, sorted by
    ``ann_date``. Duplicate rows (Tushare emits update revisions) are dropped.
    Missing / empty payloads yield an empty (but correctly-columned) frame so
    callers never special-case ``None``.
    """
    FORECAST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = FORECAST_CACHE_DIR / f"{symbol}.pkl"
    if path.exists():
        raw = pd.read_pickle(path)
    else:
        ts_code = provider.normalize_symbol(symbol)
        pro = provider._get_pro_client()
        raw = pro.forecast(ts_code=ts_code, start_date=start, end_date=end)
        if raw is None:
            raw = pd.DataFrame(columns=_FORECAST_COLS)
        raw.to_pickle(path)
    return _normalise_forecast_frame(raw)


def _normalise_forecast_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Clean a raw ``pro.forecast`` frame into the point-in-time factor frame.

    Keeps the relevant columns, coerces ``ann_date``/``end_date`` to datetimes,
    computes the ``forecast_growth`` midpoint of ``(p_change_min, p_change_max)``,
    drops rows with no usable midpoint and duplicate ``(ann_date, end_date,
    forecast_growth)`` revisions, and sorts by ``ann_date``.
    """
    cols = [c for c in _FORECAST_COLS if c in raw.columns]
    if raw is None or raw.empty or "ann_date" not in cols:
        return pd.DataFrame(
            columns=[*_FORECAST_COLS, "forecast_growth"]
        ).astype({"ann_date": "datetime64[ns]"})
    df = raw[cols].copy()
    df["ann_date"] = pd.to_datetime(df["ann_date"].astype(str), errors="coerce")
    if "end_date" in df.columns:
        df["end_date"] = pd.to_datetime(df["end_date"].astype(str), errors="coerce")
    lo = pd.to_numeric(df.get("p_change_min"), errors="coerce")
    hi = pd.to_numeric(df.get("p_change_max"), errors="coerce")
    # Midpoint of the forecast YoY-change range; fall back to whichever bound
    # exists if only one is published.
    df["forecast_growth"] = pd.concat([lo, hi], axis=1).mean(axis=1, skipna=True)
    df = df.dropna(subset=["ann_date", "forecast_growth"])
    df = df.drop_duplicates(subset=["ann_date", "end_date", "forecast_growth"])
    return df.sort_values("ann_date").reset_index(drop=True)


def latest_forecast_growth(forecast_df: pd.DataFrame, as_of) -> float | None:
    """Midpoint growth of the latest forecast with ``ann_date <= as_of``.

    Returns ``None`` when no forecast is visible as of that date — the heart of
    the point-in-time gate.
    """
    if forecast_df is None or forecast_df.empty:
        return None
    visible = forecast_df.loc[forecast_df["ann_date"] <= pd.Timestamp(as_of)]
    if visible.empty:
        return None
    # ``forecast_df`` is ann_date-sorted, so the last visible row is the latest.
    return float(visible.iloc[-1]["forecast_growth"])


class EarningsForecastGrowthFactor:
    """业绩预告-implied profit-growth factor (point-in-time)."""

    name = "earnings_forecast_growth"
    direction = 1

    def __init__(self, forecasts: dict[str, pd.DataFrame]):
        # symbol -> normalised forecast frame (ann_date-sorted).
        self._forecasts = forecasts

    def compute(self, panel, as_of) -> pd.Series:
        out: dict[str, float] = {}
        for sym in panel.symbols:
            val = latest_forecast_growth(self._forecasts.get(sym), as_of)
            if val is not None:
                out[sym] = val
        return pd.Series(out, dtype=float)

    def coverage(self, panel, as_of) -> int:
        """# symbols with a visible forecast as of ``as_of`` (diagnostic)."""
        return int(self.compute(panel, as_of).notna().sum())


def _fmt(x) -> str:
    try:
        return f"{float(x):.4f}"
    except (TypeError, ValueError):
        return "-"


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ENV_ROOT / ".env")
    from scripts.run_factor_scorecard import monthly_rebalance_dates
    from src.analytics.factors.evaluation import evaluate_factor
    from src.data.factor_panel import build_panel
    from src.data.providers.tushare_provider import TushareProvider

    provider = TushareProvider()
    csi300 = provider.get_index_constituents("000300.SH")
    print(f"CSI300 constituents: {len(csi300)}")

    # Prices/fundamentals panel (prices already cached -> fast).
    panel = build_panel(csi300, START, END, provider, cache_dir=CACHE_DIR)
    usable = len(panel.symbols)
    print(f"panel built: {usable} symbols usable (of {len(csi300)} requested)")

    # Forecasts: fetch per usable symbol once, cache to a separate dir.
    print("loading 业绩预告 forecasts (cached per symbol)...")
    forecasts: dict[str, pd.DataFrame] = {}
    n_with_any = 0
    for sym in panel.symbols:
        fdf = load_forecast_for_symbol(sym, provider)
        forecasts[sym] = fdf
        if not fdf.empty:
            n_with_any += 1
    print(f"forecast history available for {n_with_any}/{usable} symbols")

    factor = EarningsForecastGrowthFactor(forecasts)

    # Monthly rebalance dates with >=252 bars of history; drop the final date so
    # a forward bar exists.
    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref_sym = panel.symbols[0]
    dates = [d for d in base_dates if len(panel.history(ref_sym, d)) >= 252]
    dates = dates[:-1] if dates else []
    print(f"rebalance dates: {len(dates)}")

    # Coverage diagnostic (avg # of stocks with a visible forecast per date).
    coverages = [factor.coverage(panel, d) for d in dates]
    avg_cov = float(sum(coverages) / len(coverages)) if coverages else 0.0

    print(f"\nfactor: {factor.name}  direction=+{factor.direction}")
    print(f"window: {START}-{END}  horizons: {HORIZONS}")
    print(f"avg coverage (stocks with visible forecast / date): {avg_cov:.1f}\n")

    header = (
        f"{'horizon':>7} | {'mean IC':>8} | {'OOS IC':>8} | {'ICIR':>7} | "
        f"{'stable':>6} | {'coverage':>8} | {'verdict':>7}"
    )
    print(header)
    print("-" * len(header))
    for h in HORIZONS:
        rep = evaluate_factor(factor, panel, dates, h)
        print(
            f"{h:>7} | {_fmt(rep['mean_ic']):>8} | {_fmt(rep['oos_mean_ic']):>8} | "
            f"{_fmt(rep['icir']):>7} | "
            f"{('yes' if rep.get('sign_stable') else 'no'):>6} | "
            f"{avg_cov:>8.1f} | "
            f"{('PASS' if rep.get('passes') else 'FAIL'):>7}"
        )


if __name__ == "__main__":
    main()
