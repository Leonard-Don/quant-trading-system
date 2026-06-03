# 更新日志

## Unreleased

### Removed

- feat(etf)!: remove the entire ETF rotation board. Deletes the
  `/etf-rotation/*` API surface, the front-end `?view=etf` dashboard and its
  tiles (`EtfRotationDashboard`, `EtfRegimeTile`, `EtfWalkforwardPanel`,
  `EtfPolicyFactorAttributionPanel`), the `src/backtest` ETF engines
  (`EtfRotationBacktester`, `EtfRotationWalkforwardAnalyzer`,
  `StrategyComparator`, the now-orphaned `ParameterOptimizer`), the
  `src/strategy` ETF family (rotation / mean-reversion / blend / regime
  classifier + recommender), the ETF data/risk helpers, the policy-factor
  attribution research module, and all ETF-only scripts, CLIs, fixtures, docs
  and tests. The public-summary exporter drops its `etf_rotation` /
  `regime_recommendation` sections.
- Also removed the now-orphaned transaction-cost model
  (`src/backtest/transaction_costs.py`): once the ETF backtest engines were
  deleted nothing consumed it anymore (it was only re-exported from the
  `src.backtest` package barrel).
- The generic statistical-falsification engine
  (`src/backtest/strategy_statistical_tests.py`) is **kept** — it still powers
  the generic `WalkForwardAnalyzer` statistical-power diagnostics exposed via
  the live `/backtest` walk-forward endpoint.

### Data

- data(industry): promote Tushare into the THS-first industry adapter as the
  fifth industry/leader source. Industry heat now keeps THS as the live primary
  source, uses AKShare for metadata, fills missing after-close money flow,
  market cap, turnover and leading-stock fields from Tushare `moneyflow_ind_ths`
  + `dc_index`, then falls through to Sina/Tencent fallbacks only where needed.
- data(tushare): add Tushare after-close fallbacks for industry money flow and
  heatmap data. `IndustryAnalyzer.analyze_money_flow()` now tries the primary
  provider, stale cache, Tushare `moneyflow_ind_ths` + `dc_index`, and only then
  the existing Sina fallback.
- realtime(tushare): expose `/realtime/market-mood` from
  `TushareProvider.get_market_mood()` and let the realtime market overview panel
  prefer that EOD mood snapshot when available.
- data(tushare): wire `TushareProvider` in as the final fallback for the ETF
  history matrix loader. `fetch_etf_history()` still prefers AkShare
  Sina/Eastmoney, but when both are unavailable and `TUSHARE_TOKEN`/`TS_TOKEN`
  is set it now pulls ETF `fund_daily` closes through the shared provider.
- data(etf): extend tracked `data/etf_backtest/etf_prices_5y.csv` from
  2026-05-15 to 2026-05-28 with 9 Tushare-sourced trading days. Validation:
  Tushare and the existing CSV matched exactly on the 2026-05-12 → 2026-05-15
  overlap for all five ETFs before appending.

### Tests

- test(tushare): make the Tushare fallback tests hermetic and deterministic. A
  new autouse fixture in `tests/conftest.py` blanks `TUSHARE_TOKEN`/`TS_TOKEN`
  and resets the class-level `SinaIndustryAdapter._circuit_breakers` around every
  test. Fixes the flaky
  `test_get_stock_list_by_industry_uses_tushare_leader_final_fallback`: the real
  `.env` token leaked into `os.environ` via
  `etf_price_history._get_tushare_token()`, so later unit tests issued live API
  calls and tripped the shared `tushare_dc_index` breaker, which then
  short-circuited the leader fallback to an empty result on whichever test ran
  next inside the ~60s recovery window.

### Documentation

- docs(readme): reposition as quant research infrastructure + surface strategy-falsification methodology
  - 重写 `README.md` 顶部：把项目从"量化交易系统"（隐含能赚钱）如实改写为
    **量化研究基础设施**——回测引擎、实时行情、策略库与一套策略证伪方法学。
    标题、tagline、`📌 仓库定位` 与 `🎯 这个仓适合谁` 均明确声明这不是交易
    信号源、不声称产生 alpha。
  - 新增 `📉 策略证伪：诚实结论` 章节，置于 README 顶部并加入导航。直接指向
    `src/backtest/strategy_statistical_tests.py`（Diebold-Mariano + Politis-Romano
    区块自举 + Memmel/Jobson-Korkie Sharpe 检验 + Holm/Bonferroni 校正）与
    `docs/walkforward_stat_tests_summary.md`，并原样陈述结论：跨 27 个
    Walk-Forward 窗口，轮动策略相对买入持有的边际在统计上与噪声无法区分
    （0/27 窗口原始 DM p < 0.05，最小 p = 0.1299，Holm 校正后 0 个通过）。
  - 给 `✨ 核心能力 → 📊 策略回测` 增加统计检验层交叉引用，并标注策略库
    "不构成投资建议"。纯文档调整，未改动任何策略、测试或分析代码。
  - `data/etf_backtest/etf_prices_5y.csv` extended from 2020-01-02 → 2024-12-31
    (1212 rows) to 2020-01-02 → 2026-05-15 (1540 rows) via
    `scripts/fetch_etf_history_5y.py --end-date 2026-05-15`. Validated zero
    mismatch with the 4y golden CSV on all 968 overlapping dates (max abs
    diff 0.0 on each of 159985/512400/510300/518680/513130).
  - Re-ran every formal stat tool on the extended data: backtest (5y
    n_rebalances=308, Sharpe 0.795, ann-return +8.42%, total +63.89%),
    walkforward (74 × 3-month windows, mean window Sharpe 0.40, worst-DD
    10.81%), multi-strategy comparison with `--with-statistical-tests`
    (n=307 weekly obs), parameter optimizer (3⁴ grid, best Sharpe 0.816,
    no parameter moves Sharpe by more than 0.029), standalone DM test.
  - Saved 4y vs 5y side-by-side artefacts under `outputs/etf_5y_rerun/`
    (backtest_*y, walkforward_*y, comparison_*y, significance_*y, plus
    optimize_5y). Both windows now end on `2026-05-15` so the 4y vs 5y
    diff isolates the effect of *sample size*, not *recency*.
  - **Honest finding**: zero pairwise comparisons cross α=0.05 at either
    window. Smallest 5y DM p = 0.1114 (`rotation_vs_mean_reversion`,
    down from 0.6873 at the rebuilt 4y baseline because the 4y window
    happened to flip the sign of the spread); smallest 5y block-bootstrap
    p = 0.1070 (same pair). Sharpe-difference p-values went the *wrong*
    way for the `rotation_vs_MR` pair (0.12 → 0.62) because MR's 4y
    outperformance was driven by its 2022-2024 sub-window — over 5y MR's
    Sharpe drops from 1.38 to 0.68 and the difference loses both
    magnitude and statistical resolution. No correction (Bonferroni
    α/k=0.00833, Holm) flags any pair at either horizon. The "more data
    won't make it significant" power-analysis prediction from commit
    `fddfbf8` is confirmed: even at 307 weekly obs over a structurally
    favourable window, the strategy claim is statistically
    indistinguishable from noise.
  - Sub-finding: extending sample *did* fix a few sign-instability
    issues. The rebuilt 4y baseline window had `rotation_vs_MR` DM stat
    -0.40 (MR apparently slightly ahead); 5y has -1.59 (rotation clearly
    ahead, consistent with the 5y total-return spread of +37.46 pp).
    The sign no longer flips with sample-size — that's progress, even
    if p stays above 0.05.
  - Bug fix in `scripts/strategy_significance_test.py`: replaced a
    missing `_render_markdown` reference (NameError on `--output-md`)
    with a full markdown renderer (DM / Sharpe / bootstrap CI / multiple-
    testing correction tables) matching `sample_strategy_comparison_5y.md`
    column conventions.
  - Updated docs: `docs/sample_strategy_comparison_5y.md` (now contains
    explicit 4y vs 5y p-value comparison tables); `docs/sample_walkforward_5y.md`
    (4y vs 5y aggregate-metric table, 74-window roll instead of 58).

