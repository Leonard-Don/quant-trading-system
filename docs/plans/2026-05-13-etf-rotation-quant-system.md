# ETF Rotation Quant System Implementation Plan

> **For Hermes:** Use worktree-based Claude/Codex CLI agents to implement this plan task-by-task. The user explicitly requested no mobile/Android work in this wave and asked to use Claude + Codex multi-window with Claude used more heavily.

**Goal:** Build a first non-trading, daily ETF rotation system for Leonard's current ETF portfolio: fetch/normalize ETF market data, score each ETF, apply portfolio risk caps, backtest target-weight rotation, and emit daily manual trade suggestions.

**Architecture:** Implement the system inside `quant-trading-system` as pure Python modules plus scripts. Keep brokerage execution manual: scripts produce target weights and suggested share deltas only. The 512400 specialist project remains an external overlay source; this repo should expose hooks/fields for that overlay but not duplicate all 512400 commodity logic in v1.

**Tech Stack:** Python 3.9+, pandas/numpy, existing `src/backtest/PortfolioBacktester`, pytest unit tests, script entry points under `scripts/`.

---

## Current portfolio seed

Use this default seed for examples/tests only; it must be configurable and not hard-coded into core library logic:

- `159985` 豆粕ETF华夏, category `commodity_event`, current weight about 7.43%, max 8%, default target 5%.
- `512400` 有色金属ETF南方, category `nonferrous`, current weight about 32.43%, max 25%, default target 22%, supports specialist overlay/veto.
- `510300` 沪深300ETF华泰柏瑞, category `a_share_core`, current weight about 21.94%, max 35%, default target 28%.
- `518680` 金ETF富国, category `gold_hedge`, current weight about 32.05%, max 25%, default target 20%.
- `513130` 恒生科技ETF华泰柏瑞, category `hk_tech_satellite`, current weight about 6.16%, max 12%, default target 7%.
- Cash floor: 10%; preferred v1 example cash target: 18%.

## Design constraints

- No Android/mobile work in this wave.
- No broker API and no auto-ordering.
- No changes to `/Users/leonardodon/ETF 512400` dirty market-data files.
- Use clean worktrees and keep the base checkout's untracked `outputs/` untouched.
- Do not override Codex model/effort; let Codex use configured defaults.
- Claude Code should use Opus + max effort for writer/review tasks.
- Every module needs focused unit tests.

---

### Task 1: Core ETF scoring strategy

**Objective:** Add a pure Python scoring/target-weight module that converts ETF price history plus optional overlays into target weights.

**Files:**
- Create: `src/strategy/etf_rotation_strategy.py`
- Create: `tests/unit/test_etf_rotation_strategy.py`

**Requirements:**
- Define dataclasses such as `EtfAssetConfig`, `EtfSignal`, `EtfOverlay`, `EtfRotationConfig`.
- Compute features from close prices: latest price, MA20, MA60, 5/20/60-day returns, 60-day high drawdown, 60-day annualized volatility.
- Score trend/momentum/risk/premium.
- Convert score to raw target weight, then apply per-asset min/max caps.
- Support `overlay.max_weight`, `overlay.block_new_buys`, `overlay.reason` so 512400 specialist signals can cap or veto adding.
- Provide a `generate_signals(price_matrix)` method compatible with `PortfolioBacktester`: return a target-weight DataFrame indexed like the price matrix.
- Keep cash implicit: sum of ETF weights may be less than 1.

**Focused tests:**
- Strong asset above MA20/MA60 receives a higher target than weak asset below MA60.
- `overlay.max_weight` caps 512400 target.
- `block_new_buys=True` prevents increasing above current weight when current weights are provided.
- Gross ETF weights do not exceed configured gross cap after normalization.

**Verification command:**
`python3 -m pytest tests/unit/test_etf_rotation_strategy.py -q`

---

### Task 2: ETF market data and portfolio model

**Objective:** Add reusable data/portfolio helpers for ETF universe config, Sina/Eastmoney/Tiantian quote parsing, current holdings, and suggested share deltas.

**Files:**
- Create: `src/data/etf_rotation.py`
- Create: `tests/unit/test_etf_rotation_data.py`

**Requirements:**
- Define `EtfHolding`, `EtfQuote`, `EtfUniverseItem`, `EtfTradeSuggestion` dataclasses.
- Provide default universe for the five ETFs above.
- Provide pure parsing helpers for Sina ETF quote strings and fundgz `jsonpgz(...)` responses; tests must not call the network.
- Provide `calculate_current_weights(holdings, total_asset)`.
- Provide `build_trade_suggestions(current_holdings, target_weights, quotes, total_asset, lot_size=100, threshold_weight=0.03)` returning manual buy/sell/hold suggestions.
- Round suggested shares to 100-share lots and skip tiny trades below threshold.
- Include premium/discount calculation when quote + estimated NAV are present.

**Focused tests:**
- Parse a Sina quote fixture for 510300/513130 shape correctly.
- Parse a fundgz fixture correctly.
- Current weights match the screenshot seed within tolerance.
- Trade suggestions for the sample target weights roughly produce: reduce 512400 and 518680, hold/reduce豆粕, add/hold 510300/513130 depending threshold.

