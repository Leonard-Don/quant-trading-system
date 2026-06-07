# Factor Library + IC Validation (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a point-in-time factor library + IC evaluation engine that produces a factor scorecard (which candidate factors actually predict forward returns), without touching the scorer or frontend.

**Architecture:** Pure factor functions (`compute(panel, as_of) -> Series[symbol→value]`, using only data ≤ as_of) over a cached `FactorPanel` (OHLCV + Tushare fina_indicator with `ann_date` + moneyflow). An IC engine computes cross-sectional rank IC / ICIR / OOS / yearly stability per factor. A runner script emits the scorecard. Everything offline-testable with a synthetic panel; Tushare is only hit by the real run.

**Tech Stack:** Python 3.13, pandas/numpy, scipy.stats (spearmanr), pytest (`-o addopts=""`), Tushare via existing `TushareProvider`, `.venv/bin/python`.

**Conventions (every task):**
- Run tests: `.venv/bin/python -m pytest -o addopts="" <path> -q`
- Lint gate before each commit: `.venv/bin/python scripts/check_ruff_baseline.py` must report `new=0`
- Commit per task (work on a branch off `main`, e.g. `feat/factor-library-phase1`)
- All tests offline (no network; pytest-socket compatible) — build a synthetic `FactorPanel` in tests.

---

### Task 1: Cross-sectional utils + Factor protocol

**Files:**
- Create: `src/analytics/factors/__init__.py`
- Create: `src/analytics/factors/base.py`
- Test: `tests/unit/test_factor_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_factor_base.py
import numpy as np
import pandas as pd
import pytest
from src.analytics.factors.base import winsorize, cross_sectional_zscore, cross_sectional_rank

def test_winsorize_clips_tails():
    s = pd.Series([−100.0, 1, 2, 3, 4, 5, 100.0], index=list("abcdefg"))
    w = winsorize(s, lower=0.1, upper=0.9)
    assert w.max() < 100.0 and w.min() > −100.0
    # middle values unchanged
    assert w["c"] == 2.0

def test_zscore_mean0_std1():
    s = pd.Series([1.0, 2, 3, 4, 5])
    z = cross_sectional_zscore(s)
    assert abs(z.mean()) < 1e-9
    assert abs(z.std(ddof=0) − 1.0) < 1e-9

def test_zscore_constant_series_returns_zeros():
    s = pd.Series([3.0, 3, 3])
    z = cross_sectional_zscore(s)
    assert (z == 0).all()  # no divide-by-zero

def test_rank_in_unit_interval_and_monotone():
    s = pd.Series([10.0, 30, 20], index=["x", "y", "z"])
    r = cross_sectional_rank(s)
    assert r["x"] < r["z"] < r["y"]
    assert r.min() >= 0.0 and r.max() <= 1.0

def test_nan_handled_not_propagated():
    s = pd.Series([1.0, np.nan, 3.0])
    assert not cross_sectional_zscore(s).isna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_base.py -q`
Expected: FAIL (module `src.analytics.factors.base` not found)

- [ ] **Step 3: Write minimal implementation**

```python
# src/analytics/factors/__init__.py
"""Point-in-time factor library + IC evaluation (Phase 1, research-only)."""

# src/analytics/factors/base.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
import numpy as np
import pandas as pd

def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lower=lo, upper=hi)

def cross_sectional_zscore(s: pd.Series) -> pd.Series:
    x = s.astype(float)
    mu = x.mean(skipna=True)
    sd = x.std(skipna=True, ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((x − mu) / sd).fillna(0.0)

def cross_sectional_rank(s: pd.Series) -> pd.Series:
    # average-rank → [0,1]; NaNs → 0.5 (neutral)
    r = s.rank(method="average", na_option="keep")
    n = r.notna().sum()
    if n <= 1:
        return pd.Series(0.5, index=s.index)
    return ((r − 1) / (n − 1)).fillna(0.5)

@runtime_checkable
class Factor(Protocol):
    name: str
    direction: int  # +1: higher value = more bullish; −1: lower = more bullish

    def compute(self, panel, as_of: pd.Timestamp) -> pd.Series:
        """Return cross-sectional raw factor values {symbol: value}, using only data ≤ as_of."""
        ...
```