- feat(backtest): formal statistical tests (DM + block bootstrap + Sharpe ratio)
  - 新增 `src/backtest/strategy_statistical_tests.py`：三个互补的形式化假设检验。
    `diebold_mariano_test(returns_a, returns_b, *, loss_fn="negative_return"|"squared_error"|"absolute_error"|"sharpe", h=1)`
    实现 Diebold-Mariano (1995) 的 DM 统计量 + Newey-West HAC 方差（Bartlett kernel,
    截断滞后 L = h-1），asymptotic 标准正态（n<30 退化到 t-distribution），返回
    `DMResult{dm_statistic, p_value, p_value_one_sided, mean_loss_differential,
    hac_variance, n_obs, loss_fn, h, note}`。`politis_romano_block_bootstrap(
    returns_a, returns_b, *, block_size=10, n_bootstrap=1000, ci_level=0.95, seed=42)`
    实现 Politis-Romano (1994) circular block bootstrap，保留短期自相关；
    返回 `BlockBootstrapResult{mean_diff, ci_low, ci_high, ci_level,
    p_value_two_sided, p_value_one_sided, block_size, n_bootstrap, n_obs}`。
    `sharpe_ratio_test(returns_a, returns_b, *, method="memmel"|"jobson_korkie")`
    实现 Memmel (2003) 闭式 Sharpe 差检验（修正 Jobson-Korkie 1981 的方差公式），
    asymptotic z-test，返回 `SharpeTestResult{sharpe_a, sharpe_b,
    sharpe_difference, z_statistic, p_value, variance_estimate, method, n_obs}`。
    多重比较修正 `bonferroni_correct(p_values, *, alpha=0.05)` 和 `holm_correct(...)`
    返回 `MultipleTestingCorrection` dataclass，含每对的拒绝 flag + adjusted α，
    所有 result dataclass 都有 `to_dict()` 方法 JSON-friendly。
  - `StrategyComparator` 新增 `compute_statistical_tests=False` / `statistical_alpha=0.05`
    / `statistical_block_size=10` / `statistical_n_bootstrap=1000` /
    `statistical_include_buy_hold=True` 参数；启用时计算所有 unordered pairs 的 DM +
    block bootstrap + Sharpe 测试，可选加入 buy-and-hold 合成 returns 形成 4-策略 ×
    6 unordered pairs grid。`ComparisonReport` 新增 `statistical_tests: Optional[
    StatisticalTestsReport]` 字段（默认 None 保留 v0.1 schema 兼容）。Markdown 渲染
    多三个表格（DM/Sharpe/Bootstrap CI）+ Bonferroni/Holm 拒绝表 + 三句方法说明 note。
  - CLI `scripts/compare_strategies.py` 新增 `--with-statistical-tests` /
    `--statistical-alpha` / `--statistical-block-size` / `--statistical-n-bootstrap` /
    `--statistical-no-buy-hold` 标志组；新增 stand-alone CLI
    `scripts/strategy_significance_test.py` 直接打印 pairwise grid 终端表格 +
    `--output-json` JSON 落盘。
  - 单元测试：`tests/unit/test_strategy_statistical_tests.py` 24 条新 case 覆盖：
    DM identical series → p≈1（degenerate-zero-variance fallback path）/ DM 合成
    clear winner → p<0.05 / DM unknown loss_fn raises / DM 空输入 → neutral result /
    DM NaN drop pairwise / HAC bandwidth 改 h 改方差 / 4 种 loss_fn 全部接受 /
    Block bootstrap identical → CI brackets 0 / clear winner → CI clear of 0 /
    deterministic with seed / 输入校验（block_size/n_bootstrap/ci_level）/
    Sharpe identical → p≈1 / Sharpe clear winner → p<0.05 / Sharpe 两个 method
    都接受 / unknown method raises / zero-variance series → graceful 0 returned /
    Bonferroni 阈值 = α/k / Holm ≥ Bonferroni rejection count / Holm cascade 行为 /
    空 p_values list → 空 correction / `results_to_dataframe` round-trips 含 labels。
  - **真实数据回放（2024-01-02 → 2025-04-30，5-asset universe，每周 rebalance，
    blend regime=sideways，n=63 rebalance periods per strategy）**：
    - DM test p-values（6 unordered pairs，loss_fn=negative_return）：
      `rotation_vs_mean_reversion` 0.588 / `rotation_vs_blend` 0.592 /
      `rotation_vs_buy_hold` 0.387 / `mean_reversion_vs_blend` 0.583 /
      `mean_reversion_vs_buy_hold` 0.345 / `blend_vs_buy_hold` 0.387
    - Sharpe difference p-values：0.909 / 0.727 / 0.844 / 0.988 / 0.933 / 0.930
    - Block bootstrap 2-sided p-values：0.543 / 0.548 / 0.427 / 0.536 / 0.379 /
      0.392
    - Block bootstrap 95% CI on (A-B) per-period return differential 全部跨 0：
      最窄的是 `mean_reversion_vs_blend` [-0.0013, +0.0007]，最宽的是
      `mean_reversion_vs_buy_hold` [-0.0097, +0.0025]。
  - **诚实结论**：6 pairs × 3 tests = 18 个 p-value 中，**最小 p = 0.345，**
    **没有任何配对在 α=0.05 或 α=0.10 下显著**，Bonferroni（α/6=0.0083）+
    Holm-Bonferroni 也不会让任何对突围（拒绝集合和 raw α=0.05 完全一致：空集）。
    这与 commit `231c709` 的 parameter-optimizer bootstrap 结论一致：rotation 家族
    top-N config 的 Sharpe CI 都跨 0；现在我们把这个结论扩展到 family-level：
    **rotation 家族 strategies 之间的 spread + 它们与 buy-hold 的 16-19 pp 差距，
    在 2024-01-01 → 2025-04-30 这个窗口上，都是统计学上无法与噪声区分的**。
  - **Implication for paper / production**: 任何引用 "blend wins by Sharpe" /
    "rotation wins by total return" / "all three lose to buy-hold" 这些 spreads
    作为统计 edge 的论述都是 overclaim。论文应当至少 footnote 一句 "differences
    not significant at α=0.05 (p>0.34 across all pairwise tests)"。要把这些
    spreads 推到 5% level 显著，窗口大约需要 5× 当前长度（~6 年 weekly cadence）
    或换更细的 rebalance cadence。Production 不应基于一个窗口的 spread 切策略。
    `docs/sample_strategy_comparison.md` 已经更新了一节「统计显著性检验
    (formal hypothesis tests, 2026-Q2 refresh)」记载所有 p-value + CI + 多重比较
    结论。
  - 显式 **不包含** 内容：自助标准化的 White (2000) Reality Check / Hansen (2005)
    SPC（要等多个 horizon 一起测时再加）；Harvey-Liu-Zhu (2016) 的 multiple-
    testing-adjusted Sharpe（与 Bonferroni 等价但更激进）；t-Stat haircut formulas；
    Ledoit-Wolf 的 Sharpe 差检验（Memmel 已经够，未加 ledoit_wolf 实现）；GMM-based
    SR test（小样本下 Memmel 更稳）。
  - 关联 commit：`a54b986` (multi-strategy comparison) + `231c709` (parameter-
    optimizer bootstrap CIs) — 本次工作把那两次的 "看起来差异不大 / CIs span 0"
    的 hand-waving 升级成形式化 p-value，让任何后续 strategy claim 都有
    statistically defensible 的基础。

- feat(backtest): strategy parameter optimizer with sensitivity analysis
  - 新增 `src/backtest/parameter_optimizer.py`：`ParameterOptimizer` 类把任意 `EtfRotationConfig` 字段（含 ``scoring.*`` 等 dotted 嵌套字段）的笛卡尔积喂给现有 `EtfRotationBacktester` 引擎，返回 `OptimizationReport`（``configurations`` / ``per_config_metrics`` / ``optimal_by_metric`` / ``top_n_by_metric`` / ``parameter_sensitivity`` / ``confidence_intervals`` / ``walkforward_results`` / ``caveats``）。Sharpe / 总收益 / 年化 / MaxDD / Calmar / 换手 / 胜率七项 metric 各自的最优 config + 按所选 metric 排序的 top-N + 每个 swept 参数按 value 分组的 Sharpe std/range（敏感度排序）+ top-N 的 Sharpe bootstrap 95% CI（200 次重采样、deterministic seed）+ 可选 per-config walkforward 稳定性再测。Grid 大小硬上限 ``MAX_GRID_SIZE=200`` 防止误触发多小时任务。
  - 新增 CLI `scripts/optimize_strategy.py`：``--strategy rotation|mean_reversion|blend`` / ``--grid-json <file>`` / ``--metric sharpe|return|calmar|max_dd|turnover|win_rate`` / ``--top-n 10`` / ``--with-walkforward`` / ``--enable-tc`` / ``--output-md`` / ``--output-json`` 等开关；体系上沿用 ``walkforward_etf_rotation_strategy.py`` 的 universe 解析模式（``daily_etf_signal.load_default_holdings`` + ``build_strategy_config``）保证 CLI / backend / 单元测试三条路径用同一份 base config。
  - 新增 HTTP 端点 `POST /etf-rotation/optimize-parameters`：body 接受 ``{period_start, period_end, parameter_grid, strategy, metric, top_n, enable_policy_signal_factor, rebalance_freq_days, initial_capital, strategy_config_overrides, with_walkforward, walkforward_window_months, walkforward_step_months, max_grid_size, tc_model}``；超过 ``max_grid_size`` 立即 422，未知 ``parameter_grid`` key 也 422。同步执行，20-config × 4-year 历史实测 ~5-15s。
  - **真实数据 smoke**（rotation × 2024-01-01 → 2025-04-30、5×4=20 configs：``gross_cap ∈ {0.6, 0.7, 0.8, 0.9, 1.0}`` × ``min_score_to_hold ∈ {15, 20, 25, 30}``）：top-3 by Sharpe 全部是 ``gross_cap=0.6``（id=3 Sharpe 0.727 / id=1 0.724 / id=2 0.722）—— 与默认 ``gross_cap=0.9`` 相比，**收益略低 (+8.04% vs +9-10%)** 但 **MaxDD 显著小 (5.80% vs ~7-8%)** 因此 Sharpe 走高。最优 total_return 是 id=11 (``gross_cap=0.8, min_score_to_hold=30``, +8.91%)。**敏感度排序**：``gross_cap`` 的 mean-Sharpe std=0.0491 / range=0.137（≈ 一个完整波动）远高于 ``min_score_to_hold`` 的 std=0.0019 / range=0.004 —— ``min_score_to_hold`` 在这个网格里**几乎是 no-op**，``gross_cap`` 是真正影响 Sharpe 的旋钮。**Bootstrap CI**：top-5 的 95% CI 都横跨 0（low ≈ -0.13, high ≈ 0.44），说明这 5 个 Sharpe 在 0.704-0.727 区间内**统计上不可区分** —— "optimal config" 的差异有可能纯属噪声。**诚实结论**：默认 ``gross_cap=0.9`` 没有被 grid search 推翻为「错」，但揭示了一段被忽视的更高 Sharpe / 更低 MaxDD 的 ``gross_cap=0.6`` 替代点；用户需要根据自己的 risk-reward 偏好选 cap。样本输出落盘 `docs/sample_parameter_optimization.md`。
  - 单元测试：12 条新 case (`tests/unit/test_parameter_optimizer.py`) 覆盖：未知 grid key / 空 value list / oversize grid / unsupported metric 都在 construction 抛 ValueError；dotted nested key (``scoring.trend_above_ma20_points``) 接受；空 grid → empty report + 明确 caveat；single-config grid 与直接 backtest abs=1e-9 一致；多 config 网格 N 个 result + JSON round-trip；敏感度排序较大 Sharpe spread 的参数排前；top-N 方向感（Sharpe 高优先、MaxDD 低优先）；TC model 透传到每个 config（关闭时 ``no_transaction_costs_modeled`` caveat 在；开启时被剥离）；walkforward 集成 smoke。
  - 显式 **不包含** 内容：多目标 Pareto frontier（v0.1 报告 per-metric 优胜独立）；自适应贝叶斯优化（pure exhaustive grid 优先于 black-box）；早停 / 剪枝（即使最差 cell 也跑完，方便敏感度公式不丢点）；自动 promote-to-prod（report 是建议、决定权仍在人）；正则化 / shrinkage（除了 optional walkforward 之外不做样本外验证 —— 用户自己把 walkforward 打开）；前端 tile（CLI + backend 已够 v0.1 用，dashboard 集成下一轮）。
  - 关联 commit：legacy ``scripts/strategy_param_scan.py`` 一开始只能扫 2D（``min_score_to_hold`` × ``rebalance_delta``）并印 flat table；本次工作把它扩展成 N-D 可配置网格 + 敏感度排序 + bootstrap CI + 可选 walkforward 稳定性 + CLI + backend + 完整单元测试，**直接回答了「我们到底有没有试过最优参数」的合理疑问**。

