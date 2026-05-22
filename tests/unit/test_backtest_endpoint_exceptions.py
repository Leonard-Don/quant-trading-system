import asyncio

import pytest
from fastapi import HTTPException

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


def _batch_request():
    return backtest.BatchBacktestRequest(
        tasks=[{"symbol": "AAPL", "strategy": "buy_and_hold"}]
    )


def test_run_batch_backtest_reraises_http_exception(monkeypatch):
    def raise_http_exception(*args, **kwargs):
        raise HTTPException(status_code=418, detail="batch backtester unavailable")

    monkeypatch.setattr(backtest, "_build_batch_backtester", raise_http_exception)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(backtest.run_batch_backtest(_batch_request()))

    assert exc_info.value.status_code == 418
    assert exc_info.value.detail == "batch backtester unavailable"


def _advanced_history_request():
    return backtest.AdvancedHistorySaveRequest(
        record_type="batch_backtest",
        title="Batch AAPL",
        symbol="AAPL",
        strategy="batch_backtest",
        parameters={},
        metrics={"total_return": 0.08},
        result={"summary": {"successful": 1}, "results": []},
    )


def _report_request():
    return backtest.ReportRequest(symbol="AAPL", strategy="buy_and_hold")


def test_backtest_history_endpoint_preserves_runtime_error_response(monkeypatch):
    def raise_history_error(*args, **kwargs):
        raise RuntimeError("history store unavailable")

    monkeypatch.setattr(backtest.backtest_history, "get_statistics", raise_history_error)

    response = asyncio.run(backtest.get_backtest_history(limit=3))

    assert response == {"success": False, "error": "history store unavailable"}


def test_backtest_stats_endpoint_preserves_app_exception_response(monkeypatch):
    def raise_stats_error(*args, **kwargs):
        raise AppException(
            message="history statistics rejected",
            error_code="BACKTEST_HISTORY_STATS_FAILED",
        )

    monkeypatch.setattr(backtest.backtest_history, "get_statistics", raise_stats_error)

    response = asyncio.run(backtest.get_backtest_stats(symbol="AAPL"))

    assert response == {"success": False, "error": "history statistics rejected"}


def test_save_advanced_history_record_preserves_value_error_response(monkeypatch):
    def raise_save_error(*args, **kwargs):
        raise ValueError("advanced history payload invalid")

    monkeypatch.setattr(backtest.backtest_history, "save", raise_save_error)

    response = asyncio.run(
        backtest.save_advanced_history_record(_advanced_history_request())
    )

    assert response == {"success": False, "error": "advanced history payload invalid"}


def test_generate_report_raises_http_500_with_generic_detail(monkeypatch):
    def raise_report_error(*args, **kwargs):
        raise RuntimeError("report renderer unavailable")

    monkeypatch.setattr(backtest, "_build_report_pdf", raise_report_error)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(backtest.generate_report(_report_request()))

    assert exc_info.value.status_code == 500
    # Raw exception text must NOT be forwarded to the client.
    assert exc_info.value.detail == "Internal server error"
    assert "report renderer unavailable" not in str(exc_info.value.detail)


def test_generate_report_base64_preserves_runtime_error_response(monkeypatch):
    def raise_report_error(*args, **kwargs):
        raise RuntimeError("report renderer unavailable")

    monkeypatch.setattr(backtest, "_build_report_pdf", raise_report_error)

    response = asyncio.run(backtest.generate_report_base64(_report_request()))

    assert response == {"success": False, "error": "report renderer unavailable"}


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "generate_report",
        "generate_report_base64",
    ],
)
def test_report_endpoints_reraise_http_exception(endpoint_name, monkeypatch):
    def raise_http_exception(*args, **kwargs):
        raise HTTPException(status_code=418, detail="report already failed")

    monkeypatch.setattr(backtest, "_build_report_pdf", raise_http_exception)

    endpoint = getattr(backtest, endpoint_name)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(endpoint(_report_request()))

    assert exc_info.value.status_code == 418
    assert exc_info.value.detail == "report already failed"


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "get_backtest_history",
        "get_backtest_stats",
        "save_advanced_history_record",
        "generate_report",
        "generate_report_base64",
    ],
)
def test_backtest_history_report_endpoints_do_not_swallow_programmer_errors(
    endpoint_name, monkeypatch
):
    def raise_programmer_error(*args, **kwargs):
        raise AttributeError(f"{endpoint_name} missing collaborator")

    if endpoint_name in {"get_backtest_history", "get_backtest_stats"}:
        monkeypatch.setattr(
            backtest.backtest_history,
            "get_statistics",
            raise_programmer_error,
        )
        coroutine = getattr(backtest, endpoint_name)()
    elif endpoint_name == "save_advanced_history_record":
        monkeypatch.setattr(backtest.backtest_history, "save", raise_programmer_error)
        coroutine = backtest.save_advanced_history_record(_advanced_history_request())
    else:
        monkeypatch.setattr(backtest, "_build_report_pdf", raise_programmer_error)
        coroutine = getattr(backtest, endpoint_name)(_report_request())

    with pytest.raises(AttributeError, match=endpoint_name):
        asyncio.run(coroutine)
