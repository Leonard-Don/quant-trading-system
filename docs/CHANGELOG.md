# 更新日志

## Unreleased

### Features

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
