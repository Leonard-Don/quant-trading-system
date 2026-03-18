"""
API集成测试
"""

import pytest
import pandas as pd

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
from src.reporting.pdf_generator import PDFGenerator  # noqa: E402


def build_mock_backtest_data():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    close = [100, 102, 104, 106, 108, 110]
    return pd.DataFrame(
        {
            "open": close,
            "high": [price + 1 for price in close],
            "low": [price - 1 for price in close],
            "close": close,
            "volume": [1000] * len(close),
        },
        index=dates,
    )


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

            assert "metrics" in results
            assert results["metrics"]["total_return"] == results["total_return"]
            assert results["metrics"]["num_trades"] == results["num_trades"]

    def test_buy_and_hold_endpoint_has_non_zero_return(self, client):
        """买入持有策略应在真实接口路径上返回非零收益并带镜像指标"""
        payload = {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "parameters": {},
            "start_date": "2023-01-01",
            "end_date": "2023-03-31",
            "initial_capital": 10000,
            "commission": 0.001,
            "slippage": 0.001,
        }

        response = client.post("/backtest", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        results = data["data"]
        assert results["num_trades"] == 1
        assert results["total_return"] != 0
        assert results["metrics"]["total_return"] == results["total_return"]
        assert results["metrics"]["num_trades"] == results["num_trades"]

    def test_compare_endpoint_matches_main_backtest_metrics(self, client, monkeypatch):
        """策略对比入口应与主回测入口复用同一指标口径。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        payload = {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "parameters": {},
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
            "initial_capital": 10000,
            "commission": 0.001,
            "slippage": 0.001,
        }

        backtest_response = client.post("/backtest", json=payload)
        compare_response = client.get(
            "/backtest/compare",
            params={
                "symbol": "AAPL",
                "strategies": "buy_and_hold,moving_average",
                "start_date": "2024-01-01",
                "end_date": "2024-01-06",
                "initial_capital": 10000,
            },
        )

        assert backtest_response.status_code == 200
        assert compare_response.status_code == 200

        backtest_results = backtest_response.json()["data"]
        compare_results = compare_response.json()["data"]["buy_and_hold"]

        assert compare_results["metrics"]["total_return"] == compare_results["total_return"]
        assert compare_results["metrics"]["num_trades"] == compare_results["num_trades"]
        assert compare_results["metrics"]["total_trades"] == compare_results["total_trades"]
        assert compare_results["total_return"] == pytest.approx(backtest_results["total_return"])
        assert compare_results["annualized_return"] == pytest.approx(backtest_results["annualized_return"])
        assert compare_results["num_trades"] == backtest_results["num_trades"]
        assert compare_results["profit_factor"] == backtest_results["profit_factor"]

    def test_compare_endpoint_supports_macd_strategy(self, client, monkeypatch):
        """策略对比接口应能正常实例化 MACD 策略。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        response = client.get(
            "/backtest/compare",
            params={
                "symbol": "AAPL",
                "strategies": "moving_average,macd",
                "start_date": "2024-01-01",
                "end_date": "2024-01-06",
                "initial_capital": 10000,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert "macd" in payload["data"]
        assert payload["data"]["macd"]["metrics"]["total_trades"] == payload["data"]["macd"]["total_trades"]

    def test_compare_endpoint_supports_advanced_strategy_pairs(self, client, monkeypatch):
        """策略对比接口应支持高级策略组合，不因参数映射或校验缺口失败。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        strategy_pairs = [
            ("moving_average", "mean_reversion"),
            ("moving_average", "vwap"),
            ("moving_average", "stochastic"),
            ("moving_average", "atr_trailing_stop"),
        ]

        for left, right in strategy_pairs:
            response = client.get(
                "/backtest/compare",
                params={
                    "symbol": "AAPL",
                    "strategies": f"{left},{right}",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-06",
                    "initial_capital": 10000,
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True, payload
            assert right in payload["data"]
            assert "metrics" in payload["data"][right]

    def test_report_base64_replay_matches_provided_backtest_result(self, client, monkeypatch):
        """报告接口在传结果和服务端补跑两种模式下应使用一致的核心指标。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        captured_results = []

        def fake_get_report_base64(self, backtest_result, symbol, strategy, parameters=None):
            captured_results.append(backtest_result)
            return "ZmFrZV9wZGY="

        monkeypatch.setattr(PDFGenerator, "get_report_base64", fake_get_report_base64)

        payload = {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "parameters": {},
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
            "initial_capital": 10000,
            "commission": 0.001,
            "slippage": 0.001,
        }

        backtest_response = client.post("/backtest", json=payload)
        assert backtest_response.status_code == 200
        backtest_results = backtest_response.json()["data"]

        provided_report = client.post(
            "/backtest/report/base64",
            json={
                **payload,
                "backtest_result": backtest_results,
            },
        )
        replay_report = client.post("/backtest/report/base64", json=payload)

        assert provided_report.status_code == 200
        assert replay_report.status_code == 200
        assert provided_report.json()["success"] is True
        assert replay_report.json()["success"] is True
        assert len(captured_results) == 2

        for field in ["total_return", "annualized_return", "num_trades", "profit_factor"]:
            assert captured_results[0][field] == pytest.approx(captured_results[1][field])
            assert captured_results[0]["metrics"][field] == pytest.approx(
                captured_results[1]["metrics"][field]
            )

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
