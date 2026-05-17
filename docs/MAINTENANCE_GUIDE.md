# 维护指南

本文档涵盖 quant-trading-system 在长期运行下的运维操作:健康检查、日志轮换、数据备份、缓存治理、监控、排障。

---

## 1. 健康检查

### 1.1 一键全链路检查

```bash
python3 ./scripts/health_check.py
```

该脚本会依次验证:
- 后端 `/health` 端点(默认 `localhost:8000`)
- 前端可达性(默认 `localhost:3000`)
- TimescaleDB 连接(若 `DATABASE_URL` 已设)
- Redis 连接(若 `REDIS_URL` 已设)
- 关键数据 provider 心跳(yfinance / akshare)

### 1.2 单点检查

```bash
# 后端
curl -fsS http://localhost:8000/health

# 前端
curl -fsS http://localhost:3000
```

---

## 2. 日志

### 2.1 默认位置

| 来源 | 路径 | 说明 |
|------|------|------|
| 后端应用 | `logs/system.log` | 主日志,所有模块 |
| 后端启动 | `logs/backend.log` | uvicorn stdout / stderr |
| Celery worker | `logs/celery.log` | 异步任务 |
| 前端启动 | `logs/frontend.log` | npm start 输出 |

### 2.2 日志轮换(关键)

**裸机部署用 logrotate**——`logs/system.log` 在长期运行下会膨胀到几十/上百 MB(实测仓内 `system.log.1` 已达 10MB)。

`/etc/logrotate.d/quant-trading-system`:

```
/path/to/quant-trading-system/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    size 50M
}
```

### 2.3 日志级别动态调整

通过环境变量,无需重启:

```bash
# 临时升到 DEBUG
LOG_LEVEL=DEBUG python backend/main.py

# 生产推荐
LOG_LEVEL=WARNING ENVIRONMENT=production python backend/main.py
```

---

## 3. 缓存治理

### 3.1 缓存层级

1. **L1 — 内存 LRU** (`src/utils/cache.py`):进程内,重启即失效
2. **L2 — 磁盘 JSON** (`cache/*.json`):跨进程,重启保留
3. **L3 — Redis** (可选,需 `REDIS_URL`):多进程共享,带 TTL

### 3.2 手动清理

```bash
# 清磁盘缓存(安全,会自动重建)
rm -rf cache/*.json

# 清 Redis(危险,会让正在跑的回测任务丢中间结果)
redis-cli FLUSHDB

# 用脚本一并清 + 重启
./scripts/cleanup.sh
```

### 3.3 缓存命中诊断

启用 `CACHE_DEBUG=true`,后端日志会输出每次 `data_manager.get_*` 的命中层级。长时间命中率 < 60% 通常意味着 TTL 过短或 key 设计不够稳定。

---

## 4. 数据备份

### 4.1 外部 PostgreSQL / TimescaleDB

```bash
# 完整逻辑备份(慢但兼容性最好)
pg_dump "$DATABASE_URL" -Fc -f ./backups/quant-$(date +%F).dump

# 还原
pg_restore --clean --dbname "$DATABASE_URL" ./backups/quant-2026-05-02.dump
```

### 4.2 用户数据 / 研究档案

```bash
tar czf backups/data-$(date +%F).tgz data/ output/
```

### 4.3 自动化(crontab 模板)

```cron
# 每日 02:30 备份 DB,保留 14 天
30 2 * * * cd /opt/quant && ./scripts/backup_db.sh && find backups -name '*.dump' -mtime +14 -delete

# 每 6 小时刷新 policy_radar 另类数据快照,驱动 /policy-radar/* 端点
# (会触发 PolicySignalProvider.run_pipeline 实抓 + NLP,落盘到 cache/alt_data/providers/policy_radar.json)
0 */6 * * * cd /opt/quant && /usr/bin/env python scripts/refresh_policy_radar.py --force >> logs/refresh_policy_radar.log 2>&1

# 每小时刷新 data/public/quant_summary.json (Phase F1 公开摘要导出)
# 把 cache/alt_data/* + data/industry/heatmap_history.json + data/paper_trading/* +
# ~/.config/etf-rotation/audit.jsonl 蒸馏成一份小型公开 JSON,供 sibling 项目
# cn-altdata-brief 在 GitHub Actions 里 git clone 后直接消费。
# 本项目 Celery 仅用于回测任务卸载,不做 beat 调度,所以这里走 cron。
0 * * * * cd /opt/quant && ./scripts/refresh_public_summary.sh >> logs/export_public_summary.log 2>&1
```

> `refresh_policy_radar.py` 是 `/policy-radar/signal` 与 `/policy-radar/records` 端点的喂料入口。
> 没有这条 cron(或者手动执行)时,端点会按"本地优先"协议优雅降级为 `available:false`;
> cron 跑过一次后,端点立即翻成 `available:true` 并返回真实政策记录。
>
> `refresh_public_summary.sh` 是 `scripts/export_public_summary.py` 的 thin wrapper(自动激活 `.venv/`)。
> 输出 `data/public/quant_summary.json` 是 committable 工件,会被 git 跟踪;
> 不跑这条 cron 时下游项目会读到最后一次手动导出的快照,数据不会自动过期失败 —— 只会变陈旧。
> 手动一次性运行:`./scripts/refresh_public_summary.sh` 或 `./scripts/refresh_public_summary.sh --print` 输出到 stdout 调试。

---

## 5. 监控

### 5.1 Prometheus 指标

后端在 `prometheus_client` 自动暴露 `/metrics`(端口同 API)。关键序列:

