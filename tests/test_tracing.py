"""Tests for distributed tracing with context propagation."""

from freya_observability.tracing import TRACE_HEADER, TraceContext


class TestTraceContext:
    def test_auto_generates_trace_id(self):
        """TraceContext generates a 16-char hex trace ID by default."""
        ctx = TraceContext()
        assert isinstance(ctx.trace_id, str)
        assert len(ctx.trace_id) == 16

    def test_custom_trace_id(self):
        """TraceContext accepts a custom trace ID."""
        ctx = TraceContext(trace_id="custom-trace-123")
        assert ctx.trace_id == "custom-trace-123"

    def test_context_manager_sets_current(self):
        """Entering the context manager makes the trace ID current."""
        with TraceContext(trace_id="test-ctx") as ctx:
            assert TraceContext.current_trace_id() == "test-ctx"
            assert ctx.trace_id == "test-ctx"

    def test_context_manager_restores_previous(self):
        """Exiting the context manager restores the previous trace ID."""
        assert TraceContext.current_trace_id() is None
        with TraceContext(trace_id="outer"):
            assert TraceContext.current_trace_id() == "outer"
            with TraceContext(trace_id="inner"):
                assert TraceContext.current_trace_id() == "inner"
            assert TraceContext.current_trace_id() == "outer"
        assert TraceContext.current_trace_id() is None

    def test_current_trace_id_none_outside_context(self):
        """current_trace_id returns None when no context is active."""
        assert TraceContext.current_trace_id() is None

    def test_inject_headers(self):
        """inject_headers puts the trace ID into a dict under TRACE_HEADER."""
        ctx = TraceContext(trace_id="inject-test")
        headers = {}
        ctx.inject_headers(headers)
        assert headers[TRACE_HEADER] == "inject-test"

    def test_from_headers_with_trace_id(self):
        """from_headers extracts trace ID from headers dict."""
        headers = {TRACE_HEADER: "from-header-123"}
        ctx = TraceContext.from_headers(headers)
        assert ctx.trace_id == "from-header-123"

    def test_from_headers_without_trace_id(self):
        """from_headers generates a new trace ID when header is missing."""
        ctx = TraceContext.from_headers({})
        # No trace_id in headers -> auto-generated
        assert isinstance(ctx.trace_id, str)
        assert len(ctx.trace_id) == 16

    def test_inject_then_extract_roundtrip(self):
        """Trace ID survives inject -> transport -> extract roundtrip."""
        original = TraceContext(trace_id="roundtrip-id")
        headers = {}
        original.inject_headers(headers)
        restored = TraceContext.from_headers(headers)
        assert restored.trace_id == original.trace_id

    def test_trace_header_constant(self):
        """TRACE_HEADER is the expected string."""
        assert TRACE_HEADER == "X-Trace-ID"

    def test_context_manager_exit_returns_false(self):
        """__exit__ returns False so exceptions propagate normally."""
        ctx = TraceContext()
        ctx.__enter__()
        result = ctx.__exit__(None, None, None)
        assert result is False
