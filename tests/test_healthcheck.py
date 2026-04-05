"""Tests for the health/readiness router helper."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from freya_observability.healthcheck import make_health_router


def _app_with(probes):
    app = FastAPI()
    app.include_router(make_health_router(service_name="test-svc", probes=probes))
    return TestClient(app)


class TestLivenessEndpoint:
    def test_health_is_200_with_no_probes(self):
        client = _app_with(probes={})
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"service": "test-svc", "status": "alive"}

    def test_health_ignores_broken_probes(self):
        def broken():
            raise RuntimeError("this should not be called by /health")
        client = _app_with(probes={"broken": broken})
        resp = client.get("/health")
        assert resp.status_code == 200


class TestReadinessEndpoint:
    def test_ready_returns_200_when_all_probes_ok(self):
        client = _app_with(probes={
            "db": lambda: True,
            "mq": lambda: True,
        })
        resp = client.get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "test-svc"
        assert body["probes"] == {"db": "ok", "mq": "ok"}

    def test_ready_returns_503_when_any_probe_fails(self):
        def bad():
            raise ConnectionError("nope")
        client = _app_with(probes={
            "db": lambda: True,
            "mq": bad,
        })
        resp = client.get("/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["probes"]["db"] == "ok"
        assert body["probes"]["mq"].startswith("error:")

    def test_ready_with_no_probes_is_200(self):
        client = _app_with(probes={})
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["probes"] == {}

    def test_probe_returning_false_is_treated_as_failure(self):
        client = _app_with(probes={"db": lambda: False})
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["probes"]["db"] == "error: probe returned false"
