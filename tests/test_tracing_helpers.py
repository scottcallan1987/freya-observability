"""Tests for Phase 2 tracing helpers."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from freya_observability.tracing import (
    AMQP_TRACE_HEADER,
    TRACE_HEADER,
    TraceContext,
    TraceMiddleware,
    attach_trace_to_client,
    publish_with_trace,
    with_trace,
)


class TestTraceMiddleware:
    def _make_app(self):
        app = FastAPI()
        app.add_middleware(TraceMiddleware)

        @app.get("/echo-trace")
        def echo_trace():
            return {"trace_id": TraceContext.current_trace_id()}

        return app

    def test_generates_trace_when_header_missing(self):
        client = TestClient(self._make_app())
        resp = client.get("/echo-trace")
        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] is not None
        assert len(body["trace_id"]) == 16
        assert TRACE_HEADER in resp.headers
        assert resp.headers[TRACE_HEADER] == body["trace_id"]

    def test_reuses_incoming_trace_id(self):
        client = TestClient(self._make_app())
        resp = client.get("/echo-trace", headers={TRACE_HEADER: "abcdef1234567890"})
        assert resp.json()["trace_id"] == "abcdef1234567890"
        assert resp.headers[TRACE_HEADER] == "abcdef1234567890"

    def test_context_cleared_after_request(self):
        client = TestClient(self._make_app())
        client.get("/echo-trace", headers={TRACE_HEADER: "deadbeefdeadbeef"})
        assert TraceContext.current_trace_id() is None


class TestAttachTraceToClient:
    @pytest.mark.asyncio
    async def test_injects_trace_header_on_outbound(self):
        captured_headers = {}

        async def handler(request: httpx.Request):
            captured_headers.update(request.headers)
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        attach_trace_to_client(client)

        with TraceContext(trace_id="feedface12345678"):
            await client.get("https://example.com/")

        assert captured_headers.get(TRACE_HEADER.lower()) == "feedface12345678"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_skips_injection_when_no_trace_context(self):
        captured_headers = {}

        async def handler(request: httpx.Request):
            captured_headers.update(request.headers)
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        attach_trace_to_client(client)

        await client.get("https://example.com/")
        assert TRACE_HEADER.lower() not in captured_headers
        await client.aclose()


class TestPublishWithTrace:
    @pytest.mark.asyncio
    async def test_injects_amqp_header(self):
        exchange = MagicMock()
        exchange.publish = AsyncMock()

        with TraceContext(trace_id="beef0000cafe1111"):
            await publish_with_trace(
                exchange,
                routing_key="test.rk",
                body=b'{"hello": "world"}',
            )

        assert exchange.publish.await_count == 1
        call_args = exchange.publish.await_args
        message = call_args.args[0]
        assert message.headers is not None
        assert message.headers.get(AMQP_TRACE_HEADER) == "beef0000cafe1111"
        assert call_args.kwargs["routing_key"] == "test.rk"

    @pytest.mark.asyncio
    async def test_merges_with_caller_headers(self):
        exchange = MagicMock()
        exchange.publish = AsyncMock()

        with TraceContext(trace_id="1111222233334444"):
            await publish_with_trace(
                exchange,
                routing_key="test",
                body=b"{}",
                headers={"custom-header": "value"},
            )

        message = exchange.publish.await_args.args[0]
        assert message.headers["custom-header"] == "value"
        assert message.headers[AMQP_TRACE_HEADER] == "1111222233334444"

    @pytest.mark.asyncio
    async def test_no_context_no_trace_header(self):
        exchange = MagicMock()
        exchange.publish = AsyncMock()

        await publish_with_trace(exchange, routing_key="x", body=b"{}")

        message = exchange.publish.await_args.args[0]
        headers = message.headers or {}
        assert AMQP_TRACE_HEADER not in headers


class TestWithTraceDecorator:
    @pytest.mark.asyncio
    async def test_picks_up_trace_from_message_header(self):
        seen_trace_ids = []

        @with_trace
        async def handler(message):
            seen_trace_ids.append(TraceContext.current_trace_id())

        fake_message = MagicMock()
        fake_message.headers = {AMQP_TRACE_HEADER: "aaaaaaaabbbbbbbb"}

        await handler(fake_message)
        assert seen_trace_ids == ["aaaaaaaabbbbbbbb"]

    @pytest.mark.asyncio
    async def test_works_with_missing_headers(self):
        seen_trace_ids = []

        @with_trace
        async def handler(message):
            seen_trace_ids.append(TraceContext.current_trace_id())

        fake_message = MagicMock()
        fake_message.headers = None

        await handler(fake_message)
        assert seen_trace_ids[0] is not None
        assert len(seen_trace_ids[0]) == 16

    @pytest.mark.asyncio
    async def test_trace_cleared_after_handler(self):
        @with_trace
        async def handler(message):
            pass

        fake_message = MagicMock()
        fake_message.headers = {AMQP_TRACE_HEADER: "ccccccccdddddddd"}

        await handler(fake_message)
        assert TraceContext.current_trace_id() is None
