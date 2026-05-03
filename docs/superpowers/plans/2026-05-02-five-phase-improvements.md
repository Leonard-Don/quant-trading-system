# 量化系统五阶段改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 解决项目评估中识别出的五项关键债务:工程化基础缺失、文档薄弱、性能基线缺失、数据源脆弱、巨型文件难维护。

**Architecture:** 五阶段独立交付,各自一个或多个 commit。Phase 1-4 可在单 session 完成;Phase 5 三个巨型文件每个单独成 commit,可独立 review。

**Tech Stack:** ruff / pre-commit / pyproject.toml / pytest-benchmark / FastAPI services 分层。

**Branch policy:** 工作直接在 `main`(单人项目),每 phase 独立 commit。

---

## Phase 1 — 工程化基础

**目的:** 把已经声明在 `requirements-dev.txt` 但未配置的 pre-commit 真正落地;用 ruff 一并替换 flake8/isort/部分 black 功能;为后续所有提交建立质量门。

**Files:**
- Create: `pyproject.toml` — 统一 black/ruff/mypy/pytest/isort 配置
- Create: `.pre-commit-config.yaml` — pre-commit hook 链
- Modify: `requirements-dev.txt` — 加 `ruff`,移除 `flake8` / `isort` / `autopep8`(被 ruff 覆盖)
- Modify: `pytest.ini` — 迁移到 pyproject 后保留兼容入口或删除

### Tasks

- [x] **1.1 创建 pyproject.toml** — 包含 `[tool.ruff]`(line-length 100, target-version py313, 启用 E/F/W/I/UP/B/SIM 规则集,排除 frontend/.playwright/cache/data/.pytest_cache)、`[tool.black]`、`[tool.mypy]`(ignore_missing_imports=true 暂时)、`[tool.pytest.ini_options]`(从 pytest.ini 迁移)
- [x] **1.2 创建 .pre-commit-config.yaml** — hooks: pre-commit-hooks(trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files), ruff (lint + format), black, mypy(可选 stage=manual)
- [x] **1.3 更新 requirements-dev.txt** — 加 `ruff>=0.6.0`;flake8/isort/autopep8 标注为待删除(先注释,确认不破坏 CI 后再删)
- [x] **1.4 删除 pytest.ini**(配置已迁移到 pyproject.toml)
- [x] **1.5 安装并跑首次 ruff** — `pip install ruff && ruff check . --fix --unsafe-fixes` → 接受可自动修复的改动
- [x] **1.6 跑测试确认无回归** — `pytest tests/unit -q`
- [x] **1.7 安装 pre-commit hook + 跑一次** — `pre-commit install && pre-commit run --all-files` (允许 black 一次性格式化)
- [x] **1.8 commit** — `chore: add pyproject + ruff + pre-commit config`

---

## Phase 2 — 文档与运行说明充实

**目的:** 让"5 分钟跑起来"成立;把空架子文档(MAINTENANCE/PERFORMANCE)填实;新增 ARCHITECTURE.md 与 EXTENDING.md。仓库不再维护本地基础设施编排，外部数据库和 broker 通过环境变量接入。

**Files:**
- Modify: `docs/DEPLOYMENT.md` — 加本地进程部署与外部服务接入章节
- Modify: `docs/MAINTENANCE_GUIDE.md` — 扩写日志轮换、备份、健康检查、常见排障
- Modify: `docs/PERFORMANCE_OPTIMIZATION.md` — 扩写缓存策略、并发模型、性能基准、优化点
- Create: `docs/ARCHITECTURE.md` — 分层、模块依赖、数据流、关键决策(Mermaid)
- Create: `docs/EXTENDING.md` — 添加新策略/数据源/指标的 step-by-step

### Tasks

- [x] **2.1 扩写 docs/DEPLOYMENT.md** — 本地进程部署、外部数据库 / broker 环境变量、worker 启动
- [x] **2.2 扩写 docs/MAINTENANCE_GUIDE.md** — 日志轮换 logrotate 模板、cache/data 备份脚本、外部 DB 备份、健康检查检查项、排障 FAQ
- [x] **2.3 扩写 docs/PERFORMANCE_OPTIMIZATION.md** — 缓存层级图、并发模型、批量接口、关键基准
- [x] **2.4 创建 docs/ARCHITECTURE.md** — 模块图(Mermaid)、关键决策记录、数据流
- [x] **2.5 创建 docs/EXTENDING.md** — 添加新策略 / 新 provider / 新 endpoint 的 walkthrough
- [x] **2.6 commit** — `docs: flesh out ops and architecture docs`

