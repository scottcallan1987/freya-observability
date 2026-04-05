"""Named timeout profiles for external calls across Freya clusters.

Use these constants instead of hard-coding timeout seconds. The profiles are
deliberately coarse — four named tiers cover every call class in the system.

    FAST    — local/in-cluster service calls (health probes, internal HTTP)
    NORMAL  — generic outbound HTTP and database queries
    LLM     — Ollama, LiteLLM, vLLM, or any inference endpoint
    CRAWL   — web crawling, Common Crawl, Wayback — pages can be slow

Example:
    import httpx
    from freya_observability.timeouts import NORMAL

    async with httpx.AsyncClient(timeout=NORMAL) as client:
        resp = await client.get("https://example.com")
"""

FAST: float = 5.0
NORMAL: float = 30.0
LLM: float = 120.0
CRAWL: float = 300.0

__all__ = ["FAST", "NORMAL", "LLM", "CRAWL"]