> Note: replace the unicode minus `−` with ASCII `-` when typing real code; shown here only to avoid markdown list parsing.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_base.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analytics/factors/__init__.py src/analytics/factors/base.py tests/unit/test_factor_base.py
.venv/bin/python scripts/check_ruff_baseline.py   # expect new=0
git commit -m "feat(factors): cross-sectional utils + Factor protocol"
```

---

### Task 2: FactorPanel data container + synthetic builder (test fixture)

**Files:**
- Create: `src/data/factor_panel.py`
- Test: `tests/unit/test_factor_panel.py`

The `FactorPanel` holds per-symbol DataFrames and enforces point-in-time access. Live fetching is added in Task 6; this task delivers the container + a synthetic constructor used by all later tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_factor_panel.py
import pandas as pd
import pytest
from src.data.factor_panel import FactorPanel

def _ohlcv(dates, start=10.0):
    n = len(dates)
    return pd.DataFrame({
        "open": [start + i*0.1 for i in range(n)],
        "high": [start + i*0.1 + 0.5 for i in range(n)],
        "low":  [start + i*0.1 - 0.5 for i in range(n)],
        "close":[start + i*0.1 for i in range(n)],
        "volume":[1_000_000 + i for i in range(n)],
    }, index=pd.DatetimeIndex(dates, name="date"))

def test_history_is_point_in_time():
    dates = pd.bdate_range("2024-01-01", periods=10)
    panel = FactorPanel(prices={"AAA": _ohlcv(dates)})
    h = panel.history("AAA", as_of=dates[4])
    assert h.index.max() == dates[4]        # nothing after as_of
    assert len(h) == 5

def test_symbols_and_trading_dates():
    dates = pd.bdate_range("2024-01-01", periods=6)
    panel = FactorPanel(prices={"AAA": _ohlcv(dates), "BBB": _ohlcv(dates, 20.0)})
    assert set(panel.symbols) == {"AAA", "BBB"}
    assert list(panel.trading_dates) == list(dates)

def test_fundamentals_gated_by_ann_date():
    dates = pd.bdate_range("2024-01-01", periods=10)
    funda = pd.DataFrame({
        "ann_date": pd.to_datetime(["2024-01-03", "2024-01-08"]),
        "end_date": pd.to_datetime(["2023-09-30", "2023-12-31"]),
        "roe": [10.0, 12.0],
    })
    panel = FactorPanel(prices={"AAA": _ohlcv(dates)}, fundamentals={"AAA": funda})
    # as_of before 2nd announcement → only first report visible
    row = panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-05"))
    assert row["roe"] == 10.0
    # as_of after 2nd announcement → newer report visible
    row2 = panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-09"))
    assert row2["roe"] == 12.0
    # as_of before any announcement → None
    assert panel.latest_fundamental("AAA", as_of=pd.Timestamp("2024-01-02")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_panel.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**

```python
# src/data/factor_panel.py
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd

@dataclass
class FactorPanel:
    prices: dict[str, pd.DataFrame]                 # symbol -> OHLCV indexed by DatetimeIndex
    fundamentals: dict[str, pd.DataFrame] = field(default_factory=dict)  # cols incl ann_date,end_date
    moneyflow: dict[str, pd.DataFrame] = field(default_factory=dict)     # indexed by date

    @property
    def symbols(self) -> list[str]:
        return sorted(self.prices.keys())

    @property
    def trading_dates(self) -> pd.DatetimeIndex:
        idx = None
        for df in self.prices.values():
            idx = df.index if idx is None else idx.union(df.index)
        return pd.DatetimeIndex([]) if idx is None else idx.sort_values()

    def history(self, symbol: str, as_of: pd.Timestamp) -> pd.DataFrame:
        df = self.prices.get(symbol)
        if df is None:
            return pd.DataFrame()
        return df.loc[df.index <= pd.Timestamp(as_of)]

    def latest_fundamental(self, symbol: str, as_of: pd.Timestamp) -> pd.Series | None:
        df = self.fundamentals.get(symbol)
        if df is None or df.empty:
            return None
        visible = df.loc[pd.to_datetime(df["ann_date"]) <= pd.Timestamp(as_of)]
        if visible.empty:
            return None
        return visible.sort_values("ann_date").iloc[-1]

    def moneyflow_history(self, symbol: str, as_of: pd.Timestamp) -> pd.DataFrame:
        df = self.moneyflow.get(symbol)
        if df is None:
            return pd.DataFrame()
        return df.loc[df.index <= pd.Timestamp(as_of)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_panel.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/data/factor_panel.py tests/unit/test_factor_panel.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): FactorPanel point-in-time data container"
```

---

### Task 3: Price-academic factors (no new data)

**Files:**
- Create: `src/analytics/factors/price.py`
- Test: `tests/unit/test_price_factors.py`

Factors: `LowVolatilityFactor` (−realized vol of daily returns over 60d), `TurnoverReversalFactor` (−avg(volume/…) proxy → use −20d avg turnover via volume), `MomentumFactor` (12−1 month: return from t−252 to t−21), `ShortReversalFactor` (−5d return). Each `compute(panel, as_of)` slices to ≤ as_of.

- [ ] **Step 1: Write the failing test (point-in-time + sign correctness)**

```python
# tests/unit/test_price_factors.py
import numpy as np, pandas as pd
from src.data.factor_panel import FactorPanel
from src.analytics.factors.price import LowVolatilityFactor, MomentumFactor, ShortReversalFactor

def _series(dates, closes, vol=1_000_000):
    return pd.DataFrame({"open":closes,"high":closes,"low":closes,"close":closes,
                         "volume":[vol]*len(closes)}, index=pd.DatetimeIndex(dates))

def test_low_vol_factor_ranks_calmer_symbol_higher():
    dates = pd.bdate_range("2023-01-01", periods=120)
    calm = _series(dates, list(np.linspace(10, 11, 120)))           # tiny moves
    wild = _series(dates, list(10 + np.sin(np.arange(120))*3))      # big swings
    panel = FactorPanel(prices={"CALM": calm, "WILD": wild})
    f = LowVolatilityFactor()
    vals = f.compute(panel, as_of=dates[-1])
    assert vals["CALM"] > vals["WILD"]   # low-vol factor (higher = calmer)

