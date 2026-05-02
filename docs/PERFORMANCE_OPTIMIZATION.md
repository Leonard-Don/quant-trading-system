# 性能优化指南

聚焦三块:**回测吞吐**、**数据获取延迟**、**前端首屏 / 交互**。每条建议都给出当前实现位置 + 度量手段 + 推荐 SLA。

---

## 1. 当前性能基线(参考值)

| 场景 | p50 | p95 | 备注 |
|------|-----|-----|------|
| 主回测端点(单策略,1 年日线) | ~600ms | ~1.5s | `tests/integration/test_backtest_perf.py` 跟踪 |
| 行业热力图接口 | ~200ms | ~600ms | 命中缓存 |
| 行业热力图(冷启动) | ~3s | ~8s | 多 provider 串行 |
| WebSocket 行情推送 | <50ms | <200ms | 单广播 |
| 前端首屏 LCP | ~1.2s | ~2.5s | 本地 lighthouse |

> **CI 中 `tests/integration/test_backtest_perf.py` 设了 < 2s 的 SLA**(Phase 3 引入)。基线退化时 PR 会被打回。

---

## 2. 缓存层级

### 2.1 三层结构

```
请求
  │
  ▼
[L1 进程内 LRU]  ── 命中:返回(<1ms)
  │ miss
  ▼
[L2 磁盘 JSON]   ── cache/*.json,跨进程持久(~5ms)
  │ miss
  ▼
[L3 Redis(可选)]── 集群共享,TTL 控制(~10ms)
  │ miss
  ▼
[Provider]       ── yfinance / akshare / sina / ...
```

### 2.2 关键代码点

| 文件 | 职责 |
|------|------|
| `src/utils/cache.py` | L1 LRU + L2 磁盘 JSON 实现 |
| `src/data/data_manager.py:_cache_key_template` | 统一 key 生成 |
| `src/data/realtime_manager.py:_inflight_lock` | 防止同一请求并发拉取 |
| `backend/app/api/v1/endpoints/industry.py:_get_endpoint_cache` | 端点级别缓存 |

### 2.3 调优旋钮

```bash
# .env
DATA_CACHE_SIZE=500              # L1 LRU 容量(条目数)
CACHE_TTL=3600                   # 默认 TTL(秒)
CACHE_MAX_MEMORY_ITEMS=1000      # L1 上限
CACHE_CLEANUP_INTERVAL=3600      # 后台清理周期
```

**经验值**:
- 日线行情:TTL `86400` (24h)
- 实时行情:TTL `5` ~ `15` (秒)
- 行业热力:TTL `300` (5min)
- 龙头股估值:TTL `1800` (30min)

不同数据特性混在同一 TTL 是当前最大的优化机会(参见 P0 改进项)。

---

## 3. 并发模型

### 3.1 后端

| 场景 | 实现 | 配置 |
|------|------|------|
| HTTP 路由 | uvicorn + asyncio | `MAX_WORKERS=4` |
| 数据 fetch 并行 | `concurrent.futures.ThreadPoolExecutor` | `ASYNC_POOL_SIZE=10` |
| 批量回测 | `ProcessPoolExecutor`(可选)/ `ThreadPoolExecutor` | `BatchBacktester(max_workers=N)` |
| 异步任务 | Celery + Redis | `CELERY_WORKER_CONCURRENCY=4` |
| 定时任务 | APScheduler | 全局单例 |

### 3.2 阻塞调用搬到 executor

任何同步外部调用(`requests`、文件 IO、CPU 密集计算)在路由 handler 里**必须**包到 `run_in_executor`,否则会阻塞事件循环:

```python
# ✅ 正确
result = await asyncio.get_event_loop().run_in_executor(
    None, blocking_fetch, symbol
)

# ❌ 错误(会阻塞所有并发请求)
result = blocking_fetch(symbol)
```

### 3.3 进程池 vs 线程池

| 选择 | 场景 | 例子 |
|------|------|------|
| 线程池 | IO 密集(网络、磁盘) | 数据 provider 拉取 |
| 进程池 | CPU 密集(向量化、ML) | 蒙特卡洛模拟、特征工程 |
| asyncio | 已经支持 async 的库 | aiohttp、httpx、aioredis |