**Verification command:**
`python3 -m pytest tests/unit/test_etf_rotation_data.py -q`

---

### Task 3: Portfolio risk rules

**Objective:** Add a pure portfolio risk policy that clamps target weights by single-asset caps, risk-bucket caps, cash floor, premium veto, and drawdown deleveraging.

**Files:**
- Create: `src/risk/etf_portfolio_rules.py`
- Create: `src/risk/__init__.py` if absent
- Create: `tests/unit/test_etf_portfolio_rules.py`

**Requirements:**
- Define `EtfRiskRuleConfig`, `EtfRiskDecision`, `EtfRiskAdjustment` dataclasses.
- Inputs: proposed target weights, current weights, asset category/bucket metadata, optional premium percentages, optional portfolio drawdown.
- Enforce: max single weight, commodity/resource bucket cap, minimum cash, QDII/commodity premium buy veto, drawdown gross exposure cuts.
- Return adjusted weights plus human-readable reasons.
- Default caps: single 30%, commodity/resource bucket 55%, cash floor 10%, qdii premium veto 2%, hard premium veto 5%.

**Focused tests:**
- Reduces combined commodity bucket from >70% to <=55%.
- Keeps cash >=10%.
- Premium veto prevents increasing 513130/159985 when premium is too high.
- Drawdown >8% reduces gross exposure.

**Verification command:**
`python3 -m pytest tests/unit/test_etf_portfolio_rules.py -q`

---

### Task 4: Daily signal and backtest scripts

**Objective:** Add CLI scripts that combine Tasks 1-3 to produce a JSON/text daily manual trade plan and a basic backtest harness.

**Files:**
- Create: `scripts/daily_etf_signal.py`
- Create: `scripts/backtest_etf_rotation.py`
- Create: `tests/unit/test_daily_etf_signal.py`

**Requirements:**
- `daily_etf_signal.py` should accept `--holdings-json`, `--quotes-json`, `--output json|text` and default to the screenshot seed if no holdings file is supplied.
- It should not auto-trade or call broker APIs.
- It should output current weights, target weights, adjusted weights, suggested lot-rounded buy/sell/hold actions, and risk reasons.
- `backtest_etf_rotation.py` should accept a local CSV price matrix and run `PortfolioBacktester` using `EtfRotationStrategy`.
- Tests use local fixtures and no network.

**Focused tests:**
- JSON output schema includes `current_weights`, `target_weights`, `suggestions`, `risk_reasons`.
- Text output states manual-only and no auto-ordering.
- Backtest script exposes a callable function for tests without shelling out.

**Verification command:**
`python3 -m pytest tests/unit/test_daily_etf_signal.py -q`

---

### Task 5: Integration gates

**Objective:** Validate the combined implementation and produce a concise run report.

**Commands:**
- `python3 -m pytest tests/unit/test_etf_rotation_strategy.py tests/unit/test_etf_rotation_data.py tests/unit/test_etf_portfolio_rules.py tests/unit/test_daily_etf_signal.py -q`
- `python3 scripts/daily_etf_signal.py --output text`
- `python3 scripts/daily_etf_signal.py --output json`
- `git diff --check`

**Acceptance:**
- All focused tests pass.
- Script output is deterministic from local defaults/fixtures.
- No mobile/Android files touched.
- No protected ETF 512400 repo files touched.

---

### Task 6 (added 2026-05-17): Historical backtest harness

**Objective:** Close the research loop by replaying the strategy against
arbitrary historical windows and producing structured performance metrics
— independent of whatever the live audit log happens to contain.

**Where it lives:**
- Core: `src/backtest/etf_rotation_backtest.py` (`EtfRotationBacktester`
  class + `BacktestReport` dataclass).
- CLI: `scripts/backtest_etf_rotation_strategy.py`
  (`--prices-csv / --start-date / --end-date / --enable-policy-signal /
  --output-md / --output-json`).
- HTTP: `POST /etf-rotation/backtest`, body
  `{period_start, period_end, enable_policy_signal_factor,
  rebalance_freq_days, initial_capital, strategy_config_overrides}`.

**When to use it vs the existing tools:**

| Tool | Question it answers |
|---|---|
| `EtfRotationBacktester` (new) | "Across this *closed* historical window, what would the strategy have done if I'd held its planned weights bar-to-bar?" |
| `PortfolioBacktester` via `scripts/backtest_etf_rotation.py` | Same, **plus** commission / slippage / max-turnover modelling. Use when you need a realistic post-cost estimate. |
| `walkforward_etf_rotation.py` | "Across many *rolling* windows, does the best in-sample config hold up out-of-sample?" — robustness/regime test, not a single-window backtest. |
| `compute_attribution` (live) | "On the actually-executed audit log, how much did `policy_signal_factor` contribute to realised P&L?" — production observability, not research. |

**v0.1 caveats** (deliberately exhaustive — surface them upstream when
quoting numbers):

- No transaction costs.
- No bid-ask spread / slippage.
- No market impact.
- Next-bar close fills only (single-bar look-ahead lag from the strategy
  itself is honoured).
- Equal-weight buy-and-hold benchmark — naive, not the index the strategy
  claims to beat.
- No survivorship-bias handling.