---

## Phase 3 — pytest-benchmark + 性能 SLA

**目的:** 给主回测端点设性能基线,防止重构期间引入性能衰退;e2e CI 已存在,这阶段只增 perf job。

**Files:**
- Modify: `requirements-dev.txt` — 加 `pytest-benchmark>=4.0.0`
- Create: `tests/integration/test_backtest_perf.py` — 主回测端点 SLA 测试
- Modify: `pyproject.toml` — 加 `[tool.pytest.ini_options]` markers(perf)
- Modify: `.github/workflows/ci.yml` — 加 `perf` job(可选 allow_failure)

### Tasks

- [x] **3.1 加 pytest-benchmark 到 requirements-dev.txt**
- [x] **3.2 在 pyproject.toml 注册 marker** — `markers = ["perf: marks tests as performance regression"]`
- [x] **3.3 写性能测试** — `tests/integration/test_backtest_perf.py`:对 `/api/v1/backtest/` 用 mocked yfinance 数据触发主回测,断言 < 2.0s
- [x] **3.4 本地跑** — `pytest tests/integration/test_backtest_perf.py --benchmark-only -v`
- [x] **3.5 加 CI perf job**(可 continue-on-error 试跑期间)
- [x] **3.6 commit** — `test: add backtest performance SLA + CI perf job`

---

## Phase 4 — 数据源治理(ta 移除 + 断路器)

**目的:** 移除已停更的 ta(实测项目无 import,纯 dead dep);为 provider 加统一断路器,提升 akshare/sina 失败时的系统稳定性。

**Files:**
- Modify: `requirements.txt` — 删 `ta==0.11.0`(再次 grep 确认零引用)
- Create: `src/data/providers/circuit_breaker.py` — `CircuitBreaker` 类 + `@with_circuit_breaker` 装饰器
- Modify: `src/data/providers/akshare_provider.py` — 关键 fetch 方法套断路器
- Modify: `src/data/providers/sina_ths_adapter.py` — 同上
- Create: `tests/unit/test_circuit_breaker.py` — 状态机测试

### Tasks

- [x] **4.1 二次确认 ta 零引用** — `grep -rn "import ta\|from ta" --include="*.py" src backend tests`(包括非 ^ 锚点)
- [x] **4.2 从 requirements.txt 删 `ta==0.11.0`** + commit `chore: drop unused ta dependency`
- [x] **4.3 写断路器单元测试**(TDD) — `test_circuit_breaker.py`:closed → open(N 次失败后)→ half_open(冷却后允许试探)→ closed/open
- [x] **4.4 实现 CircuitBreaker** — 状态: closed/open/half_open;`failure_threshold=5`、`recovery_timeout=60s`、`half_open_max_calls=1`;线程安全(threading.Lock)
- [x] **4.5 跑断路器测试** — `pytest tests/unit/test_circuit_breaker.py -v`
- [x] **4.6 套到 akshare/sina_ths 关键方法** — 如 `get_realtime_quotes`、`get_industry_data` 等高频外部调用点
- [x] **4.7 跑 provider 相关现有测试,确认无回归**
- [x] **4.8 commit** — `feat(data): add circuit breaker for fragile providers`

---

## Phase 5 — 拆分巨型文件

**目的:** 把三个文件拆成小颗粒,降低 endpoint 文件复杂度;此阶段是最大风险面,每个文件单独 commit,跑测试后才进入下一个。

### 5A — auth.py(1229 行)

**目的优先做 auth**:它是纯函数集合,没有路由(只导出函数),拆分风险最小,适合作为热身。

**Files:**
- Create: `backend/app/core/auth/` 目录(__init__.py 重导出原对外 API)
- Create: `backend/app/core/auth/passwords.py` — `_hash_password / _verify_password`
- Create: `backend/app/core/auth/policy.py` — `_load_policy / get_auth_policy / update_auth_policy / is_production_environment / is_auth_secret_production_ready`
- Create: `backend/app/core/auth/tokens.py` — `_b64url_encode / _b64url_decode / _hash_token / _default_access_ttl / _default_refresh_ttl / _normalize_scope_items / list_refresh_sessions`
- Create: `backend/app/core/auth/oauth_providers.py` — `_oauth_provider_preset / _env_oauth_provider_specs / list_oauth_providers / sync_env_oauth_providers / diagnose_oauth_provider / upsert_oauth_provider / _sanitize_oauth_provider`
- Create: `backend/app/core/auth/oauth_states.py` — `_find_oauth_state_record / _persist_oauth_state / _mark_oauth_state_used / _backend_public_base_url / _frontend_public_origin / _pkce_challenge`
- Create: `backend/app/core/auth/users.py` — `_find_user_record / _sanitize_user / list_local_users / upsert_local_user / authenticate_local_user`
- Create: `backend/app/core/auth/secrets.py` — `_auth_secret / _env_auth_required / _env_bool_value / _env_flag`
- Modify: `backend/app/core/auth.py` → 删除,或改为 1 行 re-export(`from backend.app.core.auth.* import *`),保后向兼容

