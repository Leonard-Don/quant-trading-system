# Industry Domain — Layering Charter

> 给后续维护者 (人类 / Claude / Copilot) 的入门说明：行业热度模块为什么涉及三个看起来"差不多"的大文件，以及它们各自的职责边界。

## 速查表

| 文件 | 行数 | 角色 | 一句话职责 |
|------|------|------|-----------|
| `src/analytics/industry_analyzer.py` | ~2150 | 领域分析核心 | 给一个 provider，返回行业排名 / 热力图 / 趋势 / 轮动等纯领域计算结果 |
| `src/analytics/industry_stock_details.py` | ~230 | 字段规范化辅助 | 把 provider 返回的股票字段统一形状（normalize / merge / backfill） |
| `backend/app/services/industry/runtime.py` | ~2480 | 编排 + 缓存 + 调度 | 缓存键、in-flight 去重、prewarm、payload 序列化、磁盘持久化、fallback 兜底 |
| `backend/app/api/v1/endpoints/industry.py` | ~1670 | HTTP 路由 + 测试 patch shim | `@router.get(...)` 路由 + 一层把 runtime 各 helper 镜像到 endpoint 模块的兼容面 |

## 调用链

```text
HTTP request
    │
    ▼
backend/app/api/v1/endpoints/industry.py
    │  ├─ @router.get(...) routes               (628+ 行)
    │  └─ test-patch shim:
    │     def _foo(*args, **kwargs):            (134–625 行)
    │         return _call_industry_helper("_foo", *args, **kwargs)
    │
    ▼ (通过 _sync_industry_runtime_state() 双向 setattr)
backend/app/services/industry/runtime.py
    │  缓存 / 调度 / 预热 / payload 组装 / 持久化 / fallback
    │  仅在 ~1418 行实例化 IndustryAnalyzer 一次
    │
    ▼
src/analytics/industry_analyzer.py
    │  9 个公共方法 (rank_industries / cluster_hot_industries /
    │   get_industry_heatmap_data / get_industry_trend /
    │   get_industry_rotation / analyze_money_flow /
    │   calculate_industry_historical_volatility /
    │   calculate_industry_momentum / build_rank_score_breakdown)
    │
    ▼
src/data/providers/* (akshare / sina_ths / yahoo / ...)
```

## 三层各自该 / 不该做什么

### `src/analytics/industry_analyzer.py` (领域核心)

✅ **该做**：行业排名打分、聚类、热力图数据源构造、趋势/轮动/资金流计算、波动率与动量等**纯函数式领域算法**。给定 provider 与参数，返回 DataFrame 或 dict。

❌ **不该做**：HTTP 概念、缓存、prewarm、调度、payload 序列化、错误响应封装。该层不知道自己在哪里被调用。

### `backend/app/services/industry/runtime.py` (编排层)

✅ **该做**：

- 缓存（`_endpoint_cache`、`_parity_cache`、`_heatmap_history`）的读写、stale 兜底
- 在 ThreadPoolExecutor 上调度 prewarm / 后台计算
- 多次请求同一资源时的 in-flight 去重
- 把领域返回的 DataFrame 变成 Pydantic response 模型
- Yahoo / 备用 provider 的降级 fallback
- 磁盘持久化 (`_load_heatmap_history_from_disk` / `_persist_heatmap_history_to_disk`)

❌ **不该做**：领域算法（要调用 `IndustryAnalyzer`，不要在这里重写排名公式）；HTTP 层概念（不要在这里写 `HTTPException`，由 endpoint 层把抛出的结构化错误翻译成 HTTP 状态码）。

### `backend/app/api/v1/endpoints/industry.py` (HTTP + shim)

✅ **该做**：

- 真正的 `@router.get(...)` 装饰路由
- 把 runtime 抛出的领域错误翻译成 `HTTPException` / `JSONResponse`
- 提供 134–625 行那层 stub，供单元测试 monkeypatch 使用

❌ **不该做**：在路由函数体内做缓存、调度或领域计算。这些应该委托给 runtime helper。

## 为什么有那 500 行 stub？

`endpoints/industry.py` 134–625 行有 ~70 个看起来纯属转发的 helper：

```python
def _load_symbol_mini_trend(*args, **kwargs):
    return _call_industry_helper("_load_symbol_mini_trend", *args, **kwargs)
```

它们存在的唯一原因是**让单元测试可以从 endpoint 模块层面注入 mock**：

```python
# tests/unit/test_industry_leader_endpoint.py
from backend.app.api.v1.endpoints import industry as industry_endpoint

def test_xxx(monkeypatch):
    monkeypatch.setattr(industry_endpoint, "_load_symbol_mini_trend", fake_loader)
    # ↑ 这条 patch 通过 _sync_industry_runtime_state() 自动同步到 runtime 模块
    ...
```

`_sync_industry_runtime_state()` 在每次 `_call_industry_helper` 调用前执行，把 endpoint 模块上的 patch 同步给 runtime，反向也同步 runtime 内部更新（如 `_endpoint_cache` 引用替换）。这样无论调用从哪一层发起，都能看到测试注入的 mock。

**移除这层 shim = 让单元测试要么大改、要么失去 patch 能力**，目前不动。

## 已知的、可演进但本期不做的方向

1. **拆 `runtime.py` (~2480 行) 按主题切到子模块**：`heatmap.py` / `leader.py` / `stock_rows.py` / `caching.py` / `prewarm.py`。阻塞点是模块级共享状态（`_endpoint_cache` 等）通过 `setattr(industry_runtime, name, ...)` 双向同步。拆完后必须重写 shim 同步逻辑，且大量单元测试 patch 路径会跟着变。
2. **`_INDUSTRY_SERVICE_HELPERS` 的 70 个手动映射可以用 introspection 自动生成**：减少漂移风险但属于风格优化。
3. **`industry_analyzer.py` 9 个公共方法可以拆成多个分析器**（如 `RankAnalyzer / TrendAnalyzer / RotationAnalyzer`）。当前 9 个方法在 `IndustryAnalyzer` 单类内通过共享 provider 和缓存协作，拆开后需要新的协调对象。

这些都是**纯结构化重构**，不会带来功能或性能改进。仅在维护成本变得不可接受时再启动，每次单独立批次评估。

## 修改本模块时的检查点

- 改 `industry_analyzer.py` → 跑 `tests/unit/test_industry_analyzer.py` + `tests/unit/test_industry_analyzer_fast_path.py`
- 改 `runtime.py` → 跑 `tests/unit/test_industry_leader_endpoint.py` + `tests/unit/test_runtime_state.py` + `tests/unit/test_industry_stock_details.py`
- 改 `endpoints/industry.py` → 跑 `tests/integration/test_api.py` + 上述全部
- 如果改动到的 helper 在 `_INDUSTRY_SERVICE_HELPERS` 里，**必须**同步更新 endpoint 文件顶部的字典，否则 shim 同步会漏掉新 helper