- feat(etf-rotation): market regime classifier + strategy recommender
  - 新增 `src/strategy/market_regime_classifier.py`：`MarketRegimeClassifier` 类，把一份 wide-form 价格矩阵的最近 `lookback_days` 行（默认 90 个交易日）做 5 特征分类，落地到 6 个 regime 之一（`trending_low_vol` / `trending_high_vol` / `choppy_low_vol` / `choppy_high_vol` / `bear_high_vol` / `bear_low_vol`，外加 `unknown` 兜底）。特征：(1) log-price 线性拟合的 R² + slope（趋势强度 + 方向），(2) 年化实现波动率，(3) 收益偏度（左尾厚度 → 急跌倾向），(4) 最大回撤 / 波动率比（低波动下的不寻常压力 → 有序下行），(5) 跨资产平均两两相关性（risk-off 同向化）。`MarketRegime` dataclass 携带 regime_name / confidence / 所有 features / recommended_strategy / recommended_config_overrides / reasons / lookback_days / n_bars_used / n_assets_used / as_of，前端 tile 一次性渲染不用二次请求。
  - 新增 `src/strategy/strategy_recommender.py`：`recommend_strategy(regime, *, extra_overrides=None) -> StrategyRecommendation` 把 regime 映射到 `(strategy_name, config_overrides, rationale, alternatives)`。映射表实证锚定 commit `a54b986` 的多策略比较结论：`choppy_low_vol → rotation`（commit a54b986 的 2024 上半场 R²=0.370，rotation 胜出 +5.48%）、`trending_low_vol → mean_reversion`（commit a54b986 的 2025 下半场 R²=0.792，MR 胜出 +6.17%）、`choppy_high_vol → blend gross_cap=0.85`、`trending_high_vol → rotation gross_cap=0.85`、`bear_high_vol → cash gross_cap=0.20`、`bear_low_vol → mean_reversion gross_cap=0.60`、`unknown → unchanged`。完全确定性、无 ML 模型、任何输入永远同样输出；空 / NaN / 过短数据返回 unknown 不抛异常。`extra_overrides` 让 caller 层加 override 但不污染单例表。
  - 新增 CLI `scripts/recommend_strategy.py`：`--price-csv data/etf_backtest/etf_prices_4y.csv` / `--lookback-days 90` / `--output-md` / `--output-json` / 可选 `--trend-r2-threshold` `--vol-high-threshold` 阈值覆盖；输出 markdown 报告（regime 标签 + confidence + 5 个特征值表 + 分类依据 + 推荐策略 + config 覆盖 + 原因 + caveats）。
  - 新增 HTTP 端点 `GET /etf-rotation/regime-recommendation?lookback_days=90`：默认对 `data/etf_backtest/etf_prices_4y.csv` 做分类，返回 `{regime: MarketRegime.to_dict(), recommendation: StrategyRecommendation.to_dict(), config: {thresholds...}}`；OpenAPI 已同步（`docs/openapi.json` 新增 `/etf-rotation/regime-recommendation` path）。同步执行 < 100ms（90-day 5-asset 窗口）。
  - 新增前端 `frontend/src/components/EtfRegimeTile.jsx`：lazy-load tile（`data-testid="etf-regime-tile"`），渲染当前 regime 标签（按风险等级 6 色编码：green / blue / processing / gold / volcano / red）+ 置信度 Progress bar + 5 个特征值的 inner card + 推荐策略 + config 覆盖 + 备选 + 原因 Alert + 刷新按钮（`etf-regime-tile-refresh`）；挂载在 `EtfRotationDashboard.jsx` 权重对比表上方。新增 service 函数 `getEtfRotationRegimeRecommendation({lookbackDays, trendR2Threshold, volHighThreshold})`。
  - **真实数据回放**（截至 2026-05-15 的 etf_prices_4y.csv 最近 90 个交易日）：regime = `choppy_high_vol`（置信度 65%）；特征：trend_r2 = 0.015（无趋势）、trend_slope = -0.00018/日（轻微负 drift 但未达 bear 阈值 -0.0005）、realized_vol = 28.8%（突破 25% high-vol 门槛）、return_skew = -1.26（明显左尾厚）、drawdown_ratio = 0.64、avg_pairwise_correlation = 0.35。推荐 = `blend`，config 覆盖 `gross_cap=0.85`，原因 "Choppy AND volatile — single-strategy edge is small; blend rotation and MR to diversify regime risk, and shave 15% off gross_cap to respect the elevated vol."。样本输出落盘 `docs/sample_regime_recommendation.md` + `output/regime_recommendation.{md,json}`。
  - 单元测试：14 条新 case (`tests/unit/test_market_regime_classifier.py`) 覆盖：合成 trending 数据 → trending_* / 合成 choppy 数据 → choppy_* / 合成 bear 数据 → bear_* / 6 个特征都 finite 且在预期范围（R²∈[0,1], vol≥0, dd_ratio≥0, corr∈[-1,1]）/ 7 个 regime label 的推荐映射一致 + `to_dict` round-trip / 空 DataFrame → unknown + confidence=0 + recommended_strategy="unchanged" / 窗口过短（<10 行）→ unknown / 全 NaN 输入 → unknown / 同输入两次跑出 byte-identical dict / `json.dumps(allow_nan=False)` 严格 JSON / `extra_overrides` 覆盖单例表但不污染 / `REGIME_LABELS` 常量覆盖 `_RECOMMENDATION_TABLE` 全部 key / 阈值 override 可以让 R²=0.999 把 trending → choppy / 真实数据 smoke：截至 2026-05-15 不会落到 unknown 且 n_bars=90 / n_assets=CSV 列数 + recommendation 与 regime.recommended_strategy 一致。既有 baseline 全绿（test_etf_regime_detector 7 条 + test_etf_strategy_comparison 13 条 + test_etf_rotation_api 35 条 + 本次 14 条 = 69 条 0 失败）。
  - 与既有 `src/strategy/etf_regime_detector.py` 的分工：旧模块分类**单一广义市场代理**（默认 510300 沪深300）到 5 个 regime（bull/correction/sideways/bear/crisis + unknown）并把 `gross_cap_multiplier` 喂进 rotation 内部管线；本次新模块分类**跨资产 universe**（rotation 全宇宙 5 个 ETF）到 6 个**正交标签**（trending/choppy × low/high-vol + bear × low/high-vol）并直接告诉运营人员**该跑哪个策略**。二者目标不同、互补；前者是「rotation 内部状态」、后者是「策略选择 oracle」。
  - 显式 **不包含** 内容：自动切换策略（推荐是建议、决定权仍在人）、滚动多窗口验证（"回测显示 ChoppyHV → blend 真的优于 rotation 吗"是后续任务）、跨资产类别的 regime（只用 ETF 价格、不读宏观因子如美债收益率或 PMI）、ML 模型（确定性 threshold mapping 优先于 black-box）、regime transition probability matrix。
  - ruff baseline 不仅没有 regression，由于顺手修了若干 typing pattern 反而把 baseline 从 3102 降到 3093（9 条 resolved，0 条新增）。mypy 新增 0 错误。
  - 关联 commit：`a54b986` (multi-strategy comparison) — 本次工作把那次实证发现产品化成「**给我现在的 90 天数据，告诉我跑哪个策略**」的运行时建议器；UI 上方多出一个 tile 直接答这个问题，不用每周翻一遍 comparison report。

