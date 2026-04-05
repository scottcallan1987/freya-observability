"""Tests for the structured JSON logger."""

import json
import logging
from unittest.mock import patch

from freya_observability.logger import _JSONFormatter, get_logger


class TestJSONFormatter:
    def test_format_basic_record(self):
        """Basic log record produces valid JSON with required fields."""
        formatter = _JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello world",
            args=(),
            exc_info=None,
        )

        with patch(
            "freya_observability.tracing.TraceContext.current_trace_id", return_value=None
        ):
            output = formatter.format(record)

        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["service"] == "test-service"
        assert parsed["message"] == "Hello world"
        assert "timestamp" in parsed
        assert "logger" in parsed

    def test_format_includes_trace_id_when_available(self):
        """Trace ID is included in JSON output when TraceContext has one."""
        formatter = _JSONFormatter(service_name="tracing-svc")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="traced event",
            args=(),
            exc_info=None,
        )

        with patch(
            "freya_observability.tracing.TraceContext.current_trace_id",
            return_value="abc123",
        ):
            output = formatter.format(record)

        parsed = json.loads(output)
        assert parsed["trace_id"] == "abc123"

    def test_format_includes_exception_info(self):
        """Exception info is included in the JSON output."""
        formatter = _JSONFormatter(service_name="error-svc")
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="something broke",
            args=(),
            exc_info=exc_info,
        )

        with patch(
            "freya_observability.tracing.TraceContext.current_trace_id", return_value=None
        ):
            output = formatter.format(record)

        parsed = json.loads(output)
        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert parsed["exception"]["message"] == "test error"

    def test_format_includes_extra_fields(self):
        """Extra fields (duration_ms, method, path) are included when set."""
        formatter = _JSONFormatter(service_name="api")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="request",
            args=(),
            exc_info=None,
        )
        record.duration_ms = 42.5
        record.method = "GET"
        record.path = "/api/health"

        with patch(
            "freya_observability.tracing.TraceContext.current_trace_id", return_value=None
        ):
            output = formatter.format(record)

        parsed = json.loads(output)
        assert parsed["duration_ms"] == 42.5
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/api/health"

    def test_format_no_trace_id_key_when_not_available(self):
        """When no trace ID is active and not set as extra, trace_id key is absent."""
        formatter = _JSONFormatter(service_name="svc")
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="warning",
            args=(),
            exc_info=None,
        )

        with patch(
            "freya_observability.tracing.TraceContext.current_trace_id", return_value=None
        ):
            output = formatter.format(record)

        parsed = json.loads(output)
        assert "trace_id" not in parsed


class TestGetLogger:
    def test_returns_logger_instance(self):
        """get_logger returns a standard logging.Logger."""
        logger = get_logger("my-module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_prefix(self):
        """Logger name is prefixed with 'freya.'."""
        logger = get_logger("agent")
        assert logger.name == "freya.agent"

    def test_logger_has_json_handler(self):
        """Logger has a handler with _JSONFormatter."""
        # Use a unique name to avoid cached handlers from other tests
        logger = get_logger("test-json-handler-unique")
        assert len(logger.handlers) >= 1
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, _JSONFormatter)

    def test_logger_no_duplicate_handlers(self):
        """Calling get_logger twice with the same name does not duplicate handlers."""
        name = "test-no-dup-unique"
        logger1 = get_logger(name)
        handler_count = len(logger1.handlers)
        logger2 = get_logger(name)
        assert len(logger2.handlers) == handler_count
        assert logger1 is logger2

    def test_logger_propagate_false(self):
        """Logger does not propagate to the root logger."""
        logger = get_logger("no-propagate-unique")
        assert logger.propagate is False


class TestConfigureLogging:
    def test_configures_root_handler_with_json_formatter(self, capsys):
        """After configure_logging, logging.getLogger() emits JSON with service name."""
        import logging as stdlib_logging
        from freya_observability.logger import configure_logging, _JSONFormatter

        configure_logging(service_name="unit-test-svc", level="INFO")

        root = stdlib_logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, _JSONFormatter)
        assert root.handlers[0].formatter.service_name == "unit-test-svc"
        assert root.level == stdlib_logging.INFO

    def test_clears_existing_handlers(self):
        """configure_logging clears any handlers added by basicConfig or libraries."""
        import logging as stdlib_logging
        from freya_observability.logger import configure_logging

        root = stdlib_logging.getLogger()
        noise = stdlib_logging.StreamHandler()
        root.addHandler(noise)
        initial_count = len(root.handlers)
        assert initial_count >= 1

        configure_logging(service_name="svc", level="DEBUG")

        assert len(root.handlers) == 1
        assert root.handlers[0] is not noise
        assert root.level == stdlib_logging.DEBUG
