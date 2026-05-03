# Batch B — Industry Layer Charter (设计文档)

- 日期: 2026-05-03
- 范围: 厘清 `src/analytics/industry_analyzer.py` ↔ `backend/app/services/industry/runtime.py` ↔ `backend/app/api/v1/endpoints/industry.py` 的层级关系
- 状态: 用户已确认全权决策

## 调查结论 vs 评估假设

5 月 3 日的项目评估指出：

> `src/analytics/industry_analyzer.py` (2,146 行) 与 `backend/app/services/industry/runtime.py` (2,479 行) + `endpoints/industry.py` (1,669 行) 边界模糊，industry 是当前最重的领域却也是最容易重复实现的地方。

实际深度阅读后，这个判断**有偏差**：

1. `industry_analyzer.py` 是**纯领域分析**：`IndustryAnalyzer` 类有 9 个公共方法（`rank_industries / cluster_hot_industries / get_industry_heatmap_data / get_industry_trend / get_industry_rotation / analyze_money_flow / calculate_industry_historical_volatility / calculate_industry_momentum / build_rank_score_breakdown`），全部接收 provider、返回 DataFrame / dict。无 HTTP / 缓存 / 调度概念。

2. `services/industry/runtime.py` 是**纯编排层**：~50 个单一职责的 helper（缓存键生成、预热调度、payload 序列化、in-flight 去重、fallback 兜底、prewarm 任务、磁盘持久化等），**只在 1418 行实例化一次** `IndustryAnalyzer`。无领域算法。

3. `endpoints/industry.py` 134–625 行那一长串看似重复的 `_foo(*args, **kwargs)` stub，**不是死代码**——它是一层"测试 patching 兼容面"。`tests/unit/test_industry_leader_endpoint.py` 直接 patch `endpoint.industry._foo`，由 `_sync_industry_runtime_state()` 把 patch 双向同步到 `runtime` 模块。设计目的是让单元测试能在 endpoint 层注入 mock，而不必关心调用是从 endpoint 函数发出还是从 runtime 内部回调。

**因此层级实际是清楚的**：

```
HTTP request
    │
    ▼
endpoints/industry.py
    │  ├── @router.get(...) routes (628+ 行)
    │  └── test-patching shim (134–625 行) ─── _sync_industry_runtime_state()
    │                                              ↕  双向 setattr
    ▼                                              ↕
backend/app/services/industry/runtime.py  ◄────────┘
    │   缓存 / 调度 / 持久化 / payload 序列化 / fallback
    │
    ▼
src/analytics/industry_analyzer.py        ─────► 领域算法（rank / heatmap / trend …）
src/analytics/industry_stock_details.py   ─────► 股票详情字段规范化
    │
    ▼
DataProvider（akshare / sina_ths / yahoo / …）
```

## 真正的问题

不是分层，而是**单文件体量**：

- `runtime.py` 2,479 行集中了正交的多个关注点（heatmap / leader / stock-rows / cache / prewarm / persistence），按"主题"切分成多个子模块更友善。
- `industry_analyzer.py` 2,146 行将 9 个分析方法塞进单类，按"分析类型"也可拆分。

但是：

- `runtime.py` 中有大量**模块级共享状态**（`_endpoint_cache` / `_parity_cache` / `_heatmap_history_lock` / `_stocks_full_build_inflight` 等），通过 `setattr(industry_runtime, name, ...)` 在 shim 中双向同步。拆分到子模块后这套同步机制会失效，必须重写 shim。
- 该模块由 `tests/unit/test_industry_leader_endpoint.py` 等密集 patch，重构会引发大面积测试调整。
- 收益是"读起来更清楚"，无运行时收益、无功能变化。

**风险/收益比让大刀阔斧的拆分不值得**。Batch D（前端巨型组件拆分）才是真正高回报的体量重构，因为前端的子组件没有这种模块级状态耦合。

## 子任务（修订版）

### B1. 编写层级架构文档

新增 `docs/architecture/industry-layering.md`：

- 解释三层职责
- 解释 endpoint shim 为什么存在（测试 patching）
- 解释 `_sync_industry_runtime_state()` 的双向同步机制
- 标注后续可演进方向（按主题拆 `runtime.py`、抽离 `IndustryAnalyzer` 子方法）但**不在本批次执行**

### B2. 在三个层级文件顶部加一句指针注释

每个文件顶部 docstring 末尾追加一句"层级总览见 `docs/architecture/industry-layering.md`"，让任何进来读代码的人都能立刻找到说明。

### 不在范围内（明确排除）

- 不拆 `runtime.py`：状态耦合 + 大面积测试 patch 风险高
- 不拆 `industry_analyzer.py`：单类内聚良好，没有非内聚证据
- 不动 endpoint shim 设计：当前服务的测试覆盖密度不允许做无功能变化的重构
- 不重写 `_INDUSTRY_SERVICE_HELPERS` 的 70 个手动条目：可以用 introspection 自动生成，但这是风格优化，不在层级梳理范围内

## 验证标准

| 编号 | 条件 |
|------|------|
| B1 | `docs/architecture/industry-layering.md` 存在；用 mermaid 或 ASCII 表达层级关系；解释 shim |
| B2 | 三个文件顶部 docstring 末尾各加一句指针，无功能影响 |
| 总 | `pytest tests/unit/test_industry_leader_endpoint.py tests/unit/test_industry_analyzer.py -q` 通过 |

## 风险

- B1: 零（纯文档）
- B2: 极低（只在 docstring 末尾加一句字符串，无逻辑改动）

## 实施顺序

B1 → B2，单 commit（"docs: document industry analytics ↔ runtime ↔ endpoint layering"）。
