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


def _raise(exc: Exception) -> None:
    raise exc


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
        cb.call(_raise, RuntimeError("x"))

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


# ---------------------------------------------------------------------------
# Edge / boundary coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -42])
def test_constructor_rejects_failure_threshold_below_one(bad):
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=bad, recovery_timeout=1.0)


@pytest.mark.parametrize("bad", [0, -0.001, -10.0])
def test_constructor_rejects_non_positive_recovery_timeout(bad):
    with pytest.raises(ValueError, match="recovery_timeout"):
        CircuitBreaker(failure_threshold=1, recovery_timeout=bad)


@pytest.mark.parametrize("bad", [0, -1])
def test_constructor_rejects_half_open_max_calls_below_one(bad):
    with pytest.raises(ValueError, match="half_open_max_calls"):
        CircuitBreaker(
            failure_threshold=1, recovery_timeout=1.0, half_open_max_calls=bad
        )


def test_call_forwards_positional_and_keyword_arguments():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)

    def add(a: int, b: int, *, scale: int = 1) -> int:
        return (a + b) * scale

    assert cb.call(add, 3, 4, scale=2) == 14
    assert cb.call(add, 1, 2) == 3


def test_open_does_not_transition_before_recovery_timeout_elapses():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    svc = _FailingService(failures=10)

    with pytest.raises(RuntimeError):
        cb.call(svc.fetch)
    assert cb.state is CircuitState.OPEN

    pre_calls = svc.calls
    # Repeated state checks within the timeout window must not flip to HALF_OPEN.
    for _ in range(5):
        assert cb.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.call(svc.fetch)
    assert svc.calls == pre_calls  # wrapped fn never invoked


def test_status_during_open_reports_next_attempt_at_and_last_failure():
    recovery = 7.5
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=recovery, name="p")
    started = time.time()

    with pytest.raises(RuntimeError):
        cb.call(_raise, RuntimeError("x"))

    summary = cb.status()
    assert summary["state"] == "open"
    assert summary["failure_count"] == 1
    assert summary["recovery_timeout"] == recovery
    assert summary["last_failure_at"] is not None
    assert summary["last_failure_at"] >= started
    assert summary["next_attempt_at"] is not None
    # next_attempt_at = _opened_at + recovery_timeout, where _opened_at >= started
    assert summary["next_attempt_at"] >= started + recovery


def test_excluded_exception_in_half_open_keeps_state_and_releases_slot():
    cb = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=0.1,
        excluded_exceptions=(ValueError,),
    )

    def infra_boom() -> None:
        raise RuntimeError("infra")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(infra_boom)
    assert cb.state is CircuitState.OPEN

    time.sleep(0.15)

    # Trial call raises an EXCLUDED exception. It must not count as failure
    # (would re-open) nor as success (would close); state remains HALF_OPEN
    # and the in-flight slot must be released so the next trial may proceed.
    with pytest.raises(ValueError):
        cb.call(_raise, ValueError("user"))

    assert cb.state is CircuitState.HALF_OPEN

    # Slot released → a follow-up trial is permitted and can close the breaker.
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_half_open_max_calls_greater_than_one_allows_multiple_concurrent_trials():
    cb = CircuitBreaker(
        failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=3
    )
    with pytest.raises(RuntimeError):
        cb.call(_raise, RuntimeError("x"))
    time.sleep(0.15)
    assert cb.state is CircuitState.HALF_OPEN

    in_fn = threading.Semaphore(0)
    release = threading.Event()

    def slow_ok() -> str:
        in_fn.release()
        release.wait(timeout=2.0)
        return "ok"

    threads = [
        threading.Thread(target=lambda: cb.call(slow_ok)) for _ in range(3)
    ]
    for t in threads:
        t.start()

    # All three trials must reach the wrapped fn concurrently — proves
    # half_open_max_calls=3 grants three slots simultaneously.
    for _ in range(3):
        assert in_fn.acquire(timeout=2.0)

    release.set()
    for t in threads:
        t.join(timeout=3.0)
        assert not t.is_alive()

    # Three successes wipe the slate.
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_decorator_uses_custom_name_when_provided():
    @with_circuit_breaker(failure_threshold=1, recovery_timeout=1.0, name="alpha_vantage")
    def fetch():
        return "ok"

    assert fetch.circuit_breaker.name == "alpha_vantage"
    assert fetch.circuit_breaker.status()["name"] == "alpha_vantage"


def test_decorator_falls_back_to_function_qualname():
    @with_circuit_breaker(failure_threshold=1, recovery_timeout=1.0)
    def my_fragile_fetcher():
        return "ok"

    assert my_fragile_fetcher.circuit_breaker.name == my_fragile_fetcher.__qualname__
