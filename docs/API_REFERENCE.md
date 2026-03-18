# API参考文档

## 概述

- **应用版本**: 3.4.1
- **API版本**: v1
- **基础URL**: `http://localhost:8000`
- **认证方式**: 无（开发默认）
- **数据格式**: JSON
- **字符编码**: UTF-8
- **默认限流**: 100 次/分钟（按客户端）

> 完整请求/响应模型以 `docs/openapi.json` 或运行服务后的 `/docs` 为准。WebSocket 端点不在 OpenAPI 中导出，单独记录在本文档。

## 基础端点

### 健康检查
- `GET /health` 基础健康检查

### 系统与运维
- `GET /system/status` 系统状态（支持 `?detailed=false`）
- `GET /system/performance` 性能指标概览
- `GET /system/health-check` 综合健康检查（当前为简化版本）
- `GET /system/metrics` 详细性能指标
- `GET /system/alerts/summary` 告警摘要
- `POST /system/alerts/{alert_index}/resolve` 处理告警
- `GET /system/dependencies` 依赖连通性检查

## 数据与行情

### 市场数据
- `POST /market-data` 获取历史数据
- `GET /market-data/search` 搜索股票代码

请求示例（历史数据）：
```json
{
  "symbol": "AAPL",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "interval": "1d",
  "period": null
}
```

### 实时报价
- `GET /realtime/quote/{symbol}` 单个实时报价
- `GET /realtime/quotes?symbols=AAPL,MSFT` 批量实时报价

统一报价字段：
- `symbol, price, change, change_percent, volume, high, low, open, previous_close, bid, ask, timestamp, source`

### 实时订阅
- `WS /ws/quotes` 正式实时订阅入口
- 订阅消息：`{"action":"subscribe","symbol":"AAPL"}` 或 `{"action":"subscribe","symbols":["AAPL","MSFT"]}`
- 取消订阅：`{"action":"unsubscribe","symbol":"AAPL"}`
- 心跳：`{"action":"ping"}`

WebSocket 消息：
- 订阅确认：`{"type":"subscription","action":"subscribed","symbol":"AAPL","duplicate":false}`
- 取消确认：`{"type":"subscription","action":"unsubscribed","symbol":"AAPL","noop":false}`
- 行情推送：`{"type":"quote","symbol":"AAPL","data":{...},"timestamp":"..."}`
- 心跳响应：`{"type":"pong","timestamp":...}`

### 兼容层接口
- `POST /realtime/subscribe`
- `POST /realtime/unsubscribe`

兼容层说明：
- 仅用于兼容旧客户端，不维护持久订阅态
- 返回订阅确认、规范化后的 symbol 列表，以及正式 WebSocket 入口 `/ws/quotes`
- 响应包含 `deprecated: true`

兼容层请求示例：
```json
{
  "symbols": ["aapl", "msft"]
}
```

兼容层响应示例：
```json
{
  "success": true,
  "action": "subscribed",
  "symbols": ["AAPL", "MSFT"],
  "deprecated": true,
  "websocket": "/ws/quotes"
}
```

## 策略与回测

### 策略
- `GET /strategies` 获取策略列表

### 回测
- `POST /backtest` 运行回测
- `GET /backtest/compare` 多策略对比（`symbol`、`strategies` 等参数）
- `GET /backtest/history` 回测历史
- `GET /backtest/history/stats` 回测统计
- `GET /backtest/history/{record_id}` 回测记录详情
- `DELETE /backtest/history/{record_id}` 删除回测记录
- `POST /backtest/report` 生成回测报告 PDF
- `POST /backtest/report/base64` 生成回测报告（Base64）

回测请求示例：
```json
{
  "symbol": "AAPL",
  "strategy": "moving_average",
  "parameters": {"fast_period": 20, "slow_period": 50},
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 10000,
  "commission": 0.001,
  "slippage": 0.001
}
```

## 分析与优化

### 分析
- `POST /analysis/analyze` 趋势分析
- `POST /analysis/comprehensive` 综合分析
- `POST /analysis/volume-price` 量价分析
- `POST /analysis/sentiment` 情绪分析
- `POST /analysis/patterns` 形态识别
- `POST /analysis/prediction` 价格预测
- `POST /analysis/correlation` 多股票相关性分析
- `GET /analysis/models` 可用模型列表
- `POST /analysis/prediction/compare` 多模型预测对比
- `POST /analysis/prediction/lstm` LSTM 预测
- `POST /analysis/train/all` 训练所有模型

### 投资组合优化
- `POST /optimization/optimize`

请求示例：
```json
{
  "symbols": ["AAPL", "MSFT"],
  "period": "1y",
  "objective": "max_sharpe"
}
```

## 交易模拟

- `GET /trade/portfolio` 获取当前投资组合
- `POST /trade/execute` 执行交易
- `GET /trade/history` 获取交易历史
- `POST /trade/reset` 重置账户

## 行业分析

- `GET /industry/industries/hot`
- `GET /industry/industries/{industry_name}/stocks`
- `GET /industry/industries/heatmap`
- `GET /industry/industries/{industry_name}/trend`
- `GET /industry/industries/clusters`
- `GET /industry/leaders`
- `GET /industry/leaders/{symbol}/detail`
- `GET /industry/health`

## 错误代码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 422 | 请求数据验证失败 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |

---

**最后更新**: 2026-03-16
