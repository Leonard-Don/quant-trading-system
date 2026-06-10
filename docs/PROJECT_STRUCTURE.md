# 公开主仓结构说明

当前 `quant-trading-system` 已收敛为一个研究档案入口（今日研究）加四块 GitHub-facing 主工作区，外加一个低波动选股视图：

- `今日研究`
- `策略回测`
- `实时行情`
- `行业热度`
- `纸面账户`
- `低波动选股`（`?view=lowvol`，呈现已验证的 low_volatility@20 信号）

## 入口层

```text
frontend/src/App.jsx
├── today
├── backtest
├── realtime
├── industry
├── paper
└── lowvol
```

- 旧的 `pricing / godsEye / workbench / quantlab` view 不再公开。
- 访问旧 view 时会自动回落到 `backtest`。

## 后端公开路由

```text
backend/app/api/v1/api.py
├── /market-data
├── /strategies
├── /backtest
├── /system
├── /realtime
├── /analysis
├── /optimization
├── /industry
├── /events
├── /cross-market
├── /infrastructure
├── /research-journal
├── /policy-radar
└── /paper
```

已从当前主仓移出的公开路由：

- `/pricing/*`
- `/macro*`
- `/research-workbench/*`
- `/quant-lab/*`
- `/alt-data/*`
- `/trade/*`（2026-06-05 并入 `/paper/*` 后整体移除，#107/#108）
- `/etf-rotation/*`（ETF 轮动板块整体下线，见 CHANGELOG Unreleased）

## 关键行为调整

- `realtime` 的提醒命中接口保留原始契约，但不再触发 Quant Lab 总线。
- `industry` 只保留页面内告警和桌面通知，不再自动创建工作台任务。
- `research-journal` 只聚合公开仓内的回测快照、实时复盘、提醒和行业观察，不引入私有研究工作台。
- `cross-market` 保留在回测模块中，但不再依赖工作台队列和宏观错误定价草稿。

## 公开导出层（Phase F1）

- `data/public/` —— 新增的「committed runtime artifacts」目录。`data/` 顶层在 `.gitignore` 中默认忽略，但 `data/public/*.json` 通过白名单允许提交。当前唯一文件：
    - `data/public/quant_summary.json` —— 由 `scripts/export_public_summary.py` 蒸馏出的小型公开摘要（schema_version=1，~1.4 KB），下游消费者（sibling 项目 `cn-altdata-brief` 等）`git clone` 本仓库就能读到，无需访问 `cache/` 或拉起后端。详见 `docs/CHANGELOG.md::Unreleased` 与 `docs/MAINTENANCE_GUIDE.md` 的 cron 条目。

## 私有系统仓

拆出的系统模块保留在私有仓：

- `super-pricing-system`

该仓当前以 GitHub private repo 形式维护，并继续承接系统部分开发。