def test_factor_is_point_in_time():
    dates = pd.bdate_range("2023-01-01", periods=120)
    closes = list(np.linspace(10, 11, 120))
    panel = FactorPanel(prices={"AAA": _series(dates, closes)})
    f = LowVolatilityFactor()
    base = f.compute(panel, as_of=dates[80])
    # inject an extreme spike AFTER as_of; factor at as_of must not change
    closes2 = closes[:]; closes2[100] = 999.0
    panel2 = FactorPanel(prices={"AAA": _series(dates, closes2)})
    after = f.compute(panel2, as_of=dates[80])
    assert abs(base["AAA"] - after["AAA"]) < 1e-9

def test_momentum_positive_for_uptrend():
    dates = pd.bdate_range("2022-01-01", periods=300)
    panel = FactorPanel(prices={"UP": _series(dates, list(np.linspace(10, 30, 300)))})
    f = MomentumFactor()
    assert f.compute(panel, as_of=dates[-1])["UP"] > 0
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_price_factors.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

```python
# src/analytics/factors/price.py
from __future__ import annotations
import numpy as np, pandas as pd
from src.data.factor_panel import FactorPanel

class LowVolatilityFactor:
    name = "low_volatility"; direction = 1
    def __init__(self, window: int = 60): self.window = window
    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window + 1: continue
            rets = h["close"].pct_change().dropna().iloc[-self.window:]
            vol = rets.std(ddof=0)
            if np.isfinite(vol): out[sym] = -float(vol)   # higher = calmer
        return pd.Series(out, dtype=float)

class MomentumFactor:
    name = "momentum_12_1"; direction = 1
    def __init__(self, lookback: int = 252, gap: int = 21): self.lookback, self.gap = lookback, gap
    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.lookback + 1: continue
            c = h["close"]
            out[sym] = float(c.iloc[-self.gap] / c.iloc[-self.lookback] - 1.0)
        return pd.Series(out, dtype=float)

class ShortReversalFactor:
    name = "short_reversal"; direction = 1
    def __init__(self, window: int = 5): self.window = window
    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window + 1: continue
            c = h["close"]
            out[sym] = -float(c.iloc[-1] / c.iloc[-self.window - 1] - 1.0)  # higher = more oversold
        return pd.Series(out, dtype=float)

class TurnoverReversalFactor:
    name = "turnover_reversal"; direction = 1
    def __init__(self, window: int = 20): self.window = window
    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window: continue
            out[sym] = -float(h["volume"].iloc[-self.window:].mean())  # higher = less crowded
        return pd.Series(out, dtype=float)

ALL_PRICE_FACTORS = [LowVolatilityFactor(), MomentumFactor(), ShortReversalFactor(), TurnoverReversalFactor()]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_price_factors.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analytics/factors/price.py tests/unit/test_price_factors.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): price-academic factors (lowvol/momentum/reversal/turnover)"
```

---

### Task 4: IC evaluation engine

**Files:**
- Create: `src/analytics/factors/evaluation.py`
- Test: `tests/unit/test_factor_evaluation.py`

Computes, for a factor over a list of rebalance dates: cross-sectional Spearman rank IC per date (factor vs forward return), mean IC, ICIR (mean/std), OOS (later 30%) mean IC, and yearly IC. Forward return is strictly `> as_of`.

- [ ] **Step 1: Write the failing test (synthetic known relationship)**

```python
# tests/unit/test_factor_evaluation.py
import numpy as np, pandas as pd
from src.data.factor_panel import FactorPanel
from src.analytics.factors.evaluation import forward_returns, factor_ic_series, evaluate_factor

class _ConstFactor:
    name = "fake"; direction = 1
    def __init__(self, values_by_date): self.v = values_by_date
    def compute(self, panel, as_of): return self.v[pd.Timestamp(as_of)]

def _panel_with_relationship(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=80)
    syms = [f"S{i}" for i in range(20)]
    prices = {}
    factor_by_date = {}
    horizon = 5
    # assign each symbol a hidden 'quality' that drives BOTH its factor value and its forward return
    quality = {s: rng.normal() for s in syms}
    for s in syms:
        # forward return correlated with quality → cumulative price path
        steps = rng.normal(quality[s]*0.002, 0.01, len(dates))
        closes = 10*np.exp(np.cumsum(steps))
        prices[s] = pd.DataFrame({"open":closes,"high":closes,"low":closes,"close":closes,
                                  "volume":[1e6]*len(dates)}, index=dates)
    for d in dates[:-horizon]:
        factor_by_date[pd.Timestamp(d)] = pd.Series({s: quality[s] for s in syms})
    return FactorPanel(prices=prices), dates[:-horizon], _ConstFactor(factor_by_date), horizon

def test_forward_returns_are_strictly_future():
    panel, dates, _, horizon = _panel_with_relationship()
    fr = forward_returns(panel, dates[0], horizon)
    # forward return uses close[as_of+horizon]/close[as_of]-1; computable + finite
    assert fr.notna().any()

def test_ic_is_positive_for_predictive_factor():
    panel, dates, factor, horizon = _panel_with_relationship()
    ic = factor_ic_series(factor, panel, dates, horizon)
    assert ic.mean() > 0.1   # strong synthetic relationship → clearly positive IC

def test_ic_near_zero_for_random_factor():
    panel, dates, _, horizon = _panel_with_relationship(seed=1)
    rng = np.random.default_rng(99)
    syms = panel.symbols
    rand = _ConstFactor({pd.Timestamp(d): pd.Series({s: rng.normal() for s in syms}) for d in dates})
    ic = factor_ic_series(rand, panel, dates, horizon)
    assert abs(ic.mean()) < 0.1

def test_evaluate_factor_reports_oos_and_icir():
    panel, dates, factor, horizon = _panel_with_relationship()
    rep = evaluate_factor(factor, panel, dates, horizon, train_frac=0.7)
    assert rep["mean_ic"] > 0.1
    assert rep["oos_mean_ic"] > 0.0
    assert "icir" in rep and "yearly_ic" in rep and "n_dates" in rep
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_evaluation.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

```python
# src/analytics/factors/evaluation.py
from __future__ import annotations
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from src.data.factor_panel import FactorPanel