- feat(backtest): transaction cost modeling
  - 新增 `src/backtest/transaction_costs.py`：`TransactionCostModel` dataclass（commission_bps=3.0 / min_commission_per_trade=5.0 RMB / bid_ask_spread_bps=5.0 / market_impact_bps_per_pct_adv=0.5 / min_trade_size_rmb=100.0）覆盖 CN 真实零售 ETF 经纪现实，`apply_transaction_costs(event, model) -> CostBreakdown` 把单次调仓的权重差转成 commission + spread + impact 的拆解；冲击只在单笔 > 5% ADV 时才打开，留出零售头寸的免疫区；trade < min_trade_size_rmb 自动跳过（n_trades_skipped_under_min 计数）；missing AUM 退化到 normalized weight-space（portfolio_value=1.0），bps 输出仍可用。
  - `EtfRotationBacktester.__init__` 新增可选 `tc_model: TransactionCostModel | None`（默认 None = 沿用 v0.1 gross-of-fees 行为，**既有调用方零行为变化**）。当传入 model 时，模拟器每次调仓从 equity 扣除对应 bps 成本；新增并行 `gross_equity` 序列让 `gross_total_return_pct` 与 pure-gross 跑数完全一致（已 test verify abs=1e-9）。`BacktestReport` 新增 `tc_enabled / gross_total_return_pct / net_total_return_pct / total_tc_cost_pct / avg_tc_per_rebalance_bps / tc_drag_annualized_pct / tc_model_params` 七个字段；当 TC 关闭时全部为 zero/identity 保持 schema 兼容；当 TC 开启时 caveats 把 v0.1 的 `no_transaction_costs_modeled` / `no_bid_ask_spread_or_slippage` / `no_market_impact` 三行替换为单条 `transaction_costs_modeled(commission_bps=...,spread_bps=...,...)` 参数化标签。每次 rebalance log entry 新增 `tc_cost` 子 dict（per-rebalance 成本拆解）。
  - `EtfRotationWalkforwardAnalyzer` 与 `StrategyComparator` 都接受 `tc_model` 参数，逐窗口 / 逐策略透传给内部 backtester。`WalkforwardReport` 新增 `mean_gross_return_pct / mean_net_return_pct / mean_tc_cost_pct / mean_tc_drag_annualized_pct / tc_enabled / tc_model_params` 跨窗口聚合；`ComparisonReport` 新增 `tc_enabled / tc_model_params` 顶层字段 + markdown 渲染新增「交易成本拆解 (Gross vs Net)」表格。
  - CLI：`backtest_etf_rotation_strategy.py` / `walkforward_etf_rotation_strategy.py` / `compare_strategies.py` 三个脚本全部新增 `--enable-tc / --commission-bps / --spread-bps / --impact-bps-per-pct-adv / --min-commission-rmb / --min-trade-size-rmb` 标志组，CLI flag 默认值与 module-level `DEFAULT_*` 常量绑定，调整一处即可同步。
  - HTTP API：`POST /etf-rotation/backtest` / `/walkforward` / `/strategy-comparison` 三个端点 body 都接受可选 `tc_model` 字段，支持三种形态：`{tc_model: true}` 用 defaults，`{tc_model: {commission_bps: 6.0, ...}}` 覆盖部分参数，`{tc_model: false}` 或省略 = 关闭。Unknown override key 走 `TransactionCostModel.from_overrides` 触发 422 错误。walkforward + comparison 缓存 key 已扩展包含 tc_payload 的 repr，所以打开/调整 TC 模型会自动让 in-flight 缓存失效。
  - **实证 net 数据（2024-01-01 → 2025-04-30 真实窗口，100k 组合，default TC）**：
    - `rotation`: gross +8.71% → **net +7.24%**（1.39% 总成本拖累，2.20 bps/调仓平均）；Sharpe 0.624 → 0.533
    - `mean_reversion`: gross +5.34% → **net +4.00%**（1.30% 成本，2.03 bps/调仓）；Sharpe 0.624 → 0.480
    - `blend`: gross +7.10% → **net +5.67%**（1.37% 成本，2.15 bps/调仓）；Sharpe 0.654 → 0.536
    - **净基础 winner-by-Sharpe 仍是 `blend`**（0.536）但只领先 rotation +0.002；winner-by-Calmar 仍是 `blend` (0.674)；winner-by-return 仍是 `rotation` (+7.24%)。三个策略 **依然全部跑输 buy-hold +23.55%** —— TC 层没救回 rotation 家族的「价值是 drawdown control 而非 alpha」的诚实结论。
    - 100k 组合下 commission 5 RMB/leg 的 floor 占主导，turnover 差异在 bps 上几乎看不到；500k+ AUM 起 bps 部分接手，**v0.1 报告里 "blend's lead would widen" 的预测在 AUM ≥ 500k 才真正成立**（rotation 1.33 bps/reb > MR 1.10 > blend 1.00）。
  - 文档：`docs/sample_strategy_comparison.md` 完整重写为 net basis，头部新增 "Why this report exists" / "Honest reading" / "The 2-3 numbers a paper would cite" / "Insight: regime separation survives the TC layer" / "Bottom line" 五段叙述；`docs/sample_walkforward_report.md` 在原 gross 结果下方追加 "Re-run with default Transaction Cost model" 对照段（14 windows × 3-month，mean gross +2.20% → mean net +1.96%，annualised drag 1.22%）；`docs/sample_etf_rotation_backtest.md` reproduce 区追加 `--enable-tc` 示例（gross +6.37% → net +6.05% on the 2024-09 → 2024-12 quarter，32 bps drag）。
  - 单元测试：32 条新 case (`tests/unit/test_transaction_costs.py`) 覆盖：默认值 → 模块常量绑定 / 单字段 override 不动其他 default / 5 个字段负值都报错 / `from_overrides` 空 dict 与 None 都返回 defaults / unknown key 报 `TypeError` / 小额 trade 触发 commission floor / 大额 trade bps 主导 / impact 仅当 trade>5% ADV 才触发 / sub-min trade 跳过且 n_trades_skipped_under_min 计数 / portfolio_value=0 退化到 1.0 normalized space / zero-delta legs 不进 per_leg / 5 ETF × 5% turnover × 100k portfolio docstring 案例 (5×5=25 RMB commission + 6.25 RMB spread = 31.25 RMB = 3.125 bps) / per_leg deterministic symbol-sorted ordering / dict event input 接受 / 非法 event type `TypeError` / tc_model=None backtester 行为完全等于 v0.1 / TC on net < gross 验证 / TC-run gross == pure-gross 跑数 (abs=1e-9) / tc_drag_annualized_pct = total_tc_cost_pct / years 公式校验 / `to_dict()` + `json.dumps(allow_nan=False)` 含 TC 字段严格 JSON / rebalance_log 每条带 `tc_cost` 子 dict / walkforward 透传 tc_model 到每个窗口 / walkforward 无 tc_model legacy shape / comparator 透传 tc_model 到每个策略 / comparator 无 tc_model legacy shape / comparison `to_dict` 含 TC 字段 / legacy caveat 字符串在 TC 关闭时保留 / TC 开启时 legacy 三条 caveat 替换为单条参数化 tag。既有 1355 条测试 0 regression（含 36 条 backtest / walkforward / comparison legacy case）。
  - 显式 **不包含** 内容：variable spread（用 flat 5 bps，真实 CN ETF 1-15 bps；QDII 偏高端）、partial fills、intraday execution delay 超过 strategy 自带的 one-bar lag、survivorship bias、QDII dividend WHT、机构级 impact 校准（默认 0.5 bps/%ADV 对零售 conservative，机构需重校）。前端 tile 推迟到下一轮 —— CLI + backend 已足够支撑这一版。

