import asyncio

import pytest

from backend.app.api.v1.endpoints import backtest
from backend.app.core.error_handler import AppException


def _request_for(endpoint_name: str):
    if endpoint_name == "queue_strategy_significance":
        return backtest.SignificanceCompareRequest(
            symbol="AAPL",
            strategy_configs=[
                {"name": "buy_and_hold", "parameters": {}},
                {"name": "moving_average", "parameters": {}},
            ],
        )
    request_types = {
        "queue_backtest_monte_carlo": backtest.MonteCarloBacktestRequest,
        "queue_multi_period_backtest": backtest.MultiPeriodBacktestRequest,
        "queue_market_impact_analysis": backtest.MarketImpactAnalysisRequest,
    }
    return request_types[endpoint_name](symbol="AAPL", strategy="buy_and_hold")


def _task_name_for(endpoint_name: str) -> str:
    return {
        "queue_backtest_monte_carlo": "backtest_monte_carlo",
        "queue_strategy_significance": "backtest_significance",
        "queue_multi_period_backtest": "backtest_multi_period",
        "queue_market_impact_analysis": "backtest_impact_analysis",
    }[endpoint_name]


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "queue_backtest_monte_carlo",
        "queue_strategy_significance",
        "queue_multi_period_backtest",
        "queue_market_impact_analysis",
    ],
)
def test_async_backtest_queue_endpoints_preserve_known_submission_errors(
    endpoint_name, monkeypatch
):
    def raise_queue_error(task_name, payload):
        raise RuntimeError(f"{task_name} queue unavailable")

    monkeypatch.setattr(backtest, "_submit_async_backtest_task", raise_queue_error)

    endpoint = getattr(backtest, endpoint_name)
    response = asyncio.run(endpoint(_request_for(endpoint_name)))

    assert response == {
        "success": False,
        "error": f"{_task_name_for(endpoint_name)} queue unavailable",
    }


def test_async_backtest_queue_endpoint_preserves_app_exception_message(monkeypatch):
    def raise_app_exception(task_name, payload):
        raise AppException(
            message="task queue rejected request",
            error_code="BACKTEST_QUEUE_REJECTED",
        )

    monkeypatch.setattr(backtest, "_submit_async_backtest_task", raise_app_exception)

    response = asyncio.run(
        backtest.queue_backtest_monte_carlo(
            _request_for("queue_backtest_monte_carlo")
        )
    )

    assert response == {"success": False, "error": "task queue rejected request"}


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "queue_backtest_monte_carlo",
        "queue_strategy_significance",
        "queue_multi_period_backtest",
        "queue_market_impact_analysis",
    ],
)
def test_async_backtest_queue_endpoints_do_not_swallow_programmer_errors(
    endpoint_name, monkeypatch
):
    def raise_programmer_error(task_name, payload):
        raise AttributeError("missing task queue attribute")

    monkeypatch.setattr(backtest, "_submit_async_backtest_task", raise_programmer_error)

    endpoint = getattr(backtest, endpoint_name)

    with pytest.raises(AttributeError, match="missing task queue attribute"):
        asyncio.run(endpoint(_request_for(endpoint_name)))
