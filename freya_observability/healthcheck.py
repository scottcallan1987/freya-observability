"""FastAPI router helper for standardised /health and /ready endpoints.

Every Freya service should mount one of these. Keeps the liveness
(``/health``) and readiness (``/ready``) contracts identical across clusters,
which matters because Docker healthchecks, Prometheus, and the Phase 5
auto-healer all rely on predictable semantics.

    /health  — liveness only. Always returns 200 if the process is up. Does
               not run any probes. This is what Docker's HEALTHCHECK hits —
               it should never call the database.

    /ready   — readiness. Runs every configured probe synchronously. Returns
               200 if all probes pass, 503 if any fail. Response body is a
               JSON map of probe name to "ok" or "error: <reason>".

Usage:
    from freya_observability.healthcheck import make_health_router

    def probe_rabbit():
        # raise on failure, return truthy on success
        return rabbit_client.is_connected()

    app = FastAPI()
    app.include_router(make_health_router(
        service_name="freya-seo-workers",
        probes={"rabbitmq": probe_rabbit, "redis": lambda: redis.ping()},
    ))
"""

from typing import Callable, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

ProbeFn = Callable[[], object]


def make_health_router(service_name: str, probes: Dict[str, ProbeFn]) -> APIRouter:
    """Build a router exposing /health (liveness) and /ready (readiness)."""
    router = APIRouter()

    @router.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"service": service_name, "status": "alive"})

    @router.get("/ready")
    def ready() -> JSONResponse:
        results: Dict[str, str] = {}
        all_ok = True
        for name, probe in probes.items():
            try:
                outcome = probe()
            except Exception as exc:  # noqa: BLE001
                results[name] = f"error: {type(exc).__name__}: {exc}"
                all_ok = False
                continue
            if outcome is False:
                results[name] = "error: probe returned false"
                all_ok = False
            else:
                results[name] = "ok"

        status_code = 200 if all_ok else 503
        return JSONResponse(
            {"service": service_name, "probes": results},
            status_code=status_code,
        )

    return router