- feat(etf-rotation): multi-strategy comparison
  - 新增 `src/backtest/strategy_comparison.py` —— `StrategyComparator` 类，把 `EtfRotationStrategy` / `EtfMeanReversionStrategy` / `EtfStrategyBlend`（或任意子集）在 **同一个** 价格矩阵 / 同一个时间窗口 / 同一个 rebalance 节奏下并排回放，复用 v0.1 的 `EtfRotationBacktester`（commit `840addf`）作为唯一引擎；MR 与 blend 通过 `_bar_by_bar_generate_signals` 把它们各自的 `evaluate(latest_row)` 接口适配成与 `EtfRotationStrategy.generate_signals` 同形状的 wide-form 目标权重 DataFrame，保证三条路径的 simulation / metrics / buy-hold benchmark 计算完全相同。
  - 输出 `ComparisonReport` dataclass：每个策略的完整 `BacktestReport`（含 rebalance_log）+ Sharpe / 总收益 / Calmar / MaxDD / 换手 五项单项冠军（`WinnerSummary`，无可用值时 label/score=None 不抛异常）+ midpoint-split regime 分析（按 `_linear_fit_r2` 把窗口分成 trending / choppy 两半，并报告每个策略在每半的收益与各半优胜）+ 全部有序两两的 return / sharpe / MaxDD 差值（`PairwiseSpread`，双向都返回，UI 不用前端反推符号）。`to_dict()` 通过 `json.dumps(allow_nan=False)` —— FastAPI 默认编码器可直接吞下。
  - **直接回应**了 v0.1 + walkforward 留下的「三个策略各自测但没人 A/B/C」的问题：实测 `2024-01-01 → 2025-04-30` 真实窗口（与 walkforward 同窗口），sideways regime 下 blend 在 Sharpe (0.654 > rotation 0.624 ≈ MR 0.624) 与 Calmar (0.878 > rotation 0.791 > MR 0.694) 上同时夺冠，turnover 也最低 (5.22% < MR 6.05% < rotation 7.55%)；rotation 仅在总收益 (+8.71%) 上称王但代价是最大回撤 (8.59% vs MR 6.03%)。三个策略 **全部跑输等权 buy-hold +23.55%**，所以 rotation 家族这段窗口的价值是 drawdown control 而非 alpha generation —— 一个诚实的结论。
  - regime 分析显示 **rotation 与 MR 真正互补**：trending half（second_half R^2=0.792）winner 是 MR (+6.17%)，choppy half（first_half R^2=0.370）winner 是 rotation (+5.48%)，两个半区优胜方向相反 —— 教科书式的「ensembles smooth single-regime failure」论据在本窗口实证成立。
  - 显式继承 v0.1 backtest 全部 caveats（无交易成本 / 无买卖价差 / 无冲击 / next-bar close 全额成交 / 无幸存者偏差），并额外标注 `comparison_window_shared_across_strategies` 提醒比较是 apples-to-apples 但 turnover 差异（rotation 7.55% > MR 6.05% > blend 5.22%）意味着一旦层 5-10 bps 真实费率，rotation 的头条 +8.71% 会率先缩水、blend 的领先会拉大。
  - 新增 CLI `scripts/compare_strategies.py`：`--prices-csv`/`--period-start`（必填）/`--period-end`（必填）/`--strategies rotation,mean_reversion,blend`（默认全 3 个，逗号分隔）/`--enable-policy-signal`/`--blend-regime` (bull/correction/sideways/bear/crisis/unknown)/`--strategy-config`/`--rebalance-freq-days`/`--initial-capital`/`--output-md`/`--output-json`；与 backtest + walkforward CLI 共用 `build_strategy_config / load_default_holdings / load_policy_industry_signals` 解析路径，三个 CLI 在 universe / strategy override / industry signal 加载上行为完全一致。
  - 新增 HTTP 端点 `POST /etf-rotation/strategy-comparison`：body 接受 `{period_start, period_end, strategies, enable_policy_signal_factor, blend_regime, rebalance_freq_days, initial_capital, strategy_config_overrides, refresh}`，默认回放 `data/etf_backtest/etf_prices_4y.csv`（已提交），返回 `ComparisonReport.to_dict()`；显式 422 拒绝未知 strategy label / `rebalance_freq_days=0` / `initial_capital<=0` / 缺 `period_start` `period_end` / 非 dict 的 `strategy_config_overrides` / 非法 `blend_regime`。**缓存 1 小时**，cache_key 包含所有比较参数 (period_start/period_end/strategies/rebalance_freq_days/enable_policy_signal_factor/initial_capital/blend_regime/overrides) + 价格 CSV 的 mtime/size，CSV 更新自动让 in-flight 缓存失效；响应里带 `cached: bool` + `cache_age_seconds`。同步执行，3 策略 × 15 个月窗口实测 ~10s，OpenAPI 已同步（`docs/openapi.json` `/etf-rotation/strategy-comparison` path 已生成）。
  - 文档：`docs/sample_strategy_comparison.md` 由 `2024-01-01 → 2025-04-30` 真实数据跑出（blend_regime=sideways），头部加了 "Why this report exists" / "Honest reading" / "Insight: regime separation is real" / "Caveats inherited from v0.1" / "Bottom line" 五段叙述，把三个策略全部跑输 buy-hold、blend 在 Sharpe+Calmar+turnover 三项夺冠、rotation+MR 真正互补这些诚实结论写明。
  - 单元测试：13 条新 case 覆盖单策略 → 单 entry / 三策略 → 三 entry + 6 个 ordered pair spreads / 同输入两次跑出 byte-identical to_dict / 空策略列表 → 空报告非空 winner 对象 / 越界 period → n_bars=0 但不抛 / 单调上涨所有策略 MDD=0 + 收益≥0 / `_winner_higher_better` + `_winner_lower_better` 手工 3 策略校验 (最高 sharpe/最高 return/最高 calmar 跳过 None/最低 dd/最低 turnover) / 设计 choppy→trending 半区的合成价格让 regime 检测器准确标 `second_half=trending` `first_half=choppy` / `to_dict()` 通过 `json.dumps(allow_nan=False)` 严格 JSON / markdown 渲染包含每个 strategy 行 + 每个 ordered pair 行 / 重复 label 构造期报错 / `rebalance_freq_days=0` 与 `initial_capital<=0` 构造期报错 / 5-ETF 真实形态 universe 下 MR + blend 都跑出 n_rebalances>0（防 evaluator 静默返回零权重的回归）。既有 baseline + 13 新 case 全绿。
  - 显式 **不包含** 内容：前端 tile（CLI + backend 已足够支撑这一版）、跨策略 walkforward（用户可对每个策略分别跑 walkforward 然后比较）、交易成本建模（沿用 v0.1 caveats）、bid-ask spread。

- feat(etf-rotation): walkforward backtest analyzer
  - 新增 `src/backtest/etf_rotation_walkforward.py` —— `EtfRotationWalkforwardAnalyzer` 类，把 v0.1 的 `EtfRotationBacktester`（commit `840addf`）在同一份已提交的历史价格矩阵上滚动 N 个 `window_months` 长（默认 3 个月）、按 `step_months` 步进（默认 1 个月）的子窗口；对每个窗口直接复用 v0.1 backtester，最后把所有窗口聚合为 `WalkforwardReport` dataclass：保留每个窗口原始 `BacktestReport`，并汇总 `median/mean_window_return_pct`、`return_std_pct`、`pct_positive_windows`、`mean_sharpe/median_sharpe`、`mean_max_dd_pct/worst_window_dd_pct`、`mean_buy_hold_return_pct`、以及 0-1 的 `consistency_score`（定义 = `pct_positive * 1/(1+CV)`，CV = std/|mean| 时分母用绝对均值避免近零均值放大噪声）。
  - **直接回应**了 v0.1 backtest 留下的「single-window noise」问题：v0.1 2024-09→2024-12 那一个 4 个月窗口给的 +6.37% / Sharpe 1.33 / MDD 5.38% 只是 1 个数据点；walkforward 把同一策略滚动 14 个 3-月窗口（2024-01→2025-04）后给出 median window return +2.10% / mean +2.20% / std 4.45 pp / 9 of 14 (64.3%) 正收益 / mean MDD 4.62% / worst MDD 6.74% / mean buy-hold per window +5.05% / consistency_score 0.213 —— 实证答案：策略 **方向上多数窗口正收益但平均跑输 buy-hold**，价值仍是回撤控制而非 alpha。
  - 显式继承 v0.1 全部 caveats（无交易成本 / 无买卖价差 / 无冲击 / next-bar close 全额成交 / 无幸存者偏差），并额外标注 walkforward 专属：`walkforward_overlapping_windows_double_count_overlap`（重叠窗口在 `aggregate_return_pct` 上会双计重叠部分，看 `median_window_return_pct` 更稳）、`sequential_execution_no_parallelism`（v0.1 不做 multiprocessing —— EtfRotationStrategy 的 pickle-safety 没验证过 + 小窗口下进程启动开销可能盖过并发收益，等 benchmark 显示明显瓶颈再说）。
  - 新增 CLI `scripts/walkforward_etf_rotation_strategy.py`：`--prices-csv`/`--start-date`（必填）/`--end-date`（必填）/`--window-months`/`--step-months`/`--enable-policy-signal`/`--strategy-config`/`--rebalance-freq-days`/`--initial-capital`/`--output-md`/`--output-json`；与单窗口 backtest CLI 共用 `build_strategy_config / load_default_holdings / load_policy_industry_signals` 解析路径，所以两个 CLI 在 universe / strategy override / industry signal 加载上行为完全一致。
  - 新增 HTTP 端点 `POST /etf-rotation/walkforward`：body 接受 `{period_start, period_end, window_months, step_months, enable_policy_signal_factor, rebalance_freq_days, initial_capital, strategy_config_overrides, refresh}`，默认回放 `data/etf_backtest/etf_prices_4y.csv`（已提交），返回 `WalkforwardReport.to_dict()`；显式 422 拒绝 `window_months=0` / `step_months=0` / 缺 `period_start` / `period_end`（而不是被 `or` 操作符吞掉静默回退默认）。**缓存 1 小时**，cache_key 包含所有窗口参数（`period_start/period_end/window_months/step_months/rebalance_freq_days/enable_policy_signal_factor/initial_capital`，cents-precision 浮点 key）+ overrides + 价格 CSV 的 mtime/size，CSV 更新自动让 in-flight 缓存失效；响应里带 `cached: bool` + `cache_age_seconds` 让前端能区分命中与未命中。同步执行，14 个窗口实测 ~30s，OpenAPI 已同步（`docs/openapi.json` `/etf-rotation/walkforward` path 已生成）。
  - 文档：`docs/sample_walkforward_report.md` 由 `2024-01-01 → 2025-04-30` 真实数据跑出（14 个 3-月窗口 × 1-月步进），头部加了 "Why this report exists" / "Honest reading" / "Bottom line" 三段叙述，把单窗口 noise 问题、64% 正收益但 consistency_score 仅 0.213 的解读（CV ~2 → 方向对但波动大）、worst windows #5/#10/#11 都落在 choppy tape 这些诚实结论写明；交叉引用 v0.1 `docs/sample_etf_rotation_backtest.md` + commit `840addf`。
  - 单元测试：11 条新 case 覆盖空 period bounds → 空报告 / period<window → 空报告 / 窗口计数 = `(N-W)/S+1` 公式校验 / **单窗口等价性**（walkforward 1 window 数值必须与 `EtfRotationBacktester` 直接调用同窗口完全一致，total_return / sharpe / max_dd / final_equity / buy_hold 全 1e-9 abs）/ 多窗口 mean/median/pct-positive 与 numpy 手算一致 / A/B policy factor 双路径都不报错 + 因子 flag 透传到 per-window report / per-window buy-hold = direct call buy-hold / `_compute_consistency_score` 边界（全正零方差→1.0、全零→0.0、混合→(0, 0.5)、单元素→pct_positive、空 list→0.0）/ `to_dict()` 通过 `json.dumps(allow_nan=False)` 含嵌套 windows / 构造期 `window_months/step_months/rebalance_freq_days=0` 与 `initial_capital<=0` 报错 / 聚合 caveats 同时包含 walkforward 专属 + dedup 后的 per-window 继承。
  - 显式 **不包含** 内容：前端 tile（CLI + backend 已足够支撑这一版）、并行执行、交易成本建模、bid-ask spread。

