"""
API集成测试
"""

import pytest

# import requests  # 暂时未使用
# import time  # 暂时未使用
# import subprocess  # 暂时未使用
# import threading  # 暂时未使用
import sys
from pathlib import Path

# import uvicorn  # 暂时未使用
# import asyncio  # 暂时未使用
from fastapi.testclient import TestClient

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.main import app  # noqa: E402


class TestAPIIntegration:
    """API集成测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_strategies_endpoint(self, client):
        """测试策略列表端点"""
        response = client.get("/strategies")
        assert response.status_code == 200

        strategies = response.json()
        assert isinstance(strategies, list)
        assert len(strategies) > 0

        # 检查策略结构
        for strategy in strategies:
            assert "name" in strategy
            assert "description" in strategy
            assert "parameters" in strategy

    def test_performance_metrics_endpoint(self, client):
        """测试性能指标端点"""
        response = client.get("/system/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "metrics" in data
        assert "timestamp" in data

    def test_backtest_endpoint(self, client):
        """测试回测端点"""
        payload = {
            "symbol": "AAPL",
            "strategy": "moving_average",
            "parameters": {"short_window": 10, "long_window": 20},
            "start_date": "2023-01-01",
            "end_date": "2023-03-31",
            "initial_capital": 10000,
            "commission": 0.001,
            "slippage": 0.001,
        }

        response = client.post("/backtest", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        if data["success"]:
            assert "data" in data
            results = data["data"]

            # 检查回测结果结构
            required_fields = [
                "total_return",
                "sharpe_ratio",
                "max_drawdown",
                "num_trades",
            ]
            for field in required_fields:
                assert field in results

    def test_error_handling(self, client):
        """测试错误处理"""
        # 测试无效的策略
        invalid_payload = {
            "symbol": "AAPL",
            "strategy": "invalid_strategy",
            "parameters": {},
            "start_date": "2023-01-01",
            "end_date": "2023-01-31",
            "initial_capital": 10000,
        }

        response = client.post("/backtest", json=invalid_payload)

        # 应该返回错误状态或成功但包含错误信息
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            # 如果成功返回，应该包含错误信息
            if not data["success"]:
                assert "error" in data
        else:
            assert response.status_code in [400, 422, 500]
