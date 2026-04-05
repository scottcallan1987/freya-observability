"""Structured JSON logger for FreyaCode.

Every log line is JSON with trace_id, service, timestamp, and level.
"""

import json
import logging
from datetime import datetime, timezone


class _JSONFormatter(logging.Formatter):
    """Formats log records as JSON objects."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        from freya_observability.tracing import TraceContext

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add trace_id if available
        trace_id = TraceContext.current_trace_id()
        if trace_id:
            entry["trace_id"] = trace_id

        # Add extra fields
        for key in ("custom_field", "trace_id", "error", "duration_ms", "method", "path"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get a JSON-structured logger for a service.

    Args:
        name: Service/module name used as the 'service' field in logs.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(f"freya.{name}")

    # Only add handler if none exist to avoid duplicates
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JSONFormatter(service_name=name))
        logger.addHandler(handler)
        logger.propagate = False

    return logger


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Configure the root logger to emit JSON for an entire service.

    Call once at service startup. After this, any `logging.getLogger(__name__)`
    anywhere in the process will emit JSON records tagged with ``service_name``.

    This is the preferred entry point for satellite clusters that want
    structured logging for their whole process (as opposed to ``get_logger``
    which creates a namespaced logger). Clears any pre-existing root
    handlers to avoid duplicate output from libraries that ``basicConfig``
    themselves (e.g., uvicorn).

    Args:
        service_name: Value for the ``service`` field in every log record.
        level: Root log level. One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``.
    """
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter(service_name=service_name))
    root.addHandler(handler)
    root.setLevel(level.upper())