- feat(etf-rotation): historical backtest harness
  - 新增 `src/backtest/etf_rotation_backtest.py` —— `EtfRotationBacktester` 类，把已提交的历史价格矩阵喂给生产 `EtfRotationStrategy`，按 `--rebalance-freq-days`（默认 5 天）滚动调仓，输出 `BacktestReport` dataclass：`total_return_pct / annualized_return_pct / sharpe_ratio / max_drawdown_pct / calmar_ratio / avg_turnover_pct / win_rate / comparable_buy_hold_return_pct` + 每次 rebalance 的 weights / turnover / period_return 拆解。
  - 显式遵守策略原生的 `lag_days=1` 因果约束（bar `t` 的权重来自 bar `t-1` 的 close），现金桶隐含 0% 收益（gross_cap < 1 自然留出剩余权重）；caveats 字段把所有 v0.1 简化（无交易成本 / 无买卖价差 / 无冲击 / next-bar close 全额成交 / 无幸存者偏差）逐项写明，方便下游消费者校准期望。
  - 新增 CLI `scripts/backtest_etf_rotation_strategy.py`：`--prices-csv`/`--start-date`/`--end-date`/`--enable-policy-signal`/`--strategy-config`/`--rebalance-freq-days`/`--initial-capital`/`--output-md`/`--output-json`，支持 A/B factor 开关。
  - 新增 HTTP 端点 `POST /etf-rotation/backtest`：body 接受 `{period_start, period_end, enable_policy_signal_factor, rebalance_freq_days, initial_capital, strategy_config_overrides}`，默认回放 `data/etf_backtest/etf_prices_4y.csv`（已提交），返回 `BacktestReport.to_dict()`；3 个月窗口实测 ~5s，同步执行，OpenAPI 已同步。
  - 文档：`docs/sample_etf_rotation_backtest.md` 由 `2024-09-01 → 2024-12-31` 真实数据跑出（+6.37% rotation vs +12.02% equal-weight buy-hold；Sharpe 1.33；MDD 5.38%；avg turnover 5.98%），并在尾部诚实标注「该窗口策略 underperform buy-hold，单季度数据噪声大，需配合 walkforward 评估」。
  - 单元测试：12 条新 case 覆盖空价格 → 空报告 / warmup 不足 → empty / 平市 → 0% 收益且 Calmar=None / 单调上涨 → 正收益 0 回撤 / policy factor on+off 双路径都不报错 / turnover 与手算一致 / 单调上涨的最大回撤=0 / buy-hold 基准与天真计算匹配 / `to_dict()` 通过 `json.dumps(allow_nan=False)` / 构造期 `rebalance_freq_days=0` 与 `initial_capital<=0` 报错 / 窗口起止颠倒 → 空报告。
  - 显式 **不包含** 内容：前端 tile（推迟到下一轮，CLI + backend 已足够支撑这一版）、交易成本建模、bid-ask spread、市场冲击。

- feat(ui): policy_factor_attribution panel in ETF rotation dashboard
  - 完成上一轮显式推迟的前端 tile：`frontend/src/components/EtfPolicyFactorAttributionPanel.jsx` 现在调用 `GET /etf-rotation/policy-factor-attribution`，把 `AttributionReport` 渲染成头部 contribution Tag（正向绿 / 负向红）+ Antd Collapse 内的 Recharts `BarChart`（每次调仓一根条，色彩按 contribution 正负切换）+ Top winners / Top losers 两张迷你表。
  - 新增 7/30/60/90 天 Radio 周期选择器，切换即触发新的 fetch（不带 `refresh`，沿用 backend 5min 缓存）；🔄 按钮显式带 `refresh=true` 跳过缓存。空窗口走 Antd `Empty`，错误走 `Alert`，加载中走 `Spin`。
  - `EtfRotationDashboard.jsx`：把直接 import 改成 `lazyWithRetry(() => import('./EtfPolicyFactorAttributionPanel'))`，再用 `<Suspense fallback={null}>` 包装，并加上 `policyFactorEnabled` gate —— 因子关闭时整个面板根本不进入 DOM，初始 dashboard chunk 也不会拖 Recharts 进来。
  - 新增 `frontend/src/__tests__/etf-rotation-attribution-tile.test.jsx` 6 条用例：toggle on/off 显隐、+0.68% 绿 Tag / -0.45% 红 Tag、5 次调仓 → 5 个 Recharts Cell（mock recharts 后比对 fill 颜色）、Top winners 表渲染 515030 / 512400、refresh 按钮带 `refresh=true` 二次 fetch、period 7/30/90 切换分别带 `periodDays` 触发新 fetch、空窗口走 empty state。既有 16 条 ETF dashboard 测试全部不破。

- feat(etf-rotation): policy_signal_factor performance attribution
  - 新增 `src/research/policy_factor_attribution.py`，对启用了 `policy_signal_factor` 的历史调仓做实证归因：`adjusted_weights` 作为 factor-on 路径，对每只受影响 ETF 按 `policy_adjustment.weight_before / weight_after` 比例反推 factor-off 反事实路径，两条权重在下一条审计 rebalance 前持有（按 ETF 收盘价 mark-to-market），差值即 P&L 边际贡献。返回 `AttributionReport` dataclass，包含窗口 on/off/contribution（逐窗口复利）、命中率、top winner/loser ETF、逐次调仓拆解。
  - 新增 CLI `scripts/analyze_policy_factor.py`：`--audit-log`/`--period-days`/`--output-md`/`--output-json`，并提供 `--synthetic` 模式生成确定性 30 天 audit + 价格矩阵，便于在真实审计日志尚无 factor-on 历史时预览报告形态。
  - 新增 HTTP 端点 `GET /etf-rotation/policy-factor-attribution?period_days=30`：返回 `AttributionReport.to_dict()`；按 (period_days, audit mtime, size) 做 5 分钟内存缓存（`refresh=true` 可绕过）。OpenAPI 已同步。
  - 文档：`docs/sample_attribution_report.md` 是 `--synthetic --seed 2026` 出来的样例（5 次 rebalance，hit rate 100%，contribution +0.68%）；模块顶部 docstring 显式列出 caveats（TC 不计、调仓滞后假设 0、cash 0%、off leg 是 post-overlay proportional proxy）。
  - 单元测试：13 条 case 覆盖空 audit / factor-off / bullish boost on rising / bearish penalty on falling / bullish boost on falling / 后置 overlay 比例缩放 / 当日 close 切片 / 多次 rebalance 复利一致 / per-rebalance 加总到总 contribution / hit rate / top winner+loser 识别 / factor toggle 跨连续 rebalance / markdown render smoke。
  - 显式 **不包含** 内容：前端 tile（推迟到下一轮）、交易成本建模、多周期分解。

- feat(export): public summary JSON for external consumers (Phase F1)
  - 新增 `scripts/export_public_summary.py`（含 `scripts/refresh_public_summary.sh` thin wrapper），把 `cache/alt_data/providers/policy_radar.json`、`data/industry/heatmap_history.json` 最新 snapshot、`data/paper_trading/*.json` 的 profile 名、`~/.config/etf-rotation/audit.jsonl` 最后一条记录的时间戳，蒸馏成一份小而稳定的 `data/public/quant_summary.json`（schema_version=1，当前 ~1.4 KB）。
  - 顶层 sections：`policy_radar`（top-5 行业按 \|avg_impact\| 排序）、`industry_heat`（top-10 行业按 total_score，命中 policy_radar 时附带 `policy_signal`）、`etf_rotation`（默认 `policy_signal_factor_enabled` / 默认 universe size / 可用策略数 / 最近一次 audit 时间戳与条目数）、`paper_trading`（profile 名，**永不**暴露现金或持仓）。
  - 安全过滤：原始 RSS 正文、文件路径、用户现金、调仓权重等不会进入输出；缺 cache 时对应 key 直接缺席，绝不写入合成数据。Atomic-write 通过 `tempfile.mkstemp + replace` 保证并发读不会看到半截 JSON。
  - 下游消费者：sibling 项目 `cn-altdata-brief` 现在可以在 GitHub Actions 里 `git clone` 本仓库 → 读 `data/public/quant_summary.json` 拿到全部 headline 数据，**不再**需要直接访问 `cache/`（被 `.gitignore` 排除）或拉起 FastAPI 进程。
  - 触发方式：CLAUDE.md 已经声明 Celery 只用于回测任务卸载（**不**做定期调度），所以这里通过 `docs/MAINTENANCE_GUIDE.md` 推荐的 cron 条目（`0 * * * *`，每小时一次）周期触发；本地手动跑 `./scripts/refresh_public_summary.sh` 即可。
  - `.gitignore`：把 `data/` 顶层规则改成 `data/*` 并把 `data/public/*.json` 加入白名单；其它子目录（`paper_trading/`、`industry/`、`research_journal/` 等）保持忽略。
  - 单元测试：12 条新 case 覆盖 schema 必备字段、policy_radar 排序与 cap、industry_heat 与 policy_radar 关联富化、paper_trading 不泄露现金 / 持仓 / 股票代码、audit 只暴露时间戳、provider/heatmap 缺失时的优雅降级、atomic-write 不留 `.tmp`、size budget < 50 KB、`SCHEMA_VERSION` 锁定为 1、同输入 → 同输出的确定性、敏感字符串黑名单。

### Tests

- test(strategy): add coverage for mean reversion + strategy blend modules

### Features

