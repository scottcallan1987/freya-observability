"""Shared observability primitives for Freya clusters."""

from freya_observability.call_telemetry import CallTracer, TraceConfig
from freya_observability.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from freya_observability.healthcheck import make_health_router
from freya_observability.logger import configure_logging, get_logger
from freya_observability.retry import (
    retry_db,
    retry_external_http,
    retry_inference,
)
from freya_observability.timeouts import CRAWL, FAST, LLM, NORMAL
from freya_observability.tracing import (
    AMQP_TRACE_HEADER,
    TRACE_HEADER,
    TraceContext,
    TraceMiddleware,
    attach_trace_to_client,
    publish_with_trace,
    with_trace,
)

__all__ = [
    "CallTracer",
    "TraceConfig",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "TraceContext",
    "TRACE_HEADER",
    "AMQP_TRACE_HEADER",
    "TraceMiddleware",
    "attach_trace_to_client",
    "publish_with_trace",
    "with_trace",
    "configure_logging",
    "get_logger",
    "retry_external_http",
    "retry_inference",
    "retry_db",
    "FAST",
    "NORMAL",
    "LLM",
    "CRAWL",
    "make_health_router",
]
