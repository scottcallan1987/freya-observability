"""Tests for the circuit breaker pattern implementation."""

import time

import pytest

from freya_observability.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerInitialization:
    def test_initial_state_is_closed(self):
        """New circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=5.0)
        assert cb.state == CircuitState.CLOSED

    def test_default_parameters(self):
        """Default threshold is 5 and recovery timeout is 30s."""
        cb = CircuitBreaker(name="defaults")
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0

    def test_custom_parameters(self):
        """Custom parameters are stored correctly."""
        cb = CircuitBreaker(name="custom", failure_threshold=10, recovery_timeout=60.0)
        assert cb.name == "custom"
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 60.0


class TestCircuitBreakerStateTransitions:
    def test_closed_to_open_after_threshold_failures(self):
        """Circuit transitions from CLOSED to OPEN after failure_threshold failures."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=10.0)
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open_after_timeout(self):
        """Circuit transitions from OPEN to HALF_OPEN after recovery_timeout."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """Circuit transitions from HALF_OPEN to CLOSED on successful call."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Circuit transitions from HALF_OPEN back to OPEN on failure."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)

        cb.record_failure()
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_full_lifecycle_closed_open_halfopen_closed(self):
        """Full lifecycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
        cb = CircuitBreaker(name="lifecycle", failure_threshold=2, recovery_timeout=0.05)

        # CLOSED
        assert cb.state == CircuitState.CLOSED

        # CLOSED -> OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # OPEN -> HALF_OPEN (after timeout)
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

        # HALF_OPEN -> CLOSED (on success)
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self):
        """A success resets the failure count, preventing premature opening."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=10.0)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Failure count was reset, so 2 more failures should not open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerGuard:
    def test_guard_allows_when_closed(self):
        """guard() does not raise when circuit is CLOSED."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.guard()  # Should not raise

    def test_guard_raises_when_open(self):
        """guard() raises CircuitOpenError when circuit is OPEN."""
        cb = CircuitBreaker(name="qdrant", failure_threshold=1, recovery_timeout=30.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError) as exc_info:
            cb.guard()
        assert "qdrant" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)

    def test_guard_allows_when_half_open(self):
        """guard() allows requests through when circuit is HALF_OPEN."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN
        cb.guard()  # Should not raise


class TestCircuitBreakerProtectDecorator:
    def test_protect_passes_through_on_success(self):
        """Decorated function executes normally and records success."""
        cb = CircuitBreaker(name="test", failure_threshold=3)

        @cb.protect
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3
        assert cb.state == CircuitState.CLOSED

    def test_protect_records_failure_on_exception(self):
        """Decorated function records failure when exception is raised."""
        cb = CircuitBreaker(name="test", failure_threshold=2)

        @cb.protect
        def failing():
            raise RuntimeError("service down")

        with pytest.raises(RuntimeError):
            failing()
        with pytest.raises(RuntimeError):
            failing()

        assert cb.state == CircuitState.OPEN

    def test_protect_blocks_calls_when_open(self):
        """Decorated function raises CircuitOpenError when circuit is OPEN."""
        cb = CircuitBreaker(name="test", failure_threshold=1)

        @cb.protect
        def call_service():
            return "ok"

        # Force open
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            call_service()

    def test_protect_preserves_function_metadata(self):
        """@protect preserves the decorated function's name and docstring."""
        cb = CircuitBreaker(name="test")

        @cb.protect
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


class TestCircuitOpenError:
    def test_is_exception(self):
        """CircuitOpenError is an Exception subclass."""
        assert issubclass(CircuitOpenError, Exception)

    def test_message(self):
        """CircuitOpenError carries a descriptive message."""
        err = CircuitOpenError("service unavailable")
        assert str(err) == "service unavailable"
