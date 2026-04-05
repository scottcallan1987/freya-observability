"""Opinionated retry decorators backed by tenacity.

Three named decorators, one per external call class. Do NOT add a generic
``retry_anything`` helper — the whole point is that call sites pick the
profile that matches the kind of dependency they talk to.

    @retry_external_http   — outbound HTTP to third parties. 3 attempts,
                             exponential 1→4s, retries on transport errors
                             and httpx timeouts only.
    @retry_inference       — LLM/inference endpoints (Ollama, LiteLLM, vLLM).
                             2 attempts, linear 5s. Retries on connection
                             errors only — NEVER on content-level failures.
    @retry_db              — database connections (MySQL, Postgres, Qdrant).
                             5 attempts, exponential 0.5→8s. Retries on
                             connection resets only.
"""

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

_HTTP_RETRYABLE = (
    httpx.TransportError,
    httpx.TimeoutException,
)

retry_external_http = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(_HTTP_RETRYABLE),
    reraise=True,
)

retry_inference = retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(5),
    retry=retry_if_exception_type(_HTTP_RETRYABLE + (ConnectionError,)),
    reraise=True,
)

retry_db = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    retry=retry_if_exception_type(ConnectionError),
    reraise=True,
)

__all__ = ["retry_external_http", "retry_inference", "retry_db"]
