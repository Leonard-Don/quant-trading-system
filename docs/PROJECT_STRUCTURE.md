# 公开主仓结构说明

当前 `quant-trading-system` 已收敛为一个研究档案入口加三块 GitHub-facing 主工作区：

- `今日研究`
- `策略回测`
- `实时行情`
- `行业热度`

## 入口层

```text
frontend/src/App.js
├── today
├── backtest
├── realtime
└── industry
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
├── /trade
├── /industry
├── /events
├── /cross-market
├── /infrastructure
└── /research-journal
```

已从当前主仓移出的公开路由：

- `/pricing/*`
- `/macro*`
- `/research-workbench/*`
- `/quant-lab/*`
- `/alt-data/*`

## 关键行为调整

- `realtime` 的提醒命中接口保留原始契约，但不再触发 Quant Lab 总线。
- `industry` 只保留页面内告警和桌面通知，不再自动创建工作台任务。
- `research-journal` 只聚合公开仓内的回测快照、实时复盘、提醒和行业观察，不引入私有研究工作台。
- `cross-market` 保留在回测模块中，但不再依赖工作台队列和宏观错误定价草稿。

## 私有系统仓

拆出的系统模块保留在私有仓：

- `super-pricing-system`

该仓当前以 GitHub private repo 形式维护，并继续承接系统部分开发。
