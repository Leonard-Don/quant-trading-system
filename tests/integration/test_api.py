"""
API集成测试
"""

import base64
import time
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


def build_mock_backtest_data(periods=6):
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    close = [100 + (index * 2) for index in range(periods)]
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

    def test_backtest_endpoint(self, client, monkeypatch):
        """测试回测端点"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint
        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )
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

    def test_buy_and_hold_endpoint_has_non_zero_return(self, client, monkeypatch):
        """买入持有策略应在真实接口路径上返回非零收益并带镜像指标"""
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
        compare_response = client.post(
            "/backtest/compare",
            json={
                "symbol": "AAPL",
                "strategy_configs": [
                    {"name": "buy_and_hold", "parameters": {}},
                    {"name": "moving_average", "parameters": {"fast_period": 5, "slow_period": 12}},
                ],
                "start_date": "2024-01-01",
                "end_date": "2024-01-06",
                "initial_capital": 10000,
                "commission": 0.001,
                "slippage": 0.001,
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

    def test_batch_backtest_endpoint_returns_summary_and_ranked_results(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=20),
        )

        response = client.post(
            "/backtest/batch",
            json={
                "tasks": [
                    {
                        "task_id": "batch-1",
                        "symbol": "AAPL",
                        "strategy": "buy_and_hold",
                        "parameters": {},
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-20",
                    },
                    {
                        "task_id": "batch-2",
                        "symbol": "AAPL",
                        "strategy": "moving_average",
                        "parameters": {"fast_period": 10, "slow_period": 20},
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-20",
                    },
                ],
                "ranking_metric": "total_return",
                "top_n": 1,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["summary"]["total_tasks"] == 2
        assert len(payload["data"]["results"]) == 2
        assert len(payload["data"]["ranked_results"]) == 1
        successful_results = [item for item in payload["data"]["results"] if item["success"]]
        assert len(successful_results) == 2
        assert successful_results[0]["metrics"]["total_trades"] == successful_results[0]["metrics"]["num_trades"]
        assert payload["data"]["execution"]["use_processes"] is False

    def test_batch_backtest_endpoint_respects_timeout(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=20),
        )

        def slow_run_batch(self, **kwargs):
            time.sleep(0.05)
            return {"summary": {}, "results": [], "ranked_results": []}

        monkeypatch.setattr(backtest_endpoint.BatchBacktester, "run_batch", slow_run_batch)

        response = client.post(
            "/backtest/batch",
            json={
                "tasks": [
                    {
                        "task_id": "batch-1",
                        "symbol": "AAPL",
                        "strategy": "buy_and_hold",
                        "parameters": {},
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-20",
                    }
                ],
                "timeout_seconds": 0.01,
            },
        )

        assert response.status_code == 504
        payload = response.json()
        error_message = payload.get("detail") or payload.get("error") or ""
        if isinstance(error_message, dict):
            error_message = error_message.get("message", "")
        assert "timed out" in str(error_message).lower()

    def test_batch_backtest_endpoint_surfaces_process_mode(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint
        from src.backtest.batch_backtester import BacktestResult

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=20),
        )

        def fake_run_batch(self, **kwargs):
            tasks = kwargs["tasks"]
            self.results = [
                BacktestResult(
                    task_id=tasks[0].task_id,
                    symbol=tasks[0].symbol,
                    strategy_name=tasks[0].strategy_name,
                    parameters=tasks[0].parameters,
                    metrics={"num_trades": 1, "total_trades": 1},
                    success=True,
                )
            ]
            return self.results

        monkeypatch.setattr(backtest_endpoint.BatchBacktester, "run_batch", fake_run_batch)

        response = client.post(
            "/backtest/batch",
            json={
                "tasks": [
                    {
                        "task_id": "batch-proc",
                        "symbol": "AAPL",
                        "strategy": "buy_and_hold",
                        "parameters": {},
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-20",
                    }
                ],
                "use_processes": True,
                "timeout_seconds": 1,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["execution"]["use_processes"] is True

    def test_walk_forward_endpoint_returns_window_aggregate_metrics(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=40),
        )

        response = client.post(
            "/backtest/walk-forward",
            json={
                "symbol": "AAPL",
                "strategy": "moving_average",
                "parameters": {"fast_period": 5, "slow_period": 12},
                "start_date": "2024-01-01",
                "end_date": "2024-02-09",
                "train_period": 10,
                "test_period": 5,
                "step_size": 5,
                "optimization_metric": "sharpe_ratio",
                "optimization_method": "bayesian",
                "optimization_budget": 2,
                "monte_carlo_simulations": 40,
                "parameter_candidates": [
                    {"fast_period": 5, "slow_period": 12},
                    {"fast_period": 6, "slow_period": 15},
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["n_windows"] > 0
        assert payload["data"]["aggregate_metrics"]["average_return"] is not None
        assert len(payload["data"]["window_results"]) == payload["data"]["n_windows"]
        assert payload["data"]["monte_carlo"]["simulations"] == 40
        assert payload["data"]["optimization_method"] == "bayesian"
        assert payload["data"]["optimization_budget"] == 2
        assert "level" in payload["data"]["overfitting_diagnostics"]
        assert "selected_parameters" in payload["data"]["window_results"][0]

    def test_walk_forward_endpoint_respects_timeout(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=40),
        )

        def slow_analyze(self, *args, **kwargs):
            time.sleep(0.05)
            return {}

        monkeypatch.setattr(backtest_endpoint.WalkForwardAnalyzer, "analyze", slow_analyze)

        response = client.post(
            "/backtest/walk-forward",
            json={
                "symbol": "AAPL",
                "strategy": "moving_average",
                "parameters": {"fast_period": 5, "slow_period": 12},
                "start_date": "2024-01-01",
                "end_date": "2024-02-09",
                "train_period": 10,
                "test_period": 5,
                "step_size": 5,
                "timeout_seconds": 0.01,
            },
        )

        assert response.status_code == 504
        payload = response.json()
        error_message = payload.get("detail") or payload.get("error") or ""
        if isinstance(error_message, dict):
            error_message = error_message.get("message", "")
        assert "timed out" in str(error_message).lower()

    def test_backtest_endpoint_supports_fine_grained_cost_controls(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=12),
        )

        base_payload = {
            "symbol": "AAPL",
            "strategy": "moving_average",
            "parameters": {"fast_period": 5, "slow_period": 12},
            "start_date": "2024-01-01",
            "end_date": "2024-01-12",
            "initial_capital": 10000,
            "commission": 0.0,
            "slippage": 0.0,
        }

        low_cost = client.post("/backtest", json=base_payload)
        high_cost = client.post(
            "/backtest",
            json={
                **base_payload,
                "fixed_commission": 5.0,
                "min_commission": 5.0,
                "market_impact_bps": 25.0,
            },
        )

        assert low_cost.status_code == 200
        assert high_cost.status_code == 200
        assert high_cost.json()["data"]["total_return"] <= low_cost.json()["data"]["total_return"]

    def test_strategies_endpoint_includes_extended_strategy_set(self, client):
        response = client.get("/strategies")

        assert response.status_code == 200
        payload = response.json()
        names = {item["name"] for item in payload}
        assert "turtle_trading" in names
        assert "multi_factor" in names

    def test_market_regime_endpoint_returns_regime_breakdown(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        dates = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")
        close = (
            [100 + index * 2 for index in range(20)]
            + [140 - index * 2 for index in range(20)]
            + [100 + (3 if index % 2 == 0 else -2) * index for index in range(20)]
        )
        mock_data = pd.DataFrame(
            {
                "open": close,
                "high": [price + 1 for price in close],
                "low": [price - 1 for price in close],
                "close": close,
                "volume": [1000] * len(close),
            },
            index=dates,
        )

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: mock_data,
        )

        response = client.post(
            "/backtest/market-regimes",
            json={
                "symbol": "AAPL",
                "strategy": "buy_and_hold",
                "parameters": {},
                "start_date": "2024-01-01",
                "end_date": "2024-02-29",
                "lookback_days": 10,
                "trend_threshold": 0.05,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["summary"]["regime_count"] >= 2
        assert payload["data"]["summary"]["strongest_regime"]["regime"]
        assert payload["data"]["regimes"]

    def test_portfolio_strategy_endpoint_returns_combined_portfolio_metrics(self, client, monkeypatch):
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(periods=30),
        )

        response = client.post(
            "/backtest/portfolio-strategy",
            json={
                "symbols": ["AAPL", "MSFT", "NVDA"],
                "strategy": "buy_and_hold",
                "parameters": {},
                "start_date": "2024-01-01",
                "end_date": "2024-01-30",
                "initial_capital": 10000,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["portfolio_components"]
        assert len(payload["data"]["portfolio_components"]) == 3
        assert payload["data"]["final_value"] > 10000
        assert payload["data"]["portfolio_history"]
        assert payload["data"]["portfolio_objective"] == "equal_weight"

    def test_advanced_history_endpoint_saves_batch_experiment_record(self, client):
        response = client.post(
            "/backtest/history/advanced",
            json={
                "record_type": "batch_backtest",
                "title": "批量回测 · AAPL",
                "symbol": "AAPL",
                "strategy": "batch_backtest",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "parameters": {
                    "ranking_metric": "sharpe_ratio",
                },
                "metrics": {
                    "total_return": 0.08,
                    "sharpe_ratio": 1.1,
                    "total_tasks": 2,
                    "successful": 2,
                },
                "result": {
                    "summary": {
                        "total_tasks": 2,
                        "successful": 2,
                        "average_return": 0.08,
                        "average_sharpe": 1.1,
                    },
                    "results": [],
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["record_id"]

    def test_compare_endpoint_supports_macd_strategy(self, client, monkeypatch):
        """策略对比接口应能正常实例化 MACD 策略。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        response = client.post(
            "/backtest/compare",
            json={
                "symbol": "AAPL",
                "strategy_configs": [
                    {"name": "moving_average", "parameters": {"fast_period": 5, "slow_period": 12}},
                    {"name": "macd", "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
                ],
                "start_date": "2024-01-01",
                "end_date": "2024-01-06",
                "initial_capital": 10000,
                "commission": 0.001,
                "slippage": 0.001,
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
            response = client.post(
                "/backtest/compare",
                json={
                    "symbol": "AAPL",
                    "strategy_configs": [
                        {"name": left, "parameters": {}},
                        {"name": right, "parameters": {}},
                    ],
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-06",
                    "initial_capital": 10000,
                    "commission": 0.001,
                    "slippage": 0.001,
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True, payload
            assert right in payload["data"]
            assert "metrics" in payload["data"][right]

    def test_report_endpoints_share_generation_pipeline(self, client, monkeypatch):
        """报告接口在传结果和服务端补跑两种模式下应使用一致的核心指标和 PDF 内容。"""
        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        monkeypatch.setattr(
            backtest_endpoint.data_manager,
            "get_historical_data",
            lambda *args, **kwargs: build_mock_backtest_data(),
        )

        captured_results = []

        def fake_generate_backtest_report(self, backtest_result, symbol, strategy, parameters=None):
            captured_results.append(backtest_result)
            return b"fake_pdf"

        monkeypatch.setattr(
            PDFGenerator,
            "generate_backtest_report",
            fake_generate_backtest_report,
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
        assert backtest_response.status_code == 200
        backtest_results = backtest_response.json()["data"]

        provided_report_base64 = client.post(
            "/backtest/report/base64",
            json={
                **payload,
                "backtest_result": backtest_results,
            },
        )
        replay_report_base64 = client.post("/backtest/report/base64", json=payload)
        provided_report_file = client.post(
            "/backtest/report",
            json={
                **payload,
                "backtest_result": backtest_results,
            },
        )
        replay_report_file = client.post("/backtest/report", json=payload)

        assert provided_report_base64.status_code == 200
        assert replay_report_base64.status_code == 200
        assert provided_report_file.status_code == 200
        assert replay_report_file.status_code == 200
        assert provided_report_base64.json()["success"] is True
        assert replay_report_base64.json()["success"] is True
        assert provided_report_file.headers["content-type"] == "application/pdf"
        assert replay_report_file.headers["content-type"] == "application/pdf"
        assert "attachment; filename=" in provided_report_file.headers["content-disposition"]
        assert len(captured_results) == 4

        for field in ["total_return", "annualized_return", "num_trades", "profit_factor"]:
            assert captured_results[0][field] == pytest.approx(captured_results[1][field])
            assert captured_results[0]["metrics"][field] == pytest.approx(
                captured_results[1]["metrics"][field]
            )

        assert base64.b64decode(provided_report_base64.json()["data"]["pdf_base64"]) == b"fake_pdf"
        assert base64.b64decode(replay_report_base64.json()["data"]["pdf_base64"]) == b"fake_pdf"
        assert provided_report_file.content == b"fake_pdf"
        assert replay_report_file.content == b"fake_pdf"

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
