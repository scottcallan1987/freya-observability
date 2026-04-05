"""Pins the public API so accidental removals fail CI."""

import freya_observability as fo


def test_public_api_surface():
    expected = {
        "CircuitBreaker",
        "CircuitOpenError",
        "CircuitState",
        "TraceContext",
        "TRACE_HEADER",
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
        "AMQP_TRACE_HEADER",
        "TraceMiddleware",
        "attach_trace_to_client",
        "publish_with_trace",
        "with_trace",
    }
    missing = expected - set(dir(fo))
    assert not missing, f"missing public API: {missing}"
