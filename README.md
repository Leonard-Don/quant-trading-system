<div align="center">

# quant-trading-system

**一个基于 FastAPI + React 的量化交易研究平台，聚焦 `策略回测`、`实时行情`、`行业热度` 三块公开能力。**  
*A public-facing quantitative research workspace focused on backtesting, realtime market monitoring, and industry heat analysis.*

**当前版本：`v5.0.0`** · [查看更新日志](docs/CHANGELOG.md)

[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?style=flat-square&logo=react)](https://reactjs.org)
[![CI](https://img.shields.io/github/actions/workflow/status/Leonard-Don/quant-trading-system/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Leonard-Don/quant-trading-system/actions/workflows/ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/Leonard-Don/quant-trading-system?style=flat-square)](https://github.com/Leonard-Don/quant-trading-system/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen?style=flat-square)](LICENSE)

<br />

> **87+** 自动化测试 · **3** 大公开工作区 · **6** 大数据提供器 · **13** 种内置策略

[本地体验](#-本地体验) · [核心能力](#-核心能力) · [系统架构](#️-系统架构) · [快速开始](#-快速开始) · [测试验证](#-测试验证) · [API 文档](#-api-文档)

</div>

---

## 📌 仓库定位

这个仓库现在是 **GitHub-facing 主仓**，只保留三块公开能力：

- `策略回测`
- `实时行情`
- `行业热度`

原来系统里的 `定价研究`、`上帝视角`、`研究工作台`、`Quant Lab` 已经拆到本地私有系统仓 `super-pricing-system`，不再包含在这个公开仓中。

这意味着：

- 当前仓的前端公开 view 只剩 `backtest / realtime / industry`
- 当前仓的后端公开接口不再挂载 `/pricing/*`、`/macro*`、`/research-workbench/*`、`/quant-lab/*`
- 历史系统页旧链接会自动回落到 `backtest`

---

## 🧭 本地体验

> 当前不提供公开在线 Demo。请在本地同时启动前后端后体验完整功能。

<div align="center">
  <img src="docs/screenshots/product-tour-v2.png" alt="产品总览" />
  <br />
  <sub>公开仓当前聚焦策略回测、实时行情与行业热度三块能力</sub>
</div>

<br />

<div align="center">
  <img src="docs/screenshots/product-tour.gif" alt="产品动态演示" width="880" />
  <br />
  <sub>本地启动后的主要页面流转与交互预览</sub>
</div>

### 启动后可访问

| 页面 | 地址 | 说明 |
|------|------|------|
| 📊 策略回测 | `http://localhost:3000` | 单资产回测、历史记录、对比、组合优化、跨市场回测 |
| 📈 实时行情 | `http://localhost:3000?view=realtime` | 多市场行情聚合、提醒、复盘与深度详情 |
| 🔥 行业热度 | `http://localhost:3000?view=industry` | 热力图、排行榜、龙头股分析、轮动观察 |
| 📖 API 文档 | `http://localhost:8000/docs` | Swagger UI 交互式文档 |

### 推荐体验路径

1. 先进入 **行业热度**，查看热力图和排行榜，建立当下板块温度感。
2. 再切到 **实时行情**，打开指数或美股详情，查看趋势、量价、情绪和提醒。
3. 回到 **策略回测**，运行主回测或 `cross-market`，验证想法并沉淀结果。

---

## ✨ 核心能力

### 📊 策略回测

- 支持主回测、历史复盘、策略对比、组合优化和高级实验
- 保留 `cross-market` 作为公开仓的一部分
- 内置 `13` 种策略，覆盖趋势、均值回归、量价、配对交易、LSTM 等方向
- 回测结果支持收益、Sharpe、回撤、交易事件、月度收益等维度展示

### 📈 实时行情

- 多市场行情聚合，支持指数、美股、A 股、加密等分组
- 支持 WebSocket 更新、复盘快照、提醒命中历史和开发诊断
- 详情页整合趋势、量价、情绪、风险、相关性、AI 辅助分析
- 拆分后依然保留提醒记录接口，但不再向 Quant Lab 或研究工作台回流

### 🔥 行业热度

- 行业热力图支持时间窗、颜色维度、来源标签与状态条联动
- 行业排行榜支持排序、筛选、来源联动、URL 状态持久化
- 龙头股详情支持火花线、AI 洞察、竞态保护与观察列表提醒
- 拆分后保留页面内提醒和通知，不再自动创建系统侧研究任务

---

## 👀 界面预览

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/realtime-deep-detail.png" alt="实时行情深度详情" /><br />
      <b>实时行情深度详情</b><br />
      <sub>趋势、量价、情绪、风险与相关性等多维联动</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/industry-ranking-overview.png" alt="行业热度总览" /><br />
      <b>行业热度总览</b><br />
      <sub>行业评分、资金流向、板块轮动与排行榜</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/industry-heatmap-overview.png" alt="行业热力图" /><br />
      <b>行业热力图</b><br />
      <sub>Treemap 交互视图，支持多维度切换与状态条定位</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/leader-stock-detail.png" alt="龙头股详情" /><br />
      <b>龙头股详情</b><br />
      <sub>从行业到个股的多维分析链路</sub>
    </td>
  </tr>
</table>

---

## 🏗️ 系统架构

### 整体结构

```text
quant-trading-system/
├── backend/                    # FastAPI 后端
│   └── app/
│       ├── api/v1/endpoints/   # backtest / realtime / industry 等公开接口
│       ├── core/               # 配置、错误处理、任务队列、限流状态
│       ├── services/           # 实时提醒、偏好、复盘、交易流
│       └── websocket/          # WebSocket 路由与连接管理
├── frontend/                   # React 18 前端
│   └── src/
│       ├── components/         # 回测 / 实时 / 行业相关组件
│       ├── hooks/              # 实时偏好、实验工作区等自定义 Hook
│       ├── services/           # API 与 WebSocket 客户端
│       └── utils/              # 路由、快照对比、格式化工具
├── src/                        # 核心算法库
│   ├── analytics/              # 行业分析、估值、趋势、信号等
│   ├── backtest/               # 主回测、跨市场回测、风险管理、执行引擎
│   ├── data/                   # 数据提供器、实时管理、另类数据基础设施
│   ├── strategy/               # 内置策略实现
│   └── trading/                # 交易执行与跨市场资产建模
├── tests/                      # pytest + Playwright
└── scripts/                    # 启停、检查、文档生成、验证脚本
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI + Uvicorn | 异步 RESTful API，自动 OpenAPI 文档 |
| 前端 | React 18 + Ant Design 5 | 懒加载、响应式布局、主题支持 |
| 实时通信 | WebSocket | 实时行情与交易流广播 |
| 数据获取 | yfinance · AKShare · Sina · TwelveData · AlphaVantage | 多 provider 聚合与故障回退 |
| 图表可视化 | Recharts + Ant Design Charts | 回测图表、热力图、雷达图、走势线 |
| 测试 | pytest + Playwright + Jest | 单元 / 集成 / 浏览器 E2E |

---

## 🚀 快速开始

### 环境要求

- Python `3.9+`
- Node.js `16+`
- npm `8+`

### 一键启动

```bash
git clone https://github.com/Leonard-Don/quant-trading-system.git
cd quant-trading-system
./scripts/start_system.sh
```

### 分步启动

```bash
# 后端
pip install -r requirements-dev.txt
python scripts/start_backend.py

# 前端（新终端）
cd frontend
npm install
npm start
```

### 健康检查

```bash
python3 ./scripts/health_check.py
```

---

## 🧪 测试验证

### 前端定向测试

```bash
cd frontend
CI=1 npm test -- --runInBand --runTestsByPath \
  src/__tests__/app-routing.test.js \
  src/__tests__/research-context.test.js \
  src/__tests__/cross-market-backtest-panel.test.js \
  src/__tests__/realtime-panel.test.js \
  src/__tests__/industry-heatmap.test.js
```

### 后端定向测试

```bash
pytest -q tests/integration/test_realtime_contracts.py
```

### 浏览器 E2E

```bash
cd tests/e2e
npm run verify:realtime
npm run verify:industry
```

---

## 📖 API 文档

启动后端后可访问：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- 详细参考: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- Postman Collection: [docs/postman_collection.json](docs/postman_collection.json)

---

## 🔀 拆分说明

本仓已经完成“公开三块主仓 + 本地私有系统仓”的拆分：

- 当前公开仓只负责 `策略回测 / 实时行情 / 行业热度`
- 系统模块已经迁移到本地私有仓 `super-pricing-system`
- 当前仓允许保留必要的共享底层代码副本，但不再公开系统模块入口和 API

如果你想继续开发系统侧能力，请切换到本地私有仓；如果你要继续维护 GitHub 公开仓，请只在这个仓里处理三块主仓相关功能。