### Tasks(5A)

- [x] **5A.1 重命名** — `git mv backend/app/core/auth.py backend/app/core/auth_legacy.py`(临时)
- [x] **5A.2 创建 auth/ package + __init__.py 重导出**(空)
- [x] **5A.3 拆 secrets.py** — 把 `_auth_secret / _env_auth_required / _env_bool_value / _env_flag` 移过去
- [x] **5A.4 拆 passwords.py** — `_hash_password / _verify_password`
- [x] **5A.5 拆 tokens.py** — token 工具
- [x] **5A.6 拆 policy.py** — policy 函数 + production 判定
- [x] **5A.7 拆 oauth_providers.py / oauth_states.py / users.py** — 按列表迁移
- [x] **5A.8 在 __init__.py 重导出所有原对外 API**(从 auth_legacy.py 提取使用方再导出)
- [x] **5A.9 删除 auth_legacy.py**
- [x] **5A.10 全量跑测试** — `pytest tests/unit tests/integration -q`
- [x] **5A.11 grep 检查所有 `from backend.app.core.auth import ...` 调用方仍能 resolve**
- [x] **5A.12 commit** — `refactor(auth): split monolithic auth.py into focused modules`

### 5B — backtest.py endpoint(2087 行)

**目的:** 把 sync 业务函数(`run_backtest_pipeline / compare_strategy_significance_sync / run_multi_period_backtest_sync / run_market_impact_analysis_sync` 等)抽到 service,endpoint 只剩路由 + 参数转换。

**Files:**
- Create: `backend/app/services/backtest/` 包
- Create: `backend/app/services/backtest/pipeline.py` — `run_backtest_pipeline`(行 276-372)
- Create: `backend/app/services/backtest/comparison.py` — `_build_comparison_entry / _normalize_compare_configs / _compare_strategies_impl / compare_strategy_significance_sync`
- Create: `backend/app/services/backtest/monte_carlo.py` — `_simulate_monte_carlo_paths / run_backtest_monte_carlo_sync / _series_from_portfolio_history / _calculate_max_drawdown_from_series 等指标 helper`
- Create: `backend/app/services/backtest/multi_period.py` — `run_multi_period_backtest_sync / _classify_market_regimes`
- Create: `backend/app/services/backtest/impact.py` — `run_market_impact_analysis_sync / _market_impact_curve / _default_market_impact_scenarios`
- Create: `backend/app/services/backtest/utils.py` — `_estimate_min_history_bars / _build_no_trade_diagnostics / _parse_iso_datetime / _resolve_date_range / _fetch_backtest_data / _create_strategy_instance / _build_batch_backtester / _strategy_factory_for_batch / _safe_sharpe`
- Modify: `backend/app/api/v1/endpoints/backtest.py` — 仅保留 router、Pydantic schemas(也可移到 schemas/)、路由 handler

### Tasks(5B)

- [x] **5B.1 创建 services/backtest/ 包**
- [x] **5B.2 抽 utils.py** — 基础工具函数(数据获取、参数解析、最小窗口估算)
- [x] **5B.3 抽 pipeline.py** — `run_backtest_pipeline`
- [x] **5B.4 抽 monte_carlo.py** — Monte Carlo 模拟与指标 helper
- [x] **5B.5 抽 comparison.py** — 对比与显著性
- [x] **5B.6 抽 multi_period.py** — 多周期 + 市场状态分类
- [x] **5B.7 抽 impact.py** — 市场冲击分析
- [x] **5B.8 endpoint 改为薄壳** — 只 import + 调用 service + 返回响应
- [x] **5B.9 全量跑测试** — `pytest tests/unit/test_backtester* tests/integration -q`
- [x] **5B.10 commit** — `refactor(backtest): extract sync logic into services package`

### 5C — industry.py endpoint(3349 行)

