# quant-trading-system（量化交易系统三块主仓）

当前仓收敛为 GitHub-facing 主仓，只保留三块核心能力：

- `策略回测`
- `实时行情`
- `行业热度`

原来的 `定价研究`、`上帝视角`、`研究工作台`、`Quant Lab` 已从当前仓入口和后端公开路由中拆出，迁移到本机本地系统仓：

- `/Users/leonardodon/PycharmProjects/super-pricing-system`

该本地系统仓已初始化为独立 Git 仓，但没有配置 `origin`，不会推送到 GitHub。

## 当前可用页面

启动后可直接访问：

| 页面 | 地址 | 说明 |
| --- | --- | --- |
| 策略回测 | `http://localhost:3000` | 单资产回测、历史、对比、组合优化、跨市场回测 |
| 实时行情 | `http://localhost:3000?view=realtime` | 多市场行情聚合、提醒、复盘 |
| 行业热度 | `http://localhost:3000?view=industry` | 热力图、排行榜、龙头股分析 |
| API 文档 | `http://localhost:8000/docs` | 当前主仓公开 API |

历史系统页的旧链接会自动回落到 `策略回测`，不会再进入已拆出的系统模块。

## 快速开始

```bash
cd /Users/leonardodon/PycharmProjects/quant-trading-system
./scripts/start_system.sh
```

健康检查：

```bash
python3 ./scripts/health_check.py
```

前端定向测试：

```bash
cd frontend
CI=1 npm test -- --runInBand --runTestsByPath \
  src/__tests__/app-routing.test.js \
  src/__tests__/research-context.test.js \
  src/__tests__/cross-market-backtest-panel.test.js
```

后端定向测试：

```bash
pytest -q tests/integration/test_realtime_contracts.py
```

浏览器 E2E：

```bash
cd tests/e2e
npm run verify:realtime
npm run verify:industry
```

## 当前仓边界

保留：

- `frontend/src/App.js` 中的 `backtest / realtime / industry`
- `backend/app/api/v1/api.py` 中公开的三块相关路由
- 回测内部的 `cross-market` tab

已去联动：

- 实时提醒命中不再发布到 Quant Lab 统一事件总线
- 行业页不再自动创建工作台任务或发布统一总线事件
- 跨市场回测不再依赖工作台队列、研究任务保存或宏观错误定价草稿

## 目录概览

```text
quant-trading-system/
├── backend/                    # FastAPI 后端
│   └── app/api/v1/             # 当前主仓公开 API
├── frontend/                   # React 前端
│   └── src/
│       ├── components/         # 回测 / 实时 / 行业相关组件
│       ├── services/           # API 调用
│       └── utils/              # 路由与通用工具
├── src/                        # 回测、数据、策略、分析等底层能力
├── tests/                      # pytest 与 E2E
└── scripts/                    # 启停、检查、辅助脚本
```

## 说明

- 当前仓仍允许保留部分共享底层代码副本，以保证三块主仓可独立运行。
- 本轮拆分不处理公共包抽取，也不推送任何远端。
- 如需继续开发已拆出的系统模块，请切换到本地仓 `super-pricing-system`。