def forward_returns(panel: FactorPanel, as_of, horizon: int) -> pd.Series:
    as_of = pd.Timestamp(as_of)
    out = {}
    for sym in panel.symbols:
        df = panel.prices[sym]
        pos = df.index.searchsorted(as_of)
        if pos >= len(df) or df.index[pos] != as_of:  # as_of must be a trading day for this symbol
            continue
        fwd = pos + horizon
        if fwd >= len(df):
            continue
        c0, c1 = df["close"].iloc[pos], df["close"].iloc[fwd]
        if c0 and np.isfinite(c0) and np.isfinite(c1):
            out[sym] = float(c1 / c0 - 1.0)
    return pd.Series(out, dtype=float)

def _rank_ic(factor_vals: pd.Series, fwd: pd.Series, direction: int) -> float:
    common = factor_vals.dropna().index.intersection(fwd.dropna().index)
    if len(common) < 5:
        return np.nan
    f = factor_vals.loc[common].astype(float) * direction
    r = fwd.loc[common].astype(float)
    rho, _ = spearmanr(f, r)
    return float(rho) if np.isfinite(rho) else np.nan

def factor_ic_series(factor, panel: FactorPanel, dates, horizon: int) -> pd.Series:
    direction = getattr(factor, "direction", 1)
    rows = {}
    for d in dates:
        d = pd.Timestamp(d)
        fvals = factor.compute(panel, d)
        fwd = forward_returns(panel, d, horizon)
        ic = _rank_ic(fvals, fwd, direction)
        if np.isfinite(ic):
            rows[d] = ic
    return pd.Series(rows, dtype=float).sort_index()

def evaluate_factor(factor, panel: FactorPanel, dates, horizon: int, train_frac: float = 0.7) -> dict:
    ic = factor_ic_series(factor, panel, dates, horizon)
    if ic.empty:
        return {"name": factor.name, "n_dates": 0, "mean_ic": np.nan, "icir": np.nan,
                "oos_mean_ic": np.nan, "yearly_ic": {}, "passes": False}
    split = int(len(ic) * train_frac)
    oos = ic.iloc[split:]
    icir = float(ic.mean() / ic.std(ddof=0)) if ic.std(ddof=0) else np.nan
    yearly = {int(y): float(v.mean()) for y, v in ic.groupby(ic.index.year)}
    mean_ic, oos_ic = float(ic.mean()), float(oos.mean()) if len(oos) else np.nan
    signs = [v for v in yearly.values()]
    stable = len(signs) >= 2 and (all(s >= 0 for s in signs) or all(s <= 0 for s in signs))
    passes = bool(np.isfinite(oos_ic) and abs(oos_ic) >= 0.03 and np.isfinite(icir) and icir > 0 and stable)
    return {"name": factor.name, "n_dates": int(len(ic)), "mean_ic": mean_ic, "icir": icir,
            "oos_mean_ic": oos_ic, "yearly_ic": yearly, "sign_stable": stable, "passes": passes}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_evaluation.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analytics/factors/evaluation.py tests/unit/test_factor_evaluation.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): IC evaluation engine (rank IC / ICIR / OOS / yearly)"
