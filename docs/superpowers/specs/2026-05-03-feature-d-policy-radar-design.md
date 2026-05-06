# Feature D — Policy Radar API + UI (设计文档)

- 日期: 2026-05-03
- 范围: 把已就绪的 `PolicySignalProvider` 搬到 HTTP / 前端表面
- 状态: 用户已确认全权决策

## 调查结论

后端 **完全就绪**：

- `src/data/alternative/policy_radar/policy_signals.py` 实现 `PolicySignalProvider(BaseAltDataProvider)`，跑完 fetch → parse(NLP) → normalize → to_signal 四步管道
- 已在 `AltDataManager` 注册（name=`policy_radar`），有 60 分钟 TTL 缓存
- `to_signal` 输出：
  ```python
  {
    "category": "policy",
    "score": float,                           # 综合得分
    "industry_signals": {                     # 按行业聚合
      "新能源": {"avg_impact": 0.34, "mentions": 5, "signal": "bullish"},
      ...
    },
    "policy_count": int,
    "source_health": {                        # 数据源健康度
      "ndrc": {"level": "healthy", "full_text_ratio": 0.85, ...},
      ...
    },
  }
  ```
- 单条记录（`AltDataRecord`）结构：`{timestamp, source, raw_value: {title, summary, excerpt, policy_shift, will_intensity, industry_impact}, metadata: {link, detail_url, ...}, tags: [industry,...], normalized_score, confidence}`
- `AltDataManager` 通过 `_bootstrap_from_snapshots()` 从磁盘缓存加载，**无需现场抓取**也能给数据；`get_alt_signals(category="policy")` 是一行调用
- 前端已有 `getIndustryHeatmap` 等同领域 API client，可直接添加 policy_radar 客户端方法

**前端 0 行**：无 policy 相关组件、无 API client、无 view 入口。

## 设计

### 后端：新增 `backend/app/api/v1/endpoints/policy_radar.py`

两个 read-only 端点：

```
GET /policy-radar/signal
  返回：当前 policy signal 全量（industry_signals + source_health + policy_count + last_refresh）
  实现：alt_manager.get_alt_signals(category="policy")，提取 signals[0] 作为 policy 主信号
  缓存：依赖 AltDataManager 自身的 60 分钟 TTL
  失败：返回空骨架 {industry_signals: {}, policy_count: 0, source_health: {}}，HTTP 200

GET /policy-radar/records?industry=<name?>&timeframe=<7d|30d?>&limit=<int?=50>
  返回：政策记录列表，按时间倒序
  支持：可选 industry 标签过滤；可选 timeframe；limit ≤ 200
  实现：alt_manager.get_records(category="policy", timeframe=...) → 过滤 industry → to_dict()
```

为什么不用 POST：纯 read，全部用 GET 让浏览器/Swagger 直接联调。

注册到 `backend/app/api/v1/api.py`：

```python
api_router.include_router(
    policy_radar.router, prefix="/policy-radar", tags=["Policy Radar"]
)
```

### 后端：fallback 安全网

如果 `AltDataManager` 初始化失败（依赖 NLP API key / 网络），endpoint 必须返回 200 + 空骨架而非 500。这与项目"本地优先"基调一致——少量数据仍能展示，缺失时 UI 显示 `policy_count: 0` 即可。用 `try/except` 包住 manager 调用。

### 前端：API client

在 `frontend/src/services/api.js` 增加：

```js
export const getPolicyRadarSignal = async () => {
    const response = await api.get('/policy-radar/signal');
    return response.data;
};

export const getPolicyRadarRecords = async ({ industry, timeframe = '7d', limit = 50 } = {}) => {
    const response = await api.get('/policy-radar/records', {
        params: { industry, timeframe, limit },
    });
    return response.data;
};
```

### 前端：`PolicyRadarPanel` 组件

新建 `frontend/src/components/IndustryDashboard/PolicyRadarPanel.js`（**先放工作区子目录而非顶层 components/，避免再制造一个超大组件**）。

功能（v0）：

1. 顶部小卡片：政策记录总数 + 最近更新时间 + 数据源健康度图标
2. 行业信号 strip：按 `industry_signals` 排序展示前 8 个，带情绪色（bullish 红 / neutral 灰 / bearish 绿）
3. 最近政策列表：最多 10 条，每条显示日期 / 来源 / 标题 / 影响行业 tag / 跳转链接
4. 失败容忍：endpoint 返回空 → 显示 `<Empty>` 占位 + 一句"政策数据未就绪，可在管理后台触发刷新"
5. 不引入新依赖；纯 antd 组件

挂载位置：作为 `IndustryDashboard` 的一个新 tab `?subtab=policy`，与现有 heatmap/ranking/leader 平级。先不做 tab——直接在底部加一个 collapsible 段落，最小变更。

### 测试

**后端**：

- `tests/unit/test_policy_radar_endpoint.py` — mock `alt_manager.get_alt_signals` 返回 stub 数据，断言 endpoint 形状；额外覆盖 manager 抛异常时 endpoint 仍返回空骨架
- ~3 个用例

**前端**：

- `frontend/src/__tests__/policy-radar-panel.test.js` — 用 RTL 渲染组件，mock API 返回数据，断言行业信号 / 最近政策列表正确出现；mock API 抛错，断言 `<Empty>` 占位
- ~3 个用例

## 不在范围内（明确排除）

- 不触发实际 NLP / 爬虫管道（依赖 API key + 外部源，不在 v0 责任域）
- 不写入 / 修改 alt_data 持久化层
- 不接 WebSocket 实时推送（policy 数据天然 hourly 节奏，HTTP poll 足够）
- 不做政策事件详情页 / drill-down（点击外链跳转就够）
- 不接 IndustryHeatmap 的颜色叠加（属于 D2 阶段，本期不做）

## 验证标准

| 编号 | 条件 |
|------|------|
| D1.B | `pytest tests/unit/test_policy_radar_endpoint.py -q` 通过；3 个用例都绿 |
| D1.F | `CI=1 npm test -- --runInBand --watchAll=false --testPathPattern=policy-radar-panel` 通过 |
| D1.整 | 后端 497 + 前端 255 测试全绿；新增不破坏老测试 |
| 手验 | 启动后访问 `http://localhost:8000/docs`，能在 Swagger UI 看到 `/policy-radar/*` 两个端点；前端 `?view=industry` 页面底部能看到 PolicyRadarPanel |

## 风险

- **低**：纯 read endpoint，不改任何已有路径
- **可能漏点**：`AltDataManager` 单例初始化耗时——首次访问可能慢。可接受，依赖现有 `_bootstrap_from_snapshots()` 走磁盘缓存而非重新抓取
- **NLP 依赖问题**：`PolicyNLPAnalyzer` 默认 `mode=local` 时不需要 API key；外部抓取通过 `PolicyCrawler` 可选启动。endpoint 不主动触发 fetch，仅读已缓存内容

## 实施顺序

1. 后端 endpoint + 单元测试 → commit
2. 前端 API client + 组件 + 单元测试 → commit
3. 把组件挂到 IndustryDashboard 底部 → commit（独立以便回滚）
