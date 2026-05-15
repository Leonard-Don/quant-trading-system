"""
pytest配置文件
"""

import pytest
import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.data.data_manager import DataManager  # noqa: E402
from src.strategy.strategies import MovingAverageCrossover, RSIStrategy  # noqa: E402
from src.backtest.backtester import Backtester  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_etf_rotation_external_state(monkeypatch):
    """Keep ETF rotation tests independent of the developer's local config.

    The CLI/API auto-load ``~/.config/etf-rotation/holdings.json`` and call
    ``realtime_manager`` for live quotes by default. Both must be neutralised
    in unit tests so the same suite passes on a fresh checkout and a fully
    configured workstation. Individual tests can monkeypatch the helpers
    back to a real implementation when they want to exercise that path.
    """

    monkeypatch.delenv("ETF_HOLDINGS_PATH", raising=False)
    monkeypatch.delenv("ETF_AUDIT_LOG_PATH", raising=False)

    try:
        from scripts import daily_etf_signal
    except ImportError:
        # Skip the isolation when daily_etf_signal isn't on the path —
        # tests that don't touch it shouldn't care.
        return

    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_HOLDINGS_PATH",
        Path("/nonexistent/etf-rotation/holdings.json"),
    )
    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_AUDIT_LOG_PATH",
        Path("/nonexistent/etf-rotation/audit.jsonl"),
    )

    def _empty_quote_fetch(codes, *, use_cache=True):
        return {}, {
            "requested": len(codes) if codes else 0,
            "resolved": 0,
            "missing": len(codes) if codes else 0,
            "use_cache": use_cache,
            "offline": True,
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", _empty_quote_fetch)

    # Reset the EtfRotationService singleton between tests so each test
    # starts with no cached plan (the FastAPI lifespan hook installs one
    # in production, but in unit tests we want isolation).
    try:
        from backend.app.api.v1.endpoints import etf_rotation as etf_endpoint
    except ImportError:
        return
    etf_endpoint.reset_service_for_tests()


@pytest.fixture
def sample_data():
    """生成测试用的样本数据"""
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
    np.random.seed(42)

    # 生成模拟的OHLCV数据
    base_price = 100
    returns = np.random.normal(0.001, 0.02, len(dates))
    prices = base_price * (1 + returns).cumprod()

    data = pd.DataFrame(
        {
            "open": prices * (1 + np.random.normal(0, 0.001, len(dates))),
            "high": prices * (1 + np.abs(np.random.normal(0.002, 0.001, len(dates)))),
            "low": prices * (1 - np.abs(np.random.normal(0.002, 0.001, len(dates)))),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, len(dates)),
        },
        index=dates,
    )

    # 确保high >= low, open和close在high和low之间
    data["high"] = np.maximum(data["high"], data[["open", "close"]].max(axis=1))
    data["low"] = np.minimum(data["low"], data[["open", "close"]].min(axis=1))

    return data


@pytest.fixture
def data_manager():
    """数据管理器实例"""
    return DataManager()


@pytest.fixture
def moving_average_strategy():
    """移动平均策略实例"""
    return MovingAverageCrossover(fast_period=10, slow_period=20)


@pytest.fixture
def rsi_strategy():
    """RSI策略实例"""
    return RSIStrategy(period=14, oversold=30, overbought=70)


@pytest.fixture
def backtester():
    """回测器实例"""
    return Backtester(initial_capital=10000, commission=0.001)


@pytest.fixture
def api_client():
    """API客户端（需要后端运行）"""
    import requests

    return requests.Session()


@pytest.fixture(scope="session")
def test_config():
    """测试配置"""
    return {
        "api_base_url": "http://localhost:8000",
        "test_symbol": "AAPL",
        "test_date_range": {"start": "2023-01-01", "end": "2023-12-31"},
    }