- feat(ui): policy_signal_factor toggle in ETF rotation dashboard
  - 用户可以在仪表盘里直接开关 `policy_signal_factor`，**无需编辑** `etf_strategy_config.example.json` 或重启后端。开关勾选状态持久化到 `~/.config/etf-rotation/ui_preferences.json`（路径可由 `ETF_PREFERENCES_PATH` env 覆盖），仅影响当前安装，从源代码或部署清单看不到。
  - 新增两个 HTTP 端点：
    - `GET /etf-rotation/preferences` → `{preference, effective, config_default}`。`preference.policy_signal_factor_enabled` 是文件里的原值（`null` = 未设置）；`effective` 已经把 config 默认折算进来；`source ∈ {config, preference}` 解释 effective 是哪一档赢了。
    - `POST /etf-rotation/preferences` body `{policy_signal_factor_enabled: true|false|null}`。`null` 清除偏好，回退到 config 默认。写入使用 `temp + rename` 原子模式（参考 `src/data/alternative/governance.py::AltDataCacheStore._write_json`），并发读不会读到半截 JSON。
  - 优先级（高到低）：**显式 query 参数 > UI 偏好 > strategy.json 默认值 > built-in `False`**。`/etf-rotation/daily-signal`、`/live-target?trigger_refresh=true`、`/refresh` 的响应中现在统一带 `policy_signal_factor_enabled` 顶层 bool + `policy_signal_factor.source` 来源标签，便于前端把开关 UI 与「现在到底开没开」保持一致。
  - 前端：在 `EtfRotationDashboard.jsx` 头部卡片里新增 `data-testid="etf-policy-factor-toggle"` Antd `Switch`、Tooltip 解释「默认调整 ±10%、关闭时只是参考展示」、绿色徽标显示 ON 状态、紫色 Tag 显示「当前应用 N 只」。开启时下方渲染 `Δ vs factor-off` 面板，按 `score_breakdown[code].policy_adjustment` 列出每只受影响 ETF 的 ±% 与 `policy boost` / `policy penalty` 说明。
  - 策略逻辑保持不变（仍然由 `_apply_policy_signal_factor` 实现 ±10% 边界），仅在 orchestration 层引入偏好查询。配置默认行为 + 既有 query-param + CLI flag 路径全部向后兼容。
  - 单元测试：8 条新后端测试（GET/POST、原子写、precedence query>preference>config）+ 6 条新前端测试（toggle 默认 OFF、点击→POST→re-fetch、Δ 面板渲染 applied 行、关闭隐藏面板、source 来源 Tag、preferences 预热）。

- feat(etf-rotation): opt-in policy_signal_factor closes the decision-impact loop
  - 把 commit `1d2f9f7`/`7148009` 引入的 `policy_radar` 信号从「面板/工作区只展示」升级为「可选择真正影响 ETF 目标权重」。**默认关闭** —— 既有用户体验完全不变，要 opt-in 才生效。
  - 新增四个配置项（`src/strategy/etf_rotation_config_loader.py::DEFAULT_STRATEGY_PARAMS` + `EtfRotationConfig`）：
    - `policy_signal_factor_enabled: bool = False` —— 总开关
    - `policy_signal_factor_bullish_boost: float = 0.10` —— 看多行业 ETF 目标权重 × `(1 + 0.10)`
    - `policy_signal_factor_bearish_penalty: float = 0.10` —— 看空行业 ETF 目标权重 × `(1 - 0.10)`
    - `policy_signal_factor_neutral_pass: bool = True` —— 中性信号视为 no-op
    - `policy_signal_factor_bullish_threshold: float = 0.10` —— `avg_impact` 多空分界，与现有 dashboard tag 配色一致
  - 新增 `StrategyConfig.etf_industry_map: dict[str, str]` —— 把 ETF 6 位代码映射到 policy_radar 行业名。默认空，缺映射的 ETF 完全不受影响 —— 渐进式 opt-in。
  - **策略不变量**：在默认 ±10% 区间内，任何单只 ETF 都不会被这个因子归零或翻倍；每轮在 `_apply_policy_signal_factor` 内部按 `gross_cap` 做比例缩放，组合级约束守住。
  - 实施在 `src/strategy/etf_rotation_strategy.py::EtfRotationStrategy._apply_policy_signal_factor`：score 计算之后、`_normalize_signals` 之前对每只映射 ETF 应用乘数。`EtfSignal.policy_adjustment` 字段沿审计链下沉到 `score_breakdown[code].policy_adjustment` 与审计日志条目顶层 `policy_signal_factor` 摘要。
  - 命令行：`scripts/daily_etf_signal.py` 新增 `--enable-policy-signal` / `--disable-policy-signal` 互斥开关（覆盖 `strategy.json` 配置）。
  - HTTP API：`/etf-rotation/daily-signal` 新增 `enable_policy_signal_factor` 查询参数（`true` / `false` / 省略沿用配置）。`EtfRotationService.refresh(...)` 也接受同名参数，方便面板做 "本次开启试看" 的预览刷新。
  - Dashboard 审计 Timeline：现在每行渲染 `score_breakdown[code].policy_adjustment.applied=true` 的条目（如 `512400 -8.0% policy bearish`），同时在头部加 `政策因子 ON` 紫色 Tag，便于回看历史调仓与政策信号的对应关系。
  - 单元测试：11 条新 case 覆盖 enabled-off 不动权重、bullish boost、bearish penalty、neutral pass、缺失行业数据、极端 `avg_impact`（不出 NaN/负值/超 1.0）、NaN `avg_impact`、混合多空（含再归一化）、config 验证（负 boost / penalty=1.0）等；新增 4 条 `daily_etf_signal` 测试覆盖审计 payload + `load_policy_industry_signals` 解析。
  - **工作示例**（4 只 ETF，`enabled=True`，默认 ±10%；policy_radar 当时 `新能源汽车=bearish (avg_impact=-0.32)`、`风电=neutral (0.0)`、`电网=neutral (0.0)`、`metals=bullish (0.30)`，假设 `etf_industry_map={'515030':'新能源汽车','159987':'风电','562880':'电网','512400':'metals'}`）：
    ```
    code   industry    base_w    policy_w  delta
    515030 新能源汽车   0.20  →   0.180     -10% bearish
    159987 风电        0.20  →   0.200      0   neutral
    562880 电网        0.10  →   0.100      0   neutral
    512400 metals      0.20  →   0.220     +10% bullish
    --                 0.70      0.700     gross_cap (0.90) not bound → no rescale
    ```
    - 若 boost 把总仓推超过 `gross_cap`（例如四只都被 boost 到 0.99），系统会按 `0.90 / 0.99 ≈ 0.91` 比例统一缩放，组合级守住 0.90。
    - 若 policy_radar 离线（`cache/alt_data/providers/policy_radar.json` 缺失或解析失败），`load_policy_industry_signals` 返回空字典，整套权重退化到不开启的旧行为，永不抛错。
  - **审计日志样例**（`~/.config/etf-rotation/audit.jsonl` 每条 JSON）：
    ```json
    {
      "run_at": "2026-05-17T10:30:01+00:00",
      "quote_source": "service:live",
      "adjusted_weights": {"512400": 0.220, "515030": 0.180, "159987": 0.200, "562880": 0.100, "CASH": 0.300},
      "policy_signal_factor": {
        "enabled": true,
        "industry_signals_count": 3,
        "applied_count": 2,
        "boosted": ["512400"],
        "penalised": ["515030"],
        "last_refresh": "2026-05-17T08:29:46"
      },
      "score_breakdown": {
        "515030": {
          "score": 32.1, "raw_target_weight": 0.180,
          "policy_adjustment": {
            "industry": "新能源汽车", "signal": "bearish", "avg_impact": -0.32,
            "multiplier": 0.90, "delta_weight": -0.020,
            "weight_before": 0.200, "weight_after": 0.180,
            "applied": true
          }
        }
      }
    }
    ```

- feat(industry): surface policy_radar in ranking + heatmap
  - 把 `policy_radar` 的覆盖面从 commit `1d2f9f7` 的「ETF 轮动调仓面板」扩展到「行业研究视图」(`?view=industry`)。
  - 后端 `/industry/industries/hot` 新增可选 `include_policy_signal` 查询参数（默认 `false`，既有调用方完全不变）。`true` 时每一行追加 `policy_signal: {avg_impact, mentions, signal, last_refresh_at}`；缺政策数据的行业返回 `null`。policy_radar 离线时整张表整体降级为 `None`，HTTP 200 不变。
  - 前端「行业排行榜」新增「政策信号」列：偏多/偏空/中性 Tag、提及次数、影响数值，按 `|avg_impact|` 可排序，空数据回退到 `-`。`data-testid="industry-policy-signal-column"` 留作 e2e/集成测试钩子。
  - 行业热力图新增「政策着色」按钮模式（与默认温度着色独立切换）：tile 背景按 `signal` 重新上色（红=偏多 / 绿=偏空 / 灰=中性或无数据），不替换默认温度着色，OFF 时回归原配色。
  - 仅信息呈现层；ETF 轮动策略的目标权重计算（`src/strategy/etf_rotation_strategy.py`）保持不变。

- feat(etf-rotation): surface policy_radar signal in dashboard
  - 在 ETF 轮动调仓页面新增「政策信号」Collapse 面板，展示 `policy_radar` 最新行业级别影响（按 `|avg_impact|` 排序的 Top 3）。
  - 面板位于审计日志 Collapse 之前，懒加载方式拉取 `/policy-radar/signal`；`available:false` 时显示 Empty 占位；`last_refresh` 超过 24 小时时打上「已过期」提示。
  - 仅 UI 改动；ETF 轮动策略的目标权重计算（`src/strategy/etf_rotation_strategy.py`）保持不变，政策信号仅作为信息提示。

### Tooling

