# Batch C — Integration Test Reinforcement (设计文档)

- 日期: 2026-05-03
- 范围: 量化交易系统集成测试薄弱区补强
- 状态: 用户已确认全权决策，无需逐步审批

## 背景

5 月 3 日评估指出 `tests/integration/` 当前仅 5 个测试文件（`test_api.py` / `test_backtest_perf.py` / `test_realtime_contracts.py` / `test_research_journal_contracts.py` / `test_strategy_comparison.py`），其中：

- `test_backtest_perf.py` 是 SLA / benchmark 性能测试，不是功能集成测试
- 其余四个都聚焦 **HTTP / WS 契约**，没有覆盖 `src/` 内部的跨模块协作

而代码体量重灾区是 `src/data/providers/`（8 个 provider + 工厂 + 熔断器）和 `src/backtest/`（14 个模块）。这两个区域的内部协作目前完全没有集成测试。

> 当前回归只能在生产或 E2E 阶段才暴露，回归成本偏高。

## 设计原则

- **目标不是覆盖率最大化**，而是补盖最高价值的"跨模块边界行为"。两个高质量集成测试胜过 10 个浅层用例。
- **不打网络**。所有外部依赖通过子类化 `BaseDataProvider` 或注入 mock provider 实现。
- **不引入新依赖**，复用 pytest + pandas + 现有 `src/` 类。
- 集成测试速度目标：单个 < 1 秒；不打 `@pytest.mark.slow`。

## 子任务

### C1. `tests/integration/test_provider_failover.py`

**覆盖目标**：`DataProviderFactory.get_historical_data` 多 provider 故障转移逻辑。

**关键路径**：
1. 注册 3 个 mock provider（`MockProviderA / B / C`，priority 分别为 1 / 2 / 3）。
2. A 抛 `RuntimeError("upstream timeout")` → factory 进入下一个。
3. B 返回空 DataFrame → factory 视为失败、继续。
4. C 返回正常 OHLCV → factory 返回该结果。

**断言**：
- 返回的 DataFrame 来自 C（通过特征列识别，例如 `df.attrs["source"] = "C"`）；
- A / B / C 的 `get_historical_data` 各被调用 1 次；
- factory 的内部日志或 errors 列表反映 A / B 失败。

**额外覆盖**：
- `fallback_enabled=False` 时第一个失败立即抛出。
- 全部失败时返回空 DataFrame（不抛）。

### C2. `tests/integration/test_backtest_pipeline.py`

**覆盖目标**：`DataManager → Strategy → Backtester` 端到端协作，验证三者的接口形状契合。

**关键路径**：
1. 实例化 `DataManager(use_provider_factory=False)`，monkeypatch `_fetch_yahoo_historical_data` 让它返回固定 OHLCV 合成数据（避免触网络）。
2. 调用 `data_manager.get_historical_data("TEST", ...)` 拿到 DataFrame。
3. 用 `MovingAverageCrossover` 跑 `Backtester.run(strategy, df)`。
4. 断言结果字典包含 `total_return / sharpe_ratio / max_drawdown / trades` 等字段，且数值合理（finite、非空）。

**断言**：
- DataManager 输出的 DataFrame 列含 `open / high / low / close / volume`（小写规范化）；
- Backtester 不会抛出；
- `result.metrics.total_return` 是 finite 数；
- `result.trades` 列表长度 ≥ 0。

**为什么选 MovingAverageCrossover**：策略简单稳定，已被单元测试 + perf 测试覆盖，集成测试只需要它"能正常生成信号"即可，不需要再校验策略本身正确性。

### 不在范围内

- 不测试单个 provider 的网络抓取行为（属于 `tests/unit/test_yahoo_provider.py` 等单元测试领域）；
- 不补 `cross-market` 跨市场回测的集成测试（已有 `test_cross_market_backtester.py` 单元测试 + 端点契约测试）；
- 不补 `WalkForward` / `BatchBacktester` 的集成测试（后续如有需要再立批次）。

## 验证标准

| 编号 | 条件 |
|------|------|
| C1 | `pytest tests/integration/test_provider_failover.py -q` 通过；用例不联网 |
| C2 | `pytest tests/integration/test_backtest_pipeline.py -q` 通过；用例不联网；运行时长 < 2 秒 |
| 总 | `pytest tests/integration/ -q` 整体仍然全绿（不破坏原有 5 个文件） |

## 风险

- 低。仅新增测试文件，不改产线代码。
- 唯一潜在坑：`DataManager._fetch_yahoo_historical_data` 是私有方法，monkeypatch 私有实现细节属于"白盒"测试。若后续重构方法名，集成测试会失败。已在测试中加注释说明依赖点，并在断言失败时给出明确提示。

## 实施顺序

C1 → C2，单 commit（"test: add provider failover and backtest pipeline integration tests"）。
