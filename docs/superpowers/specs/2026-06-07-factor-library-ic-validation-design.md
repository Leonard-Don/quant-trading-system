# 设计:点位时间因子库 + IC 验证(Phase 1)

> Status: approved (design), pending implementation plan
> Date: 2026-06-07
> Goal owner: Leonard-Don (single-user A-share research tool)

## 背景与目标

`comprehensive_scorer` 的综合评分目前对未来收益**几乎没有预测力**——已由点位时间 IC 校准
(`scripts/calibrate_scorer_weights.py`, PR #132)证明:现有价量/情绪/技术维度样本外 rank IC ≈ 0,
且重新加权样本外不收敛(过拟合)。

**最终目标(用户选定)**:让现有综合评分真正有预测力。
**实现路径**:构建候选因子 → 全部过 IC 框架(点位时间、样本外)→ 只保留真有 IC 的接进 scorer。

因为"接哪些因子"取决于"哪些因子真有 IC",**必须先验证再接**。故拆两阶段:

- **Phase 1(本 spec)**:点位时间数据层 + 因子库 + IC 验证引擎 → 产出**因子记分卡**。纯研究产出。
- **Phase 2(后续,门控于 Phase 1)**:把过关因子合成 `alpha` 维度接进 `comprehensive_scorer`、
  把 ~0 IC 维度降权为描述性、前端展示。其规模/形态由 Phase 1 存活因子数决定,故本 spec 不涵盖。

## Phase 1 范围

### 组件(隔离单元)

| 模块 | 职责 | 依赖 |
|---|---|---|
| `src/analytics/factors/base.py` | `Factor` 协议:`compute(panel, as_of) -> dict[symbol, float]`,只用 ≤as_of 数据;横截面工具(z-score/rank、winsorize、缺失处理) | numpy/pandas |
| `src/analytics/factors/fundamental.py` | Tushare `fina_indicator`,按 **ann_date 公告日**对齐:盈利收益率(净利/市值)、BP(净资产/市值)、ROE、毛利率、营收增速、净利增速 | factor_panel |
| `src/analytics/factors/moneyflow.py` | Tushare `moneyflow`:主力净流入比、大单净占比(N 日 trailing,只用 ≤as_of) | factor_panel |
| `src/analytics/factors/price.py` | 现有价格算:低波动(−实现波动)、换手率反转、12−1 动量、短期反转 | factor_panel |
| `src/data/factor_panel.py` | 面板构建器:universe×日期 的 OHLCV+fina_indicator+moneyflow,点位时间对齐 + **本地缓存**(复用校准脚本 checkpoint 模式) | TushareProvider |
| `src/analytics/factors/evaluation.py` | IC 引擎:每因子横截面 rank IC、ICIR、IC 衰减(多前向窗口)、逐年稳定性、换手;train/test 切分,样本外指标 | factor_panel, factors |
| `scripts/run_factor_scorecard.py` | 跑全套 → 记分卡(Markdown + JSON);CLI 配置 universe/日期/前向窗口 | 上述全部 |

### 数据层补充(`src/data/providers/tushare_provider.py`)

- `get_financial_indicators(symbol, start, end)` — `fina_indicator` 历史,**保留 `ann_date`**(点位时间门控用)。
- `get_moneyflow(symbol, start, end)` — `moneyflow` 历史。
- 复用已加的 TTL 缓存 + 每分钟限流退避(PR #101)。面板构建器对每标的**一次性拉全史并本地落盘**,
  避免重复联网。

## 严谨性(最重要 — 不能重新引入刚修掉的 look-ahead)

- **点位时间铁律**:
  - 基本面:某报告期数值仅在其 `ann_date ≤ as_of` 后可见;公告前用上一期或视为缺失。
  - 所有因子只读 `index ≤ as_of`;标签 = 严格 `> as_of` 的前向收益(默认 20 个交易日)。
  - 代码内 `assert sliced.index.max() <= as_of`。
- **接受门槛(因子过关)**:样本外 rank IC ≥ ~0.03 **且** ICIR > 0 **且** 符号在逐年子区间稳定。
- **诚实门**:若没有因子过关 → 记分卡如实报告,**Phase 2 不启动**(绝不接入假装有预测力的分)。
- **universe**:流动性筛选的务实池(默认 ~50–100 只跨行业流动性标的),**注明轻微幸存者偏差**
  (用当前流动名单近似历史池)。范围/前向窗口/universe 全部可配。
- **默认参数**:~6 年、月频 rebalance、20 个交易日前向收益、train/test 70/30 时序切分。

## 测试(TDD)

- 每因子:点位时间正确性(注入 as_of 之后的极端值,断言因子值不变)+ 已知输入的手算值。
- IC 引擎:在"合成已知关系"数据(因子与前向收益人为正相关)上断言 IC 显著为正;无关系数据 IC≈0。
- 面板:ann_date 门控正确(公告前不可见)、缓存命中、缺失/停牌处理。
- 全部离线可跑(mock Tushare;pytest-socket 兼容)。

## 明确不做(YAGNI)

- Phase 1 **不动** `comprehensive_scorer`、**不动**前端、**不做**实盘/纸面交易。
- 不做点位时间的精确历史指数成分(用流动性近似 + 注明 caveat)。
- 不做多因子加权优化的最终接入(那是 Phase 2,门控于本阶段结果)。

## 成功标准

1. 可复现的因子库 + IC 引擎 + `run_factor_scorecard.py`,离线测试全绿。
2. 一份**因子记分卡**:每个候选因子的样本内/外 rank IC、ICIR、稳定性、是否过关。
3. 点位时间正确性有测试背书(无 look-ahead)。
4. 明确结论:哪些因子值得进 Phase 2(或"都不过关"的诚实结论)。
