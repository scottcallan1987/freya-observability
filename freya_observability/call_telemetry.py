"""Call-level telemetry for cross-service operations.

Wraps any RPC call (GraphQL, HTTP, etc.) as a span. On exit, emits a full
trace record to Qdrant with a semantic embedding. Failures in the tracer
NEVER propagate to the wrapped call - degrade gracefully.

Feeds the episodic memory / Karpathy autotrain loop per the 2026-04-13
architectural principle: service-to-service = GraphQL + Qdrant + autotrain.
"""

from __future__ import annotations

import functools
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TraceConfig:
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "freya_service_traces"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    ollama_host: str = "http://localhost:11434"
    failure_mode: str = "log_and_continue"


@dataclass
class _Span:
    trace_id: str
    caller_service: str
    target_service: str
    operation: str
    inputs: Any
    started_at: float
    outputs: Any = None
    quality_signal: Optional[float] = None

    def record_output(self, outputs: Any) -> None:
        self.outputs = outputs

    def record_quality_signal(self, score: float) -> None:
        self.quality_signal = score


class CallTracer:
    def __init__(self, caller_service: str, config: Optional[TraceConfig] = None) -> None:
        self._caller = caller_service
        self._config = config or TraceConfig()
        self._qdrant: Any = None
        self._embed: Optional[Callable[[str], Awaitable[list[float]]]] = None

    def _get_qdrant(self) -> Any:
        if self._qdrant is None:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams

                self._qdrant = QdrantClient(url=self._config.qdrant_url)
                try:
                    collections = [c.name for c in self._qdrant.get_collections().collections]
                    if self._config.qdrant_collection not in collections:
                        self._qdrant.create_collection(
                            collection_name=self._config.qdrant_collection,
                            vectors_config=VectorParams(
                                size=self._config.embedding_dim,
                                distance=Distance.COSINE,
                            ),
                        )
                except Exception as e:
                    logger.warning("call_telemetry: could not ensure Qdrant collection: %s", e)
            except Exception as e:
                logger.warning("call_telemetry: qdrant_client unavailable: %s", e)
                self._qdrant = None
        return self._qdrant

    async def _default_embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._config.ollama_host}/api/embeddings",
                    json={"model": self._config.embedding_model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                vec = data.get("embedding")
                if isinstance(vec, list) and len(vec) == self._config.embedding_dim:
                    return vec
                logger.warning("call_telemetry: unexpected embedding shape from ollama")
                return [0.0] * self._config.embedding_dim
        except Exception as e:
            logger.warning("call_telemetry: embedding failed: %s", e)
            return [0.0] * self._config.embedding_dim

    async def _get_embedding(self, text: str) -> list[float]:
        if self._embed is not None:
            try:
                return await self._embed(text)
            except Exception as e:
                logger.warning("call_telemetry: custom embed fn failed: %s", e)
                return [0.0] * self._config.embedding_dim
        return await self._default_embed(text)

    @asynccontextmanager
    async def trace(
        self,
        target_service: str,
        operation: str,
        inputs: Any,
    ) -> AsyncIterator[_Span]:
        span = _Span(
            trace_id=str(uuid.uuid4()),
            caller_service=self._caller,
            target_service=target_service,
            operation=operation,
            inputs=inputs,
            started_at=time.monotonic(),
        )
        success = True
        error_type: Optional[str] = None
        error_message: Optional[str] = None
        try:
            yield span
        except BaseException as e:
            success = False
            error_type = type(e).__name__
            error_message = str(e)[:2000]
            raise
        finally:
            duration_ms = (time.monotonic() - span.started_at) * 1000.0
            try:
                await self._emit(
                    span=span,
                    duration_ms=duration_ms,
                    success=success,
                    error_type=error_type,
                    error_message=error_message,
                )
            except Exception as e:
                logger.warning("call_telemetry: emit failed: %s", e)

    async def _emit(
        self,
        span: _Span,
        duration_ms: float,
        success: bool,
        error_type: Optional[str],
        error_message: Optional[str],
    ) -> None:
        def _safe_json(obj: Any) -> Any:
            try:
                json.dumps(obj)
                return obj
            except Exception:
                return {"__unserializable__": repr(obj)[:500]}

        inputs_safe = _safe_json(span.inputs)
        outputs_safe = _safe_json(span.outputs)

        embed_text = (
            f"{span.operation} :: "
            f"{json.dumps(inputs_safe)[:1500]} => "
            f"{json.dumps(outputs_safe)[:1500]}"
        )
        vec = await self._get_embedding(embed_text)

        payload = {
            "trace_id": span.trace_id,
            "caller_service": span.caller_service,
            "target_service": span.target_service,
            "operation": span.operation,
            "inputs": inputs_safe,
            "outputs": outputs_safe,
            "duration_ms": duration_ms,
            "success": success,
            "error_type": error_type,
            "error_message": error_message,
            "quality_signal": span.quality_signal,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            from qdrant_client.models import PointStruct
        except Exception as e:
            logger.warning("call_telemetry: qdrant_client unavailable: %s", e)
            return

        qdrant = self._get_qdrant()
        if qdrant is None:
            return

        try:
            qdrant.upsert(
                collection_name=self._config.qdrant_collection,
                points=[PointStruct(id=span.trace_id, vector=vec, payload=payload)],
            )
        except Exception as e:
            logger.warning("call_telemetry: qdrant upsert failed: %s", e)

    def traced(self, target_service: str, operation: str) -> Callable:
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                inputs = {"args": list(args), "kwargs": kwargs}
                async with self.trace(
                    target_service=target_service,
                    operation=operation,
                    inputs=inputs,
                ) as span:
                    result = await fn(*args, **kwargs)
                    span.record_output(result)
                    return result

            return wrapper

        return decorator
