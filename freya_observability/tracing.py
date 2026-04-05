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
AMQP_TRACE_HEADER = "x-trace-id"


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


# ---------------------------------------------------------------------------
# Phase 2 helpers: FastAPI middleware, httpx trace injection,
# aio_pika publish wrapper, and consumer handler decorator.
# ---------------------------------------------------------------------------

import functools
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class TraceMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that establishes a TraceContext per request.

    Reads ``X-Trace-ID`` from the incoming request; if missing, a fresh one
    is generated. Installs the context for the duration of the request and
    echoes the ID back in the response header.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(TRACE_HEADER)
        with TraceContext(trace_id=incoming) as ctx:
            response = await call_next(request)
            response.headers[TRACE_HEADER] = ctx.trace_id
            return response


def attach_trace_to_client(client: Any) -> None:
    """Attach an httpx event hook that injects X-Trace-ID into outbound requests.

    Works with both ``httpx.Client`` and ``httpx.AsyncClient``. Safe to call
    multiple times on the same client — hooks append rather than replace.
    """
    import httpx

    async def _async_on_request(request):
        tid = TraceContext.current_trace_id()
        if tid:
            request.headers[TRACE_HEADER] = tid

    def _sync_on_request(request):
        tid = TraceContext.current_trace_id()
        if tid:
            request.headers[TRACE_HEADER] = tid

    hooks = dict(client.event_hooks)
    request_hooks = list(hooks.get("request", []))

    if isinstance(client, httpx.AsyncClient):
        request_hooks.append(_async_on_request)
    else:
        request_hooks.append(_sync_on_request)

    hooks["request"] = request_hooks
    client.event_hooks = hooks


async def publish_with_trace(
    exchange: Any,
    routing_key: str,
    body: bytes,
    *,
    headers: dict | None = None,
    **message_kwargs: Any,
) -> Any:
    """Publish an aio_pika message with X-Trace-ID injected into headers.

    Drop-in replacement for ``exchange.publish(aio_pika.Message(body=...), routing_key=...)``
    that adds the trace header automatically if a TraceContext is active.
    """
    import aio_pika

    merged_headers = dict(headers or {})
    tid = TraceContext.current_trace_id()
    if tid:
        merged_headers[AMQP_TRACE_HEADER] = tid

    message = aio_pika.Message(
        body=body,
        headers=merged_headers,
        **message_kwargs,
    )
    return await exchange.publish(message, routing_key=routing_key)


def with_trace(handler: Callable) -> Callable:
    """Decorator for aio_pika consumer handlers.

    Reads ``x-trace-id`` from the incoming message headers and establishes a
    TraceContext for the handler body. If the message has no trace header,
    a fresh trace ID is generated so the handler's logs are still correlatable.
    """
    @functools.wraps(handler)
    async def wrapper(message: Any, *args: Any, **kwargs: Any) -> Any:
        incoming = None
        raw_headers = getattr(message, "headers", None) or {}
        if isinstance(raw_headers, dict):
            incoming = raw_headers.get(AMQP_TRACE_HEADER)
        with TraceContext(trace_id=incoming):
            return await handler(message, *args, **kwargs)

    return wrapper
