# 二次开发指南

如何给系统添加新策略、新数据源、新指标、新 API 端点 —— step-by-step,假设你刚 clone 完。

---

## 0. 前置准备

```bash
git clone https://github.com/Leonard-Don/quant-trading-system.git
cd quant-trading-system
pip install -r requirements-dev.txt
pre-commit install   # 启用质量门(可选,目前 codebase 仍有 lint 债务)
```

---

## 1. 添加一个新策略

> 目标:添加 `KAMAStrategy`(Kaufman 自适应均线)。

### Step 1.1 实现策略类

新文件 `src/strategy/kama.py`:

```python
from __future__ import annotations
import numpy as np
import pandas as pd
from src.strategy.base import BaseStrategy


class KAMAStrategy(BaseStrategy):
    """Kaufman Adaptive Moving Average."""

    def __init__(self, period: int = 10, fast: int = 2, slow: int = 30) -> None:
        super().__init__(name="kama", parameters={"period": period, "fast": fast, "slow": slow})
        self.period = period
        self.fast_sc = 2.0 / (fast + 1)
        self.slow_sc = 2.0 / (slow + 1)

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        close = prices["close"].astype(float)
        change = (close - close.shift(self.period)).abs()
        volatility = close.diff().abs().rolling(self.period).sum()
        er = (change / volatility).fillna(0.0)
        sc = (er * (self.fast_sc - self.slow_sc) + self.slow_sc) ** 2

        kama = pd.Series(np.nan, index=close.index)
        kama.iloc[self.period] = close.iloc[self.period]
        for i in range(self.period + 1, len(close)):
            kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i - 1])

        signal = pd.Series(0, index=close.index)
        signal[close > kama] = 1
        signal[close < kama] = -1
        signal = signal.diff().fillna(0).clip(-1, 1)
        return pd.DataFrame({"signal": signal, "indicator": kama})
```

### Step 1.2 注册到工厂

`src/strategy/__init__.py`:

```python
from .kama import KAMAStrategy
__all__ = [..., "KAMAStrategy"]
```

`backend/app/api/v1/endpoints/backtest.py` 的 `STRATEGIES` 字典加一行:

```python
"kama": KAMAStrategy,
```

### Step 1.3 写单元测试

`tests/unit/test_strategies.py`(已存在,append):

```python
def test_kama_signals_on_trending_data():
    prices = make_trending_prices(days=200)
    strat = KAMAStrategy(period=10)
    signals = strat.generate_signals(prices)
    assert (signals["signal"] != 0).sum() > 0
    assert signals["indicator"].notna().sum() > 100
```

### Step 1.4 跑回测

```bash
pytest tests/unit/test_strategies.py::test_kama_signals_on_trending_data -v
```

通过后 commit:`feat(strategy): add KAMA adaptive moving average`。

---

## 2. 添加一个新数据 Provider

> 目标:添加 `EastMoneyProvider`(东财 A 股)。

### Step 2.1 创建 provider

`src/data/providers/eastmoney_provider.py`:

```python
from __future__ import annotations
import pandas as pd
import requests
from src.data.providers.base_provider import BaseDataProvider


class EastMoneyProvider(BaseDataProvider):
    name = "eastmoney"
    BASE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    def get_history(self, symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
        # 实现:调用 self._session.get(...)、解析、返回标准 DataFrame
        # DataFrame 必须包含: index=DatetimeIndex(name="date"),
        # columns=["open","high","low","close","volume"]
        ...

    def is_available(self) -> bool:
        try:
            self._session.get(self.BASE_URL, timeout=3).raise_for_status()
            return True
        except Exception:
            return False
```

### Step 2.2 注册到工厂

`src/data/providers/__init__.py`:

```python
from .eastmoney_provider import EastMoneyProvider
PROVIDERS["eastmoney"] = EastMoneyProvider
```

### Step 2.3 加入故障转移链

`src/data/data_manager.py` 内 `PROVIDER_PRIORITY`(或等价配置):

```python
PROVIDER_PRIORITY = {
    "a_share": ["akshare", "eastmoney", "sina"],
    "us_stock": ["yahoo", "alpha_vantage"],
    ...
}
```

### Step 2.4 写测试

`tests/unit/test_eastmoney_provider.py`:

```python
import pytest
from unittest.mock import patch
from src.data.providers.eastmoney_provider import EastMoneyProvider


@patch("src.data.providers.eastmoney_provider.requests.Session.get")
def test_history_parses_canonical_columns(mock_get):
    mock_get.return_value.json.return_value = {...}
    df = EastMoneyProvider().get_history("000001.SZ", "2025-01-01", "2025-01-31")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "date"
```

### Step 2.5 套断路器(Phase 4 后)

