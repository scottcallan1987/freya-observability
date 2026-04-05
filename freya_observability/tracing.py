"""Distributed tracing with context propagation.

TraceContext manages trace IDs that flow across GraphQL requests,
RabbitMQ messages, and worker logs.
"""

import contextvars
import uuid
from typing import Optional

_current_trace: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_trace", default=None
)

TRACE_HEADER = "X-Trace-ID"


class TraceContext:
    """Manages trace ID propagation across services.

    Usage:
        with TraceContext() as ctx:
            # All logs in this block include ctx.trace_id
            logger.info("processing")

        # Propagate via headers:
        headers = {}
        ctx.inject_headers(headers)
        # ... send message ...
        received_ctx = TraceContext.from_headers(headers)
    """

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self._token: Optional[contextvars.Token] = None
        self._previous: Optional[str] = None

    def __enter__(self) -> "TraceContext":
        self._previous = _current_trace.get(None)
        self._token = _current_trace.set(self.trace_id)
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _current_trace.reset(self._token)
        return False

    def inject_headers(self, headers: dict) -> None:
        """Inject trace ID into message headers (e.g., RabbitMQ)."""
        headers[TRACE_HEADER] = self.trace_id

    @classmethod
    def from_headers(cls, headers: dict) -> "TraceContext":
        """Extract trace context from message headers."""
        trace_id = headers.get(TRACE_HEADER)
        return cls(trace_id=trace_id)

    @staticmethod
    def current_trace_id() -> Optional[str]:
        """Get the current trace ID from context."""
        return _current_trace.get(None)
