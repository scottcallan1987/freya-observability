"""Tests for the freya_observability.call_telemetry module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from freya_observability.call_telemetry import CallTracer, TraceConfig


def _make_tracer(qdrant_client=None, embed_fn=None):
    config = TraceConfig(
        qdrant_url="http://qdrant-test:6333",
        qdrant_collection="test_traces",
        embedding_model="nomic-embed-text",
        ollama_host="http://ollama-test:11434",
    )
    tracer = CallTracer(caller_service="test-caller", config=config)
    if qdrant_client is not None:
        tracer._qdrant = qdrant_client
    if embed_fn is not None:
        tracer._embed = embed_fn
    return tracer


class TestCallTracerHappyPath:
    @pytest.mark.asyncio
    async def test_context_manager_emits_trace_on_exit(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        embed = AsyncMock(return_value=[0.1] * 768)
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        async with tracer.trace(
            target_service="target",
            operation="doThing",
            inputs={"a": 1},
        ) as span:
            span.record_output({"b": 2})

        qdrant.upsert.assert_called_once()
        call = qdrant.upsert.call_args
        assert call.kwargs["collection_name"] == "test_traces"
        points = call.kwargs["points"]
        assert len(points) == 1
        payload = points[0].payload
        assert payload["caller_service"] == "test-caller"
        assert payload["target_service"] == "target"
        assert payload["operation"] == "doThing"
        assert payload["inputs"] == {"a": 1}
        assert payload["outputs"] == {"b": 2}
        assert payload["success"] is True
        assert "duration_ms" in payload
        assert "timestamp" in payload
        assert points[0].vector == [0.1] * 768

    @pytest.mark.asyncio
    async def test_context_manager_records_exception_as_failure(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        embed = AsyncMock(return_value=[0.1] * 768)
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        with pytest.raises(ValueError):
            async with tracer.trace(target_service="target", operation="op", inputs={}) as span:
                raise ValueError("boom")

        qdrant.upsert.assert_called_once()
        payload = qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["success"] is False
        assert payload["error_type"] == "ValueError"
        assert "boom" in payload["error_message"]

    @pytest.mark.asyncio
    async def test_quality_signal_recorded_when_set(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        embed = AsyncMock(return_value=[0.1] * 768)
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        async with tracer.trace(target_service="t", operation="o", inputs={}) as span:
            span.record_output({"x": 1})
            span.record_quality_signal(0.87)

        payload = qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["quality_signal"] == 0.87


class TestCallTracerDegradation:
    @pytest.mark.asyncio
    async def test_qdrant_failure_does_not_raise(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock(side_effect=ConnectionError("qdrant down"))
        embed = AsyncMock(return_value=[0.1] * 768)
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        async with tracer.trace(target_service="t", operation="o", inputs={}) as span:
            span.record_output({"ok": True})

    @pytest.mark.asyncio
    async def test_embed_failure_does_not_raise_and_still_emits_trace(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        embed = AsyncMock(side_effect=RuntimeError("ollama down"))
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        async with tracer.trace(target_service="t", operation="o", inputs={}) as span:
            span.record_output({"ok": True})

        qdrant.upsert.assert_called_once()
        payload = qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["success"] is True
        points = qdrant.upsert.call_args.kwargs["points"]
        assert points[0].vector == [0.0] * 768


class TestDecorator:
    @pytest.mark.asyncio
    async def test_traced_decorator_wraps_function_and_emits_trace(self):
        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        embed = AsyncMock(return_value=[0.1] * 768)
        tracer = _make_tracer(qdrant_client=qdrant, embed_fn=embed)

        @tracer.traced(target_service="t", operation="op")
        async def call_something(x):
            return {"result": x * 2}

        result = await call_something(5)

        assert result == {"result": 10}
        qdrant.upsert.assert_called_once()
        payload = qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["inputs"] == {"args": [5], "kwargs": {}}
        assert payload["outputs"] == {"result": 10}