```python
from src.data.providers.circuit_breaker import with_circuit_breaker

class EastMoneyProvider(BaseDataProvider):
    @with_circuit_breaker(failure_threshold=5, recovery_timeout=60)
    def get_history(self, ...): ...
```

---

## 3. 添加一个新 API 端点

> 目标:添加 `GET /api/v1/strategies/{name}/parameter-ranges`。

### Step 3.1 在 `backend/app/schemas/` 定义 IO

`backend/app/schemas/strategies.py`:

```python
from pydantic import BaseModel, Field

class ParameterRange(BaseModel):
    name: str
    type: str = Field(..., description="int / float / str / bool")
    min: float | None = None
    max: float | None = None
    default: object
    description: str | None = None

class ParameterRangesResponse(BaseModel):
    strategy: str
    parameters: list[ParameterRange]
```

### Step 3.2 写 service 函数

`backend/app/services/strategies.py`:

```python
from src.strategy import StrategyValidator

def get_parameter_ranges(strategy_name: str) -> list[ParameterRange]:
    spec = StrategyValidator.get_spec(strategy_name)
    return [
        ParameterRange(name=p.name, type=p.type, min=p.min, max=p.max,
                       default=p.default, description=p.help)
        for p in spec.parameters
    ]
```

### Step 3.3 在路由 endpoint 暴露

`backend/app/api/v1/endpoints/strategies.py`:

```python
@router.get(
    "/{name}/parameter-ranges",
    response_model=ParameterRangesResponse,
    summary="返回某策略的参数范围",
)
async def parameter_ranges(name: str):
    try:
        params = get_parameter_ranges(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"strategy {name!r} unknown")
    return ParameterRangesResponse(strategy=name, parameters=params)
```

### Step 3.4 写集成测试

`tests/integration/test_strategy_endpoints.py`:

```python
def test_parameter_ranges_for_known_strategy(client):
    r = client.get("/api/v1/strategies/ma/parameter-ranges")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "ma"
    assert any(p["name"] == "fast_period" for p in body["parameters"])

def test_parameter_ranges_for_unknown_strategy(client):
    r = client.get("/api/v1/strategies/__nope__/parameter-ranges")
    assert r.status_code == 404
```

### Step 3.5 重新生成 OpenAPI 文档

```bash
python scripts/generate_api_docs.py
git add docs/openapi.json docs/postman_collection.json docs/API_REFERENCE.md
```

---

## 4. 添加一个新前端页面

> 目标:`/portfolio` 页面展示组合优化结果。

### Step 4.1 路由

`frontend/src/App.js` 加入:

```jsx
const PortfolioPanel = React.lazy(() => import('./components/PortfolioPanel'));

<Route path="/portfolio" element={
  <Suspense fallback={<Spin />}>
    <PortfolioPanel />
  </Suspense>
} />
```

### Step 4.2 组件

`frontend/src/components/PortfolioPanel.js`:

```jsx
import { useEffect, useState } from 'react';
import { Card, Table } from 'antd';
import { fetchPortfolioOptimization } from '../services/portfolio';

export default function PortfolioPanel() {
  const [rows, setRows] = useState([]);
  useEffect(() => { fetchPortfolioOptimization().then(setRows); }, []);
  return <Card title="组合优化"><Table dataSource={rows} /></Card>;
}
```

### Step 4.3 服务层

`frontend/src/services/portfolio.js`:

```js
import { api } from './api';
export const fetchPortfolioOptimization = (req) =>
  api.post('/api/v1/portfolio/optimize', req).then(r => r.data);
```

### Step 4.4 测试

`frontend/src/__tests__/portfolio-panel.test.js`(Jest + React Testing Library):

```js
import { render, screen, waitFor } from '@testing-library/react';
import PortfolioPanel from '../components/PortfolioPanel';

jest.mock('../services/portfolio', () => ({
  fetchPortfolioOptimization: () => Promise.resolve([{ symbol: 'AAPL', weight: 0.3 }])
}));

test('renders fetched rows', async () => {
  render(<PortfolioPanel />);
  await waitFor(() => screen.getByText('AAPL'));
});
```

---

## 5. 提交规范

| 前缀 | 用法 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | bug 修复 |
| `refactor:` | 重构(无功能变化) |
| `docs:` | 文档 |
| `test:` | 仅测试改动 |
| `chore:` | 工具链 / 依赖 |
| `style:` | 格式化 / lint |
| `perf:` | 性能优化 |

每个 commit 应该:
- 通过 `pytest tests/unit -q`
- 通过 `ruff check .`(对你新增的文件至少是干净的)
- 描述清楚 *为什么* 改,而不是 *改了什么*

---

**最后更新**: 2026-05-02