---

## 4. 数据获取优化

### 4.1 批量接口优先

不要在循环里调单 symbol 的 fetch:

```python
# ❌ N+1
for symbol in symbols:
    data[symbol] = provider.get_history(symbol)

# ✅ 一次拿所有
data = provider.get_history_bulk(symbols)
```

### 4.2 增量拉取

`src/data/data_manager.py` 已支持基于上次 `last_modified` 的增量同步。在 `.env` 中:

```bash
DATA_INCREMENTAL_FETCH=true
DATA_REFRESH_INTERVAL=300  # 全量刷新最大间隔
```

### 4.3 Provider 选择

| 数据 | 首选 | 备选 |
|------|------|------|
| A 股日线 | akshare | sina |
| A 股实时 | sina_ths | akshare |
| 美股 | yfinance | alpha_vantage |
| 全球指数 | twelvedata | yfinance |
| 商品 | commodity_provider | — |

故障切换在 `src/data/providers/` 工厂内自动完成,Phase 4 后加入断路器避免雪崩。

---

## 5. 回测加速

### 5.1 向量化优先

| 改动 | 加速 |
|------|------|
| 用 `numpy.where` 取代 for-loop 信号生成 | 5-30x |
| `pandas.rolling` 取代滑窗手写 | 3-10x |
| `numpy.cumsum`/`cumprod` 算 PnL | 2-5x |

### 5.2 批量并行

```python
from src.backtest.batch_backtester import BatchBacktester

bb = BatchBacktester(max_workers=8, use_processes=True)
results = bb.run_grid([{"strategy": "ma", "fast": f, "slow": s}
                       for f in [5, 10, 20] for s in [50, 100, 200]])
```

### 5.3 跳过早期失败

`Backtester` 支持 `early_exit_on_drawdown` 和 `min_trades_required`,Walk-Forward 会大量中断糟糕参数,显著缩短网格搜索时间。

---

## 6. 前端

### 6.1 已做

- React 18 自动批处理 + concurrent rendering
- 路由懒加载(`React.lazy + Suspense`,见 `frontend/src/App.js`)
- 图表用 `lightweight-charts`(WebGL,比 recharts 快)
- WebSocket 增量更新,行情面板不全量重渲染

### 6.2 可优化

- **虚拟滚动**:行业排行榜 / 历史回测列表使用 `react-window`,长列表 > 200 条后必备
- **memoize 重计算**:`useMemo` 包裹快照对比、收益曲线归一化
- **代码分包**:`webpack-bundle-analyzer` 检查首屏 chunk > 500KB 的依赖,懒加载移除
- **图片资产**:`docs/screenshots` 中 PNG 应转 WebP,体积 -60%

### 6.3 度量

```bash
cd frontend
npm run build
npx serve -s build &
npx lighthouse http://localhost:3000 --view
```

目标:Performance ≥ 90,LCP < 2.5s,TBT < 200ms。

---

## 7. 性能回归测试

### 7.1 本地

```bash
# 单跑性能套件
pytest -m perf --benchmark-only -v

# 对比上次基线
pytest -m perf --benchmark-compare=0001
```

### 7.2 CI

`.github/workflows/ci.yml` 中 `perf` job(Phase 3 引入)在每次 PR 上运行 `tests/integration/test_backtest_perf.py`。退化超过 20% 自动 fail。

### 7.3 性能压测

```bash
# 全链路压测
python scripts/performance_test.py --concurrency 50 --duration 60s
```

---

## 8. 故障诊断 cheat sheet

| 症状 | 可能原因 | 第一手段 |
|------|---------|---------|
| API p95 突然 > 5s | 缓存击穿 / provider 慢 | 看 `data_provider_request_duration` |
| 内存持续上涨 | LRU 容量过大 / DataFrame 没释放 | `py-spy dump --pid <pid>` + `memory_profiler` |
| Celery worker 堆积 | concurrency 太低 / 死锁 | `celery -A backend.app.core.celery_app inspect active` |
| 前端首屏慢 | bundle 太大 / API 串行 | lighthouse + Network tab |

---

**最后更新**: 2026-05-02
