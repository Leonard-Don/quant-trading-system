"""Unit tests for the data-provider circuit breaker.

Behavioural contract::

    closed       — calls pass through; failures increment counter
    closed → open — when failure_count ≥ failure_threshold
    open         — calls short-circuit with CircuitOpenError
    open → half_open — after recovery_timeout seconds
    half_open    — only one trial call allowed; success closes,
                   failure re-opens with full timeout
"""

from __future__ import annotations

import threading
import time

import pytest

from src.data.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    with_circuit_breaker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FailingService:
    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self.failures = failures

    def fetch(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(f"boom {self.calls}")
        return "ok"


# ---------------------------------------------------------------------------
# Direct CircuitBreaker API
# ---------------------------------------------------------------------------


def test_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_successful_call_resets_failure_count_in_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    svc = _FailingService(failures=2)

    with pytest.raises(RuntimeError):
        cb.call(svc.fetch)
    assert cb.failure_count == 1
    with pytest.raises(RuntimeError):
        cb.call(svc.fetch)
    assert cb.failure_count == 2

    # Successful call clears the counter
    assert cb.call(svc.fetch) == "ok"
    assert cb.failure_count == 0
    assert cb.state is CircuitState.CLOSED


def test_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    svc = _FailingService(failures=10)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(svc.fetch)

    assert cb.state is CircuitState.OPEN
    assert cb.failure_count == 3


def test_open_breaker_short_circuits():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    svc = _FailingService(failures=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(svc.fetch)
    assert cb.state is CircuitState.OPEN

    # Subsequent calls don't reach the wrapped function
    pre_calls = svc.calls
    with pytest.raises(CircuitOpenError):
        cb.call(svc.fetch)
    assert svc.calls == pre_calls


def test_breaker_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    svc = _FailingService(failures=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(svc.fetch)
    assert cb.state is CircuitState.OPEN

    time.sleep(0.06)

    # First call after timeout enters half_open
    with pytest.raises(RuntimeError):
        cb.call(svc.fetch)
    # That trial failed → reopened
    assert cb.state is CircuitState.OPEN


def test_half_open_success_closes_breaker():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    svc = _FailingService(failures=2)  # only 2 fails, 3rd succeeds

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(svc.fetch)
    assert cb.state is CircuitState.OPEN

    time.sleep(0.06)

    # Trial call succeeds → breaker closes, counter resets
    assert cb.call(svc.fetch) == "ok"
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_half_open_blocks_concurrent_trials():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, half_open_max_calls=1)
    svc = _FailingService(failures=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(svc.fetch)
    time.sleep(0.06)

    # Simulate two concurrent trials — only one allowed
    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    results: list[str] = []

    def slow_call() -> None:
        barrier.wait()
        try:
            results.append(cb.call(svc.fetch))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=slow_call)
    t2 = threading.Thread(target=slow_call)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Exactly one of the two reached the wrapped function
    assert len(errors) + len(results) == 2
    # And the wrapped service did not get hammered
    assert svc.calls <= 3  # 2 prior failures + at most 1 trial


def test_manual_reset():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

    assert cb.state is CircuitState.OPEN
    cb.reset()
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_breaker_is_thread_safe():
    cb = CircuitBreaker(failure_threshold=10, recovery_timeout=10.0)
    counter = {"value": 0}
    lock = threading.Lock()

    def increment() -> int:
        # Simulate IO with brief contention
        with lock:
            counter["value"] += 1
        return counter["value"]

    threads = [threading.Thread(target=lambda: cb.call(increment)) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter["value"] == 50
    assert cb.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Decorator API
# ---------------------------------------------------------------------------


def test_decorator_wraps_function():
    fail_count = {"n": 0}

    @with_circuit_breaker(failure_threshold=2, recovery_timeout=10.0)
    def fragile() -> str:
        fail_count["n"] += 1
        if fail_count["n"] <= 2:
            raise RuntimeError("nope")
        return "fine"

    with pytest.raises(RuntimeError):
        fragile()
    with pytest.raises(RuntimeError):
        fragile()
    # Now open
    with pytest.raises(CircuitOpenError):
        fragile()

    # State is accessible via decorator attribute
    assert fragile.circuit_breaker.state is CircuitState.OPEN


def test_decorator_breakers_are_independent_per_function():
    @with_circuit_breaker(failure_threshold=1, recovery_timeout=10.0)
    def fn_a():
        raise RuntimeError("a")

    @with_circuit_breaker(failure_threshold=1, recovery_timeout=10.0)
    def fn_b():
        return "b"

    with pytest.raises(RuntimeError):
        fn_a()
    assert fn_a.circuit_breaker.state is CircuitState.OPEN

    # fn_b's breaker is untouched
    assert fn_b() == "b"
    assert fn_b.circuit_breaker.state is CircuitState.CLOSED


def test_excluded_exceptions_dont_count_as_failures():
    @with_circuit_breaker(
        failure_threshold=2,
        recovery_timeout=10.0,
        excluded_exceptions=(ValueError,),
    )
    def picky(should_value_error: bool) -> str:
        if should_value_error:
            raise ValueError("user error")
        raise RuntimeError("infra")

    # ValueError should NOT trip the breaker
    for _ in range(5):
        with pytest.raises(ValueError):
            picky(True)
    assert picky.circuit_breaker.state is CircuitState.CLOSED

    # RuntimeError DOES count
    with pytest.raises(RuntimeError):
        picky(False)
    with pytest.raises(RuntimeError):
        picky(False)
    assert picky.circuit_breaker.state is CircuitState.OPEN


def test_status_summary_reports_state():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=5.0, name="test_provider")
    summary = cb.status()

    assert summary["name"] == "test_provider"
    assert summary["state"] == "closed"
    assert summary["failure_count"] == 0
    assert "last_failure_at" in summary
    assert "next_attempt_at" in summary
