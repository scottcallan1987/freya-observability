"""Generic circuit breaker for external services (Qdrant, Ollama, GitHub API)."""

import functools
import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and blocking requests."""

    pass


class CircuitBreaker:
    """Generic circuit breaker pattern implementation.

    States:
        CLOSED   - Normal operation, requests pass through.
        OPEN     - Requests blocked after failure_threshold failures.
        HALF_OPEN - After recovery_timeout, allows one test request.

    Args:
        name: Identifier for this circuit breaker (used in logs/errors).
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
    """

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' OPENED after %d failures", self.name, self._failure_count
                )
            elif self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' re-OPENED after failure in HALF_OPEN", self.name
                )

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._failure_count = 0
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit breaker '%s' CLOSED after successful call", self.name)
            self._state = CircuitState.CLOSED

    def guard(self) -> None:
        """Check if the circuit allows a request. Raises CircuitOpenError if OPEN."""
        current = self.state  # triggers HALF_OPEN check
        if current == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is OPEN — service unavailable. "
                f"Retry after {self.recovery_timeout}s."
            )

    def protect(self, func):
        """Decorator that wraps a function with circuit breaker protection."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            self.guard()
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception:
                self.record_failure()
                raise

        return wrapper