**目的:** 这是最大单文件。先按"职责域"分包,endpoint 只剩 ~12 个路由 + DI;helper 拆 6 个模块。

**Files:**
- Create: `backend/app/services/industry/` 包
- Create: `backend/app/services/industry/cache.py` — `_get_endpoint_cache / _set_endpoint_cache / _get_stale_endpoint_cache / _set_parity_cache / _get_parity_cache / _get_stale_parity_cache / _is_fresh_parity_entry / _get_matching_parity_cache`
- Create: `backend/app/services/industry/heatmap.py` — `_serialize_heatmap_response / _trim_heatmap_history_payload / _load_heatmap_history_from_disk / _persist_heatmap_history_to_disk / _append_heatmap_history / _build_heatmap_response_from_history / _load_live_heatmap_response / _schedule_heatmap_refresh`
- Create: `backend/app/services/industry/leaders.py` — `_normalize_sparkline_points / _load_symbol_mini_trend / _attach_leader_mini_trends / _extract_leading_stock_symbol_lookup / _collect_hot_leader_candidates / _build_leading_stock_symbol_lookup / _dedupe_leader_responses`
- Create: `backend/app/services/industry/parity.py` — `_build_parity_price_data / _build_leader_detail_fallback / _leader_detail_error_status`
- Create: `backend/app/services/industry/stocks.py` — `_get_stock_cache_keys / _build_stock_responses / _count_quick_stock_detail_fields / _promote_detail_ready_quick_rows / _load_cached_quick_valuation / _backfill_quick_rows_with_cached_valuation / _build_full_industry_stock_response / _build_quick_industry_stock_response / _get_stock_status_key / _set_stock_build_status / _get_stock_build_status / _schedule_full_stock_cache_build`
- Create: `backend/app/services/industry/trend.py` — `_coerce_trend_alignment_stock_rows / _load_trend_alignment_stock_rows / _build_trend_summary_from_stock_rows / _should_align_trend_with_stock_rows`
- Create: `backend/app/services/industry/lifecycle.py` — `_classify_industry_lifecycle / _build_industry_events / _map_industry_etfs / _cosine_similarity / _model_to_dict / _format_storage_size / _resolve_industry_profile / _resolve_symbol_with_provider / _build_hot_industry_rank_responses`
- Create: `backend/app/services/industry/dependencies.py` — `_get_or_create_provider / get_industry_analyzer / get_leader_scorer`(FastAPI Depends 用)
- Modify: `backend/app/api/v1/endpoints/industry.py` — 仅保留 12 个路由 handler

### Tasks(5C)

- [x] **5C.1 创建 services/industry/ 包**
- [x] **5C.2 抽 cache.py**(8 个函数)
- [x] **5C.3 抽 heatmap.py**(8 个函数)
- [x] **5C.4 抽 leaders.py**(7 个函数)
- [x] **5C.5 抽 parity.py**(3 个函数)
- [x] **5C.6 抽 stocks.py**(12 个函数)
- [x] **5C.7 抽 trend.py**(4 个函数)
- [x] **5C.8 抽 lifecycle.py + dependencies.py**(剩余)
- [x] **5C.9 endpoint 改为薄壳**
- [x] **5C.10 全量跑测试** — `pytest tests/unit/test_industry* tests/unit/test_industry_leader* tests/integration -q`
- [x] **5C.11 commit** — `refactor(industry): split 3349-line endpoint into focused services`

---

## Self-Review Checklist

### 覆盖性

| 评估建议 | 实施 phase |
|---|---|
| pyproject + ruff + pre-commit | Phase 1 ✓ |
| 充实运维/架构文档 | Phase 2 ✓ |
| pytest-benchmark + e2e CI | Phase 3 ✓ |
| ta → 移除 | Phase 4 ✓ |
| 数据源断路器 | Phase 4 ✓ |
| 拆 industry.py | Phase 5C ✓ |
| 拆 backtest.py | Phase 5B ✓ |
| 拆 auth.py | Phase 5A ✓ |

### 风险

- **Phase 5(拆分)是最大风险点** — 每文件单独 commit,跑测试后再合并 / 推进
- **Phase 1 的 ruff --fix --unsafe-fixes 可能改大量代码** — 先用 `--fix` 不带 unsafe,review diff 再决定
- **ta 的 grep 已确认零引用** — 风险低
- **外部服务只通过环境变量接入** — 仓库不维护本地基础设施编排

### 执行顺序

1 → 2 → 3 → 4 → 5A → 5B → 5C(由轻到重,每段独立可中止)