```

---

### Task 5: Tushare provider — historical fina_indicator + moneyflow

**Files:**
- Modify: `src/data/providers/tushare_provider.py`
- Test: `tests/unit/test_tushare_factor_endpoints.py`

Add `get_financial_indicators(symbol, start, end)` (calls `pro.fina_indicator`, returns DataFrame incl. `ann_date`, `end_date`, and the indicator columns) and `get_moneyflow(symbol, start, end)` (`pro.moneyflow`). Mock the pro client; blank `TUSHARE_TOKEN` + reset class circuit-breaker state in setup (per repo tushare-test-isolation convention).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tushare_factor_endpoints.py
import pandas as pd
from unittest.mock import MagicMock
import src.data.providers.tushare_provider as tp

def _provider_with_mock(monkeypatch, df):
    monkeypatch.setenv("TUSHARE_TOKEN", "")          # isolation
    p = tp.TushareProvider()
    fake_pro = MagicMock()
    fake_pro.fina_indicator.return_value = df
    fake_pro.moneyflow.return_value = df
    monkeypatch.setattr(p, "_get_pro", lambda: fake_pro, raising=False)
    p.clear_cache() if hasattr(p, "clear_cache") else None
    return p, fake_pro

def test_get_financial_indicators_keeps_ann_date(monkeypatch):
    df = pd.DataFrame({"ts_code":["600000.SH"],"ann_date":["20240101"],"end_date":["20231231"],
                       "roe":[12.0],"netprofit_yoy":[5.0]})
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_financial_indicators("600000.SH", "20230101", "20240101")
    assert "ann_date" in out.columns and "roe" in out.columns
    assert len(out) == 1

def test_get_moneyflow_returns_frame(monkeypatch):
    df = pd.DataFrame({"ts_code":["600000.SH"],"trade_date":["20240101"],
                       "net_mf_amount":[1234.0],"buy_lg_amount":[50.0]})
    p, _ = _provider_with_mock(monkeypatch, df)
    out = p.get_moneyflow("600000.SH", "20230101", "20240101")
    assert "net_mf_amount" in out.columns
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_tushare_factor_endpoints.py -q`
Expected: FAIL (methods don't exist)

- [ ] **Step 3: Implement** (add methods near the existing `get_stock_financial_data`; reuse the existing pro-client accessor + the TTL cache/throttle helpers added in PR #101; match the symbol-normalization used by the existing methods)

```python
# in src/data/providers/tushare_provider.py (TushareProvider)
def get_financial_indicators(self, symbol: str, start: str, end: str) -> "pd.DataFrame":
    """Historical fina_indicator with ann_date (point-in-time). symbol like '600000.SH'."""
    import pandas as pd
    pro = self._get_pro()  # use the same accessor the other methods use
    if pro is None:
        return pd.DataFrame()
    if not self._throttle_acquire():           # reuse PR #101 rate-limit helper name
        return pd.DataFrame()
    df = pro.fina_indicator(ts_code=self._to_ts_code(symbol), start_date=start, end_date=end)
    return df if df is not None else pd.DataFrame()

def get_moneyflow(self, symbol: str, start: str, end: str) -> "pd.DataFrame":
    import pandas as pd
    pro = self._get_pro()
    if pro is None:
        return pd.DataFrame()
    if not self._throttle_acquire():
        return pd.DataFrame()
    df = pro.moneyflow(ts_code=self._to_ts_code(symbol), start_date=start, end_date=end)
    return df if df is not None else pd.DataFrame()
```

> If the existing provider uses different helper names (`_get_pro`, `_to_ts_code`, `_throttle_acquire`), align to the real ones — read the file first and reuse whatever `get_stock_financial_data` already uses. The test stubs `_get_pro`, so keep that name or adjust the test to match.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_tushare_factor_endpoints.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/data/providers/tushare_provider.py tests/unit/test_tushare_factor_endpoints.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(tushare): historical fina_indicator + moneyflow for factors"
```

---

### Task 6: Panel builder (live fetch + local cache)

**Files:**
- Modify: `src/data/factor_panel.py` (add `build_panel`)
- Test: `tests/unit/test_factor_panel_build.py`
- Ensure cache dir ignored: confirm `data/_factor_cache/` is under an already-gitignored path (`data/` patterns) or add to `.gitignore`.

`build_panel(symbols, start, end, provider, cache_dir)` fetches per-symbol OHLCV history (via `provider.get_historical_data`), fina_indicator, moneyflow; writes each to parquet in `cache_dir`; on rerun loads from cache. Returns a `FactorPanel`. Test with a fake provider (no network).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_factor_panel_build.py
import pandas as pd
from src.data.factor_panel import FactorPanel, build_panel

class _FakeProvider:
    def get_historical_data(self, symbol, start, end, interval="1d"):
        dates = pd.bdate_range("2024-01-01", periods=10)
        c = [10+i for i in range(10)]
        return pd.DataFrame({"open":c,"high":c,"low":c,"close":c,"volume":[1e6]*10}, index=dates)
    def get_financial_indicators(self, symbol, start, end):
        return pd.DataFrame({"ann_date":["20240103"],"end_date":["20231231"],"roe":[11.0]})
    def get_moneyflow(self, symbol, start, end):
        d = pd.bdate_range("2024-01-01", periods=10)
        return pd.DataFrame({"trade_date":[x.strftime("%Y%m%d") for x in d],"net_mf_amount":[100]*10})

def test_build_panel_assembles_and_caches(tmp_path):
    prov = _FakeProvider()
    panel = build_panel(["AAA","BBB"], "20240101", "20240115", prov, cache_dir=tmp_path)
    assert isinstance(panel, FactorPanel)
    assert set(panel.symbols) == {"AAA","BBB"}
    assert not panel.history("AAA", pd.Timestamp("2024-01-05")).empty
    assert panel.latest_fundamental("AAA", pd.Timestamp("2024-01-04"))["roe"] == 11.0
    # cache files written
    assert any(tmp_path.rglob("*.parquet"))

def test_build_panel_uses_cache_on_rerun(tmp_path):
    calls = {"n": 0}
    prov = _FakeProvider()
    orig = prov.get_historical_data
    def counted(*a, **k):
        calls["n"] += 1; return orig(*a, **k)
    prov.get_historical_data = counted
    build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)
    first = calls["n"]
    build_panel(["AAA"], "20240101", "20240115", prov, cache_dir=tmp_path)  # rerun
    assert calls["n"] == first   # no extra fetch; served from cache
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_panel_build.py -q`
Expected: FAIL (`build_panel` not defined)

- [ ] **Step 3: Implement** (append to `src/data/factor_panel.py`)

```python
import pathlib

def _cache_load(path: pathlib.Path):
    import pandas as pd
    return pd.read_parquet(path) if path.exists() else None

def build_panel(symbols, start, end, provider, cache_dir) -> FactorPanel:
    import pandas as pd
    cache_dir = pathlib.Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    prices, fundamentals, moneyflow = {}, {}, {}
    for sym in symbols:
        px_path = cache_dir / f"{sym}_px.parquet"
        px = _cache_load(px_path)
        if px is None:
            px = provider.get_historical_data(sym, start, end)
            if px is not None and not px.empty:
                px.to_parquet(px_path)
        if px is None or px.empty:
            continue
        px.index = pd.DatetimeIndex(px.index)
        prices[sym] = px

        fa_path = cache_dir / f"{sym}_fa.parquet"
        fa = _cache_load(fa_path)
        if fa is None:
            fa = provider.get_financial_indicators(sym, start, end)
            if fa is not None and not fa.empty:
                fa.to_parquet(fa_path)
        if fa is not None and not fa.empty:
            fa = fa.copy(); fa["ann_date"] = pd.to_datetime(fa["ann_date"].astype(str))
            fundamentals[sym] = fa

        mf_path = cache_dir / f"{sym}_mf.parquet"
        mf = _cache_load(mf_path)
        if mf is None:
            mf = provider.get_moneyflow(sym, start, end)
            if mf is not None and not mf.empty:
                mf.to_parquet(mf_path)
        if mf is not None and not mf.empty:
            mf = mf.copy()
            mf.index = pd.DatetimeIndex(pd.to_datetime(mf["trade_date"].astype(str)))
            moneyflow[sym] = mf.sort_index()
    return FactorPanel(prices=prices, fundamentals=fundamentals, moneyflow=moneyflow)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_factor_panel_build.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
echo "data/_factor_cache/" >> .gitignore   # only if not already covered
git add src/data/factor_panel.py tests/unit/test_factor_panel_build.py .gitignore
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): panel builder with local parquet cache"
```

---

### Task 7: Fundamental + moneyflow factors

**Files:**
- Create: `src/analytics/factors/fundamental.py`
- Create: `src/analytics/factors/moneyflow.py`
- Test: `tests/unit/test_fundamental_moneyflow_factors.py`

Fundamental factors read `panel.latest_fundamental(sym, as_of)` (already ann_date-gated): `ROEFactor` (roe), `EarningsYieldFactor` (net profit / market cap → use `1/pe` proxy if pe present, else roe*bp), `RevenueGrowthFactor` (or_yoy), `ProfitGrowthFactor` (netprofit_yoy). Moneyflow factor reads `panel.moneyflow_history` trailing N days net inflow.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fundamental_moneyflow_factors.py
import pandas as pd
from src.data.factor_panel import FactorPanel
from src.analytics.factors.fundamental import ROEFactor, ProfitGrowthFactor
from src.analytics.factors.moneyflow import NetInflowFactor

def _px(dates): 
    c=[10+i for i in range(len(dates))]
    return pd.DataFrame({"open":c,"high":c,"low":c,"close":c,"volume":[1e6]*len(dates)}, index=dates)

def test_roe_factor_uses_ann_date_gated_value():
    dates = pd.bdate_range("2024-01-01", periods=10)
    fa = pd.DataFrame({"ann_date":pd.to_datetime(["2024-01-03"]),"end_date":pd.to_datetime(["2023-12-31"]),
                       "roe":[15.0]})
    fa2 = pd.DataFrame({"ann_date":pd.to_datetime(["2024-01-03"]),"end_date":pd.to_datetime(["2023-12-31"]),
                        "roe":[5.0]})
    panel = FactorPanel(prices={"HI":_px(dates),"LO":_px(dates)}, fundamentals={"HI":fa,"LO":fa2})
    vals = ROEFactor().compute(panel, as_of=dates[5])
    assert vals["HI"] > vals["LO"]

def test_fundamental_factor_invisible_before_ann_date():
    dates = pd.bdate_range("2024-01-01", periods=10)
    fa = pd.DataFrame({"ann_date":pd.to_datetime(["2024-01-08"]),"end_date":pd.to_datetime(["2023-12-31"]),
                       "roe":[15.0]})
    panel = FactorPanel(prices={"HI":_px(dates)}, fundamentals={"HI":fa})
    vals = ROEFactor().compute(panel, as_of=dates[2])  # before 2024-01-08 announcement
    assert "HI" not in vals.index   # not yet visible → excluded

def test_net_inflow_factor_ranks_inflow_higher():
    dates = pd.bdate_range("2024-01-01", periods=10)
    mf_in = pd.DataFrame({"net_mf_amount":[100.0]*10}, index=dates)
    mf_out = pd.DataFrame({"net_mf_amount":[-100.0]*10}, index=dates)
    panel = FactorPanel(prices={"IN":_px(dates),"OUT":_px(dates)}, moneyflow={"IN":mf_in,"OUT":mf_out})
    vals = NetInflowFactor(window=5).compute(panel, as_of=dates[-1])
    assert vals["IN"] > vals["OUT"]
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_fundamental_moneyflow_factors.py -q`
Expected: FAIL (modules not found)

- [ ] **Step 3: Implement**

```python
# src/analytics/factors/fundamental.py
from __future__ import annotations
import numpy as np, pandas as pd
from src.data.factor_panel import FactorPanel

def _fundamental_factor(panel, as_of, col, direction):
    out = {}
    for sym in panel.symbols:
        row = panel.latest_fundamental(sym, as_of)
        if row is None or col not in row or pd.isna(row[col]):
            continue
        out[sym] = float(row[col])
    return pd.Series(out, dtype=float)

class ROEFactor:
    name="roe"; direction=1
    def compute(self, panel, as_of): return _fundamental_factor(panel, as_of, "roe", 1)
class ProfitGrowthFactor:
    name="profit_growth"; direction=1
    def compute(self, panel, as_of): return _fundamental_factor(panel, as_of, "netprofit_yoy", 1)
class RevenueGrowthFactor:
    name="revenue_growth"; direction=1
    def compute(self, panel, as_of): return _fundamental_factor(panel, as_of, "or_yoy", 1)

ALL_FUNDAMENTAL_FACTORS = [ROEFactor(), ProfitGrowthFactor(), RevenueGrowthFactor()]

# src/analytics/factors/moneyflow.py
from __future__ import annotations
import numpy as np, pandas as pd
from src.data.factor_panel import FactorPanel

class NetInflowFactor:
    name="net_inflow"; direction=1
    def __init__(self, window:int=5): self.window=window
    def compute(self, panel, as_of):
        out={}
        for sym in panel.symbols:
            mf = panel.moneyflow_history(sym, as_of)
            if mf.empty or "net_mf_amount" not in mf.columns: continue
            v = mf["net_mf_amount"].iloc[-self.window:].mean()
            if np.isfinite(v): out[sym]=float(v)
        return pd.Series(out, dtype=float)

ALL_MONEYFLOW_FACTORS = [NetInflowFactor()]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_fundamental_moneyflow_factors.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analytics/factors/fundamental.py src/analytics/factors/moneyflow.py tests/unit/test_fundamental_moneyflow_factors.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): fundamental (ann_date-gated) + moneyflow factors"
```

---

### Task 8: Scorecard runner

**Files:**
- Create: `scripts/run_factor_scorecard.py`
- Test: `tests/unit/test_run_factor_scorecard.py` (tests the pure assemble/report functions, not the live run)

The script: parse CLI (universe file or default list, start/end, horizon, monthly rebalance dates), `build_panel`, evaluate every factor (`price + fundamental + moneyflow`), write `docs/factor_scorecard.md` + `.json`. Factor the report-building into a pure function so it's testable offline.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_factor_scorecard.py
import importlib
def test_build_scorecard_table_and_monthly_dates():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports = [
        {"name":"roe","n_dates":40,"mean_ic":0.04,"icir":0.3,"oos_mean_ic":0.035,"sign_stable":True,"passes":True,"yearly_ic":{2023:0.04}},
        {"name":"random","n_dates":40,"mean_ic":0.0,"icir":0.0,"oos_mean_ic":0.0,"sign_stable":False,"passes":False,"yearly_ic":{2023:0.0}},
    ]
    md = mod.build_scorecard_markdown(reports)
    assert "roe" in md and "PASS" in md and "FAIL" in md
    import pandas as pd
    dates = mod.monthly_rebalance_dates(pd.bdate_range("2023-01-01","2023-06-30"))
    assert len(dates) >= 5 and all(isinstance(d, pd.Timestamp) for d in dates)
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_run_factor_scorecard.py -q`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement** (the pure helpers + a `main()` guarded by `if __name__ == "__main__"`)

```python
# scripts/run_factor_scorecard.py
from __future__ import annotations
import argparse, json, sys, pathlib
import pandas as pd
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_UNIVERSE = ["600519.SH","601398.SH","000858.SZ","300750.SZ","600036.SH","000333.SZ",
                    "601318.SH","600276.SH","000651.SZ","002415.SZ","600900.SH","601012.SH",
                    # ... ~50 diversified liquid names; survivorship caveat noted in scorecard
                    ]

def monthly_rebalance_dates(trading_dates) -> list:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]

def build_scorecard_markdown(reports: list[dict]) -> str:
    lines = ["# 因子记分卡 (Phase 1)", "",
             "> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。", "",
             "| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |",
             "|---|--:|--:|--:|--:|:--:|:--:|"]
    for r in sorted(reports, key=lambda x: (x.get("oos_mean_ic") or -9), reverse=True):
        lines.append("| {name} | {n_dates} | {mean_ic:.4f} | {icir:.3f} | {oos_mean_ic:.4f} | {ss} | {v} |".format(
            ss="✓" if r.get("sign_stable") else "✗", v="PASS" if r.get("passes") else "FAIL", **{k:(r.get(k) if r.get(k) is not None else float('nan')) for k in ["name","n_dates","mean_ic","icir","oos_mean_ic"]}))
    passed = [r["name"] for r in reports if r.get("passes")]
    lines += ["", f"**过关因子:** {', '.join(passed) if passed else '无 —— 不启动 Phase 2(诚实门)'}"]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20180101"); ap.add_argument("--end", default="20240101")
    ap.add_argument("--horizon", type=int, default=20); ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()
    from dotenv import load_dotenv; load_dotenv(PROJECT_ROOT/".env")
    from src.data.providers.tushare_provider import TushareProvider
    from src.data.factor_panel import build_panel
    from src.analytics.factors.evaluation import evaluate_factor
    from src.analytics.factors.price import ALL_PRICE_FACTORS
    from src.analytics.factors.fundamental import ALL_FUNDAMENTAL_FACTORS
    from src.analytics.factors.moneyflow import ALL_MONEYFLOW_FACTORS
    panel = build_panel(DEFAULT_UNIVERSE, args.start, args.end, TushareProvider(),
                        cache_dir=PROJECT_ROOT/"data/_factor_cache")
    dates = monthly_rebalance_dates(panel.trading_dates)
    dates = [d for d in dates if len(panel.history(panel.symbols[0], d)) >= 252][:-1]  # need history + a future bar
    factors = ALL_PRICE_FACTORS + ALL_FUNDAMENTAL_FACTORS + ALL_MONEYFLOW_FACTORS
    reports = [evaluate_factor(f, panel, dates, args.horizon, args.train_frac) for f in factors]
    (PROJECT_ROOT/"docs/factor_scorecard.md").write_text(build_scorecard_markdown(reports), encoding="utf-8")
    (PROJECT_ROOT/"docs/factor_scorecard.json").write_text(json.dumps(reports, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    print(build_scorecard_markdown(reports))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -o addopts="" tests/unit/test_run_factor_scorecard.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_factor_scorecard.py tests/unit/test_run_factor_scorecard.py
.venv/bin/python scripts/check_ruff_baseline.py
git commit -m "feat(factors): scorecard runner (offline-tested pure helpers)"
```

---

### Task 9: Full-suite verification + real scorecard run

- [ ] **Step 1:** Run the whole backend suite to confirm nothing regressed.

Run: `.venv/bin/python -m pytest -o addopts="" tests/ -q`
Expected: all prior tests still pass + the new factor tests (baseline was 1566 passed, 2 skipped → now higher).

- [ ] **Step 2:** Ruff gate.

Run: `.venv/bin/python scripts/check_ruff_baseline.py`
Expected: `new=0`.

- [ ] **Step 3: Run the REAL scorecard (network — Tushare).** Expand `DEFAULT_UNIVERSE` to ~50 diversified liquid names first.

Run: `.venv/bin/python scripts/run_factor_scorecard.py --start 20180101 --end 20240101 --horizon 20`
Expected: prints the scorecard; writes `docs/factor_scorecard.md` + `.json`. If Tushare rate-limits, the panel cache lets you re-run to resume.

- [ ] **Step 4: Commit the scorecard** (the research deliverable).

```bash
git add docs/factor_scorecard.md docs/factor_scorecard.json
git commit -m "docs(factors): Phase 1 factor IC scorecard"
```

- [ ] **Step 5: Report verdict.** Summarize which factors PASS the IC gate. This is the input to the Phase 2 (integration) decision — do NOT start Phase 2 here.

---

## Self-Review

**Spec coverage:** ✅ point-in-time factor library (Tasks 1,3,7) · ann_date gating (Task 2,7) · moneyflow (Tasks 5,7) · price-academic (Task 3) · panel builder + cache (Tasks 2,6) · IC engine generalizing the calibration harness (Task 4) · scorecard runner (Task 8) · honesty gate (Task 8 "无 → 不启动 Phase 2", Task 9 Step 5) · does NOT touch scorer/frontend (no such task) · offline-testable (all tests use synthetic panels / mocked provider).

**Placeholder scan:** the `DEFAULT_UNIVERSE` has a `# ...` — Task 9 Step 3 explicitly instructs expanding to ~50 names before the real run (not a code-path placeholder; the helpers are fully implemented and tested with the partial list). All other steps contain real code + real commands.

**Type consistency:** `Factor.compute(panel, as_of) -> pd.Series` consistent across price/fundamental/moneyflow. `FactorPanel` methods (`history`, `latest_fundamental`, `moneyflow_history`, `symbols`, `trading_dates`) used consistently in Tasks 2,3,4,6,7. `evaluate_factor(...) -> dict` keys (`name,n_dates,mean_ic,icir,oos_mean_ic,yearly_ic,sign_stable,passes`) consistent between Task 4 and the Task 8 report builder. Provider method names (`get_financial_indicators`, `get_moneyflow`, `get_historical_data`) consistent between Tasks 5,6,8.

**Note for implementer:** the unicode minus `−` in Task 1's code block is only to survive markdown; type ASCII `-`. Before Task 5, READ `tushare_provider.py` and align helper names (`_get_pro`/`_to_ts_code`/throttle) to the real ones the existing methods use.