- **CI**: 新增 `lint` 任务与 coverage 阈值，防止 ETF rotation 扩张期债务静默回涨。
  - `lint` 任务：`ruff check src backend scripts tests --output-format=github`
    输出 GitHub 行内注释（advisory），随后 `python scripts/check_ruff_baseline.py`
    作为硬门槛——读取 `scripts/ruff_baseline_count.txt`（首版 3102），
    比当前发现数大就 fail，留出修就降一档的空间。
  - `backend` 任务的 `pytest --cov` 调用新增 `--cov-fail-under=60`
    （当前实测 61%，1 个百分点缓冲）。后续覆盖率上涨时手动抬高，
    永不下调。
  - 本地复跑：`python scripts/check_ruff_baseline.py` 与
    `pytest tests/unit tests/integration -m "not perf" --cov=src --cov=backend --cov-fail-under=60`。
  - 详细的 re-baseline 流程见 `docs/MAINTENANCE_GUIDE.md` 第 9 节。
- **BREAKING (前端)**：从 CRA (`react-scripts 5.0.1`) 迁移到 **Vite 5 + Vitest 2**。
  - `npm start` 与 `npm run build` 仍然存在，但底层换成 Vite。构建输出目录保持 `frontend/build/` 不变。
  - 新增 `npm run dev`（与 `start` 同义）和 `npm run preview`（预览 production bundle）。
  - 单元测试通过 Vitest 跑：`npm test` 等价 `vitest run --reporter=basic src/__tests__`。
  - **环境变量**：生产部署应使用 `VITE_API_URL` / `VITE_API_TIMEOUT` / `VITE_API_TIMEOUT_ANALYSIS` / `VITE_API_TIMEOUT_STANDARD` / `VITE_API_TIMEOUT_DASHBOARD` / `VITE_REALTIME_WS_TOKEN`。`REACT_APP_*` 旧变量名通过 `frontend/src/env.js` 兼容层继续可读，但不再是首选。
  - 漏洞扫描数：从 41 (CRA depchain) 降到 4 (Vite depchain)。
- 后端 `Alembic` 引入 baseline migration（`backend/alembic/versions/0001_baseline.py`，no-op）；首次部署时执行 `alembic stamp head` 即可。
- CI 新增 `typecheck` 任务：`mypy` 在迁出来的 `src/analytics/technical_indicators` + `src/analytics/industry/` 干净目标上必过；全 `backend/app/services` 范围作为非阻塞探针。

### Refactoring

- `analysis.py` endpoint 内联的 RSI / MACD / Bollinger Bands 计算抽到 `src/analytics/technical_indicators.py`（80+ 行下沉，加 8 条烟测）。
- `IndustryAnalyzer`（2152 行）的纯模块级与 @staticmethod 助手抽到 `src/analytics/industry/{computations,heatmap_history}.py`，公开类外形完全不变（2152 → 2004 行，加 9 条隔离测试）。

### Documentation

- `DEPLOYMENT.md` 新增"异步任务队列"章节，明确 Celery + Redis 在生产环境是事实上的必备组件。
- `DEPLOYMENT.md` 新增"数据库迁移"章节，描述 `alembic stamp head` / `alembic upgrade` 的引导流程。

## v5.0.0 (2026-04-18)
- 公开仓正式收敛为 `策略回测 / 实时行情 / 行业热度` 三块能力，`定价研究`、`上帝视角`、`研究工作台` 与 `Quant Lab` 已迁移到私有 companion repo `super-pricing-system`
- 前端公开入口只保留 `backtest / realtime / industry`，历史系统页旧链接会自动回落到 `backtest`
- 后端公开路由不再挂载 `/pricing/*`、`/macro*`、`/research-workbench/*`、`/quant-lab/*` 与 `/alt-data/*`
- `realtime` 提醒命中接口继续兼容旧客户端契约，但 `create_workbench_task` 字段现在仅保留兼容语义，公开仓会忽略该值，不再创建系统侧任务
- 仓库文档与测试元数据同步收口：README、结构说明、API 文档、E2E package 名称和发布说明已全部对齐新的双仓边界

## v4.0.0 (2026-04-14)
- 基础设施层正式产品化：新增 `Infrastructure` API、认证令牌、持久化状态、Redis/Celery 任务队列、通知能力与 TimescaleDB schema，并补齐迁移与健康检查脚本
- Quant Lab 升级为独立量化实验台，覆盖策略优化、批量回测、基准对比、组合实验、Walk-Forward、风险中心、交易日志、告警编排与估值实验等新工作流
- GodEye 从宏观错误定价扩展到结构性衰败与部门混乱监控，新增 people / governance / execution / physical / evidence 维度雷达、部门执行混乱看板、贸易论点跟踪与物理世界观测面板
- 研究运营链路继续深度模块化：Research Workbench、实时复盘、行业研究、跨市场分析与定价研究新增更多状态持久化、异步处理、复制分享与上下文切换能力

## v3.9.0 (2026-04-02)
- 将宏观错误定价正式扩展为 6 因子可靠度引擎，新增利率曲线压力、信用利差压力与汇率错配三类因子，并补齐冲突、覆盖、时滞、漂移、反转前兆、政策源健康度与输入可靠度诊断
- 定价研究完成后端支撑层与前端展示层模块化拆分，补齐标的检索、同行候选池、基准因子摘要、敏感性/估值支撑解释，让 CAPM / FF / DCF / Gap Analysis 的结果更稳定且更易扩展
- 实时行情页升级为“数据流 + 派生状态 + 分享模板”结构，复盘快照与时间线开始版本化管理，诊断开关、导出与分享文案更一致，相关 WebSocket / contract 测试同步补齐
- 行业研究与工作台继续产品化：行业自选/保存视图/提醒阈值支持后端同步与导入导出，行业成分股构建增加流式状态反馈，GodEye 与 Research Workbench 进一步拆分为独立模块

## v3.8.0 (2026-04-01)
- 将研究运营闭环从“状态提示”升级为“动作姿势”：GodEye、Cross-Market 与 Research Workbench 现已统一区分降级运行、自动降级、核心腿受压、复核语境切换与输入可靠度变化，并给出明确的下一步动作建议
- 为 pricing、backtest、realtime、industry 并行模块补齐统一的结果姿势与行动提示层，支持从结果页直接判断“推进执行清单 / 先复核假设 / 继续观察补证”
- 扩展实时复盘与提醒管理能力：复盘快照与时间线容量提升，提醒支持条件筛选、批量启停/重置/删除，实时详情页保留跨标的对比选择记忆
- 高级回测实验台继续模块化，模板管理、研究洞察、跨市场诊断与研究剧本联动更稳定，定价研究也新增“切换到跨市场验证”的判定与原因解释

## v3.7.0 (2026-03-27)
- 将另类数据与宏观因子升级为可追溯证据质量引擎，新增实体统一、来源可信度、冲突/漂移/断流/跨源确认、一致度、反转前兆与因子共振判断
- 政策公开源升级为官方 feed + 正文抓取 + source health 诊断，政策源退化现已直接影响宏观因子有效置信度与跨市场研究输入质量
- 跨市场模板推荐与回测解释补齐 selection quality、ranking penalty、bias compression、core leg pressure 与 auto-downgrade 逻辑，默认模板选择会主动避开受压主题
- GodEye 与 Research Workbench 打通研究运营闭环，支持共振驱动、政策源驱动、自动降级、核心腿受压等任务优先级、直达 deep link 与版本对比解释

## v3.6.0 (2026-03-20)
- 打通 GodEye、跨市场模板推荐与研究工作台，新增“主导叙事切换”预警与直达跨市场剧本入口
- 将宏观因子与另类数据正式映射为跨市场模板的动态权重偏置，回测结果开始区分模板原始权重与信号驱动后的有效权重
- 升级跨市场执行研究层，补齐 execution plan、集中度、lot efficiency、rebalance cadence 与 stress test 诊断
- 强化研究工作台的快照解释与版本对比，支持比较 recommendation、allocation mode、bias、dominant driver、theme core/support 等主题变化

## v3.5.0 (2026-03-18)
- 重建实时行情深度详情，恢复实时快照、多维分析与 AI 预测联动
- 优化实时行情与分析页前端加载速度，补齐懒加载、请求去重与测试回归
- 打通交易 WebSocket 快照与广播，交易弹窗开始直接消费单条实时 quote 与账户推送
- 提升回测结果兼容性与展示一致性，补齐历史、导出和前端工作台契约

## v3.4.1 (2026-03-18)
- 修复策略回测收益率归零、历史快照异常和策略对比失败问题
- 统一回测结果契约，补齐历史、报告、导出和前端展示字段兼容
- 升级策略回测工作台界面、图表与中文文案，并修复策略对比中文报告导出

## v3.4.0 (2026-03-17)
- 新增研究工作台，支持后端持久化研究任务卡
- 打通 GodEye、定价研究、跨市场回测之间的保存与重开闭环
- 增加研究剧本与工作台联动，形成可持续推进的研究流

## v3.3.0 (2026-03-16)
- 优化 GitHub 仓库首页展示与 README 信息结构
- 新增项目界面截图与本地体验引导
- 补充贡献指南并统一版本元数据

## v3.2.0 (2025-12-24)
- 回测与分析相关 API 稳定化
- 引入多数据源适配结构（providers）
- 新增回测历史与报告导出能力

## v3.1.0 (2025-09-09)
- 安全与代码质量修复
- 基础性能与缓存优化

## 说明
- 版本号以项目根目录 `VERSION` 文件为准
- 可运行 `python scripts/sync_version.py` 同步前端元数据
- 文档更新时间与代码版本可能不同步，以代码为准

---

**最后更新**: 2026-04-18