| 指标 | 含义 | 告警阈值 |
|------|------|---------|
| `http_request_duration_seconds` | API 延迟 | p99 > 2s |
| `data_provider_failures_total{provider}` | 数据源失败次数 | 5min 增量 > 5 |
| `backtest_duration_seconds` | 主回测耗时 | p95 > 30s |
| `cache_hit_ratio` | 缓存命中率 | < 0.6 |
| `celery_task_runtime_seconds` | 异步任务耗时 | p95 > 60s |

### 5.2 系统资源

`scripts/health_check.py` 同时上报 CPU / 内存 / 磁盘水位,环境变量可调阈值:

```bash
CPU_WARNING_THRESHOLD=80.0
MEMORY_WARNING_THRESHOLD=85.0
DISK_WARNING_THRESHOLD=90.0
```

---

## 6. 数据源治理

### 6.1 故障转移

`src/data/data_manager.py` 在 provider 失败时按以下顺序回退(由 `src/data/providers/` 工厂决定):

1. 主 provider(如 A 股 → akshare)
2. 备 provider(如 sina)
3. 硬编码兜底(`alt_data` 或最后一次成功缓存)

### 6.2 断路器(Phase 4 后启用)

每个 provider 有独立的 `CircuitBreaker` 状态:

```bash
# 查看断路器状态
curl http://localhost:8000/api/v1/system/providers/status
```

返回示例:
```json
{
  "akshare": {"state": "closed", "failures": 0, "last_failure": null},
  "yahoo":   {"state": "open",   "failures": 5, "last_failure": "2026-05-02T14:00:00Z"},
  "sina":    {"state": "half_open", "next_attempt_at": "2026-05-02T14:30:00Z"}
}
```

`open` 持续 > 30 分钟应人工介入(网站接口大概率改版)。

---

## 7. 常见问题

### 7.1 接口报 429

触发限流。默认 `RATE_LIMIT_REQUESTS=100 / RATE_LIMIT_WINDOW=60s`。批量回测前可调高到 1000 / 60。

### 7.2 回测结果不一致

- 检查 `DATA_CACHE_SIZE`、`CACHE_TTL`,确认未读到陈旧数据
- 关闭随机种子(`RANDOM_SEED=42`)排查 ML 策略

### 7.3 WebSocket 频繁断线

- 检查反向代理 `proxy_read_timeout` ≥ 3600s
- 后端日志查 `connection_manager` 警告

### 7.4 前端找不到后端

- `frontend/.env`(或构建参数)中的 `REACT_APP_API_URL` 是否指向了真实地址
- 同域反向代理部署时，确认 `/api` 和 WebSocket 路径都转发到后端

### 7.5 日志显示 "ImportError: cannot import name '...'(circular import)"

**通常发生在 ruff/isort 自动重排导入后**。回退该文件的导入顺序,或把循环依赖项改为函数内 lazy import。

---

## 8. 升级流程

```bash
# 1. 拉取
git fetch && git pull --rebase

# 2. 同步依赖
pip install -r requirements-dev.txt
cd frontend && npm install --legacy-peer-deps && cd ..

# 3. 运行迁移(若 alembic 有新 head)
alembic upgrade head

# 4. 跑回归
pytest tests/unit -q
cd frontend && CI=1 npm test -- --runInBand --watchAll=false

# 5. 重启服务
./scripts/stop_system.sh
./scripts/start_system.sh
```

---

## 9. CI 质量门槛 (lint + coverage)

`.github/workflows/ci.yml` 里有两道"防回涨"门槛,只增不减,绝对不允许在不
对齐基线的情况下放宽:

### 9.1 Ruff 基线门 (`scripts/check_ruff_baseline.py`)

- 基线文件: `scripts/ruff_baseline_count.txt` (单整数, 首版 = 3102)
- CI 行为: `lint` job 跑 `ruff check src backend scripts tests` 并比对计数,
  发现数 **大于** 基线即 fail
- **不要求清零** —— 只要求"不再增长"。新写的代码必须不引入新发现。

**本地复跑(每次 push 前推荐):**

```bash
python scripts/check_ruff_baseline.py
# 通过: Ruff baseline gate passed: current=3102 baseline=3102 resolved=0 new=0
# 失败: 列出 top-10 规则码, 提示要么修要么 --write-baseline
```

**修了一批后,降低基线 (这是健康行为, 多做):**

```bash
# 比如顺手 ruff check --fix 干掉一批 PIE790
ruff check src backend scripts tests --fix --select=PIE790
python scripts/check_ruff_baseline.py --write-baseline
git add scripts/ruff_baseline_count.txt
git commit -m "chore(lint): tighten ruff baseline to <new-N>"
```

**绝对不要在没有清理动作的情况下抬高基线** —— 那等于把回归静音化。
如果新代码必须引入暂时无法修的发现 (例如第三方库的兼容垫片),
先评估能否走 `# noqa` + 文件内 `# noqa` 注释,或在 `pyproject.toml`
`[tool.ruff.lint] ignore` 加个明确条目,再调基线。

### 9.2 Coverage 阈值 (`--cov-fail-under`)

- 当前阈值: 60% (实测 61%, 1 个百分点缓冲, 2026-05-16 锁定)
- CI 行为: `backend` job 里 `pytest ... --cov-fail-under=60`,
  覆盖率跌破 60% 即 fail
- **只升不降** —— 阈值随补测试自然抬高,每隔几周复测一次

**本地复跑:**

```bash
pytest tests/unit tests/integration -m "not perf" \
  --cov=src --cov=backend --cov-report=term --cov-fail-under=60 -q
# 末尾会打印 TOTAL ... 61%
```

**抬高阈值:**

```bash
# 看实测百分比, 然后改 .github/workflows/ci.yml 里的 --cov-fail-under=N
# (保留 1pt 缓冲, 比如实测 65% → 设 64)
```

---

**最后更新**: 2026-05-16
