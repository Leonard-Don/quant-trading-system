"""Circuit breaker for fragile data providers.

Drop-in protection for upstream services that can hard-fail at any time
(akshare/sina HTML parsing, alpha_vantage rate limits, ...). Pattern:

    @with_circuit_breaker(failure_threshold=5, recovery_timeout=60)
    def get_history(self, symbol: str) -> pd.DataFrame:
        ...

State machine::

    CLOSED ── N consecutive failures ──▶ OPEN
    OPEN   ── recovery_timeout elapsed ──▶ HALF_OPEN (1 trial allowed)
    HALF_OPEN ── trial succeeds ──▶ CLOSED (counter reset)
    HALF_OPEN ── trial fails    ──▶ OPEN  (timer restarts)

The breaker is thread-safe: providers are commonly invoked from
``concurrent.futures.ThreadPoolExecutor``, so the internal counter and state
transitions are guarded by a ``threading.RLock``.
"""

from __future__ import annotations

import enum
import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is short-circuited because the breaker is OPEN."""


class CircuitBreaker:
    """Per-target circuit breaker.

    Parameters
    ----------
    failure_threshold:
        Consecutive failures required to trip from CLOSED to OPEN.
    recovery_timeout:
        Seconds the breaker stays in OPEN before allowing one trial call.
    half_open_max_calls:
        Number of concurrent trial calls permitted in HALF_OPEN. Default 1.
    excluded_exceptions:
        Exception classes that do NOT count as failures (e.g. user-input
        ``ValueError``). They still propagate to the caller.
    name:
        Optional label included in :py:meth:`status` output for telemetry.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        *,
        half_open_max_calls: int = 1,
        excluded_exceptions: tuple[type[BaseException], ...] = (),
        name: str | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.excluded_exceptions = excluded_exceptions
        self.name = name or "anonymous"

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._half_open_in_flight: int = 0
        self._last_failure_at: float | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Properties (read-only views — locked snapshots)
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Invoke ``fn`` through the breaker."""
        # Phase 1: gate
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state is CircuitState.OPEN:
                raise CircuitOpenError(
                    f"circuit '{self.name}' is OPEN; "
                    f"next attempt at {self._next_attempt_at_unlocked()}"
                )

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self.half_open_max_calls:
                    raise CircuitOpenError(
                        f"circuit '{self.name}' HALF_OPEN trial in progress"
                    )
                self._half_open_in_flight += 1
                in_half_open = True
            else:
                in_half_open = False

        # Phase 2: real call (lock released)
        try:
            result = fn(*args, **kwargs)
        except self.excluded_exceptions:
            with self._lock:
                if in_half_open:
                    self._half_open_in_flight -= 1
            raise
        except BaseException:
            with self._lock:
                if in_half_open:
                    self._half_open_in_flight -= 1
                self._record_failure()
            raise

        # Phase 3: success bookkeeping
        with self._lock:
            if in_half_open:
                self._half_open_in_flight -= 1
            self._record_success()

        return result

    def reset(self) -> None:
        """Force the breaker back to CLOSED. For administrative use."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_in_flight = 0

    def status(self) -> dict[str, Any]:
        """Snapshot for telemetry / API exposure."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_at": self._last_failure_at,
                "next_attempt_at": self._next_attempt_at_unlocked(),
            }

    # ------------------------------------------------------------------
    # Internal — caller already holds self._lock
    # ------------------------------------------------------------------

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_at = time.time()

        # In HALF_OPEN, ANY failure reopens immediately (timer restart).
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return

        if self._failure_count >= self.failure_threshold:
            self._open()

    def _record_success(self) -> None:
        # Successful call wipes the slate clean and forces CLOSED.
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.time()

    def _maybe_transition_to_half_open(self) -> None:
        if self._state is not CircuitState.OPEN or self._opened_at is None:
            return
        if (time.time() - self._opened_at) >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_in_flight = 0

    def _next_attempt_at_unlocked(self) -> float | None:
        if self._opened_at is None:
            return None
        return self._opened_at + self.recovery_timeout


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def with_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    *,
    half_open_max_calls: int = 1,
    excluded_exceptions: tuple[type[BaseException], ...] = (),
    name: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Wrap a callable so that all invocations route through a CircuitBreaker.

    Each decorated function gets its own breaker instance. The breaker is
    accessible on the wrapper as the ``circuit_breaker`` attribute, useful
    for inspecting state in tests or telemetry endpoints.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            excluded_exceptions=excluded_exceptions,
            name=name or fn.__qualname__,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return breaker.call(fn, *args, **kwargs)

        wrapper.circuit_breaker = breaker  # type: ignore[attr-defined]
        return wrapper

    return decorator
