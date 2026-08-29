"""
Tests for Phase 5 (#135) observability: GET /health's database check,
the X-Request-ID correlation-ID middleware, and check_database_health()
itself.

Sentry initialization isn't tested directly here — it's a straight
`if settings.sentry_dsn: sentry_sdk.init(...)` in main.py, and the whole
existing test suite already runs with SENTRY_DSN unset (see conftest.py /
.env.example: no test sets it), so every one of those 322+ tests is
already a regression test for "the app boots and every route works with
Sentry disabled." Nothing here needs to re-prove that.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils import database as database_module


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_reports_database_ok(client, monkeypatch):
    async def _fake_ok():
        return True

    monkeypatch.setattr("app.main.check_database_health", _fake_ok)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "ok"


def test_health_reports_database_unreachable_but_stays_200(client, monkeypatch):
    """The whole point of #135's health check: a Supabase outage must not
    make an uptime monitor think the entire product is down — the
    heuristic engine works fine without persistence."""

    async def _fake_down():
        return False

    monkeypatch.setattr("app.main.check_database_health", _fake_down)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "unreachable"


# ---------------------------------------------------------------------------
# X-Request-ID correlation-ID middleware
# ---------------------------------------------------------------------------


def test_request_id_generated_when_absent(client):
    resp = client.get("/health")
    request_id = resp.headers.get("x-request-id")
    assert request_id, "every response should carry an X-Request-ID"
    # Looks like a UUID4 — 36 chars, hyphens in the right places. Not a
    # strict format assertion (uuid.uuid4() guarantees this), just a
    # sanity check that it's not empty/malformed.
    assert len(request_id) == 36


def test_request_id_echoes_caller_supplied_value(client):
    resp = client.get("/health", headers={"X-Request-ID": "my-custom-trace-id"})
    assert resp.headers.get("x-request-id") == "my-custom-trace-id"


def test_request_id_differs_across_requests_without_one_supplied(client):
    first = client.get("/health").headers.get("x-request-id")
    second = client.get("/health").headers.get("x-request-id")
    assert first != second


# ---------------------------------------------------------------------------
# check_database_health()
# ---------------------------------------------------------------------------


def test_check_database_health_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(database_module.settings, "supabase_url", "")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "")
    import asyncio

    assert asyncio.run(database_module.check_database_health()) is False


def test_check_database_health_true_on_200(monkeypatch):
    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")

    def _handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(_handle)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(database_module.httpx, "AsyncClient", _FakeAsyncClient)

    import asyncio

    assert asyncio.run(database_module.check_database_health()) is True


def test_check_database_health_false_on_error_status(monkeypatch):
    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")

    def _handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    transport = httpx.MockTransport(_handle)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(database_module.httpx, "AsyncClient", _FakeAsyncClient)

    import asyncio

    assert asyncio.run(database_module.check_database_health()) is False


def test_check_database_health_false_on_network_error(monkeypatch):
    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")

    def _handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated network failure", request=request)

    transport = httpx.MockTransport(_handle)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(database_module.httpx, "AsyncClient", _FakeAsyncClient)

    import asyncio

    assert asyncio.run(database_module.check_database_health()) is False
