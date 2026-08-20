"""
Tests for Phase 5 quick win #116 — URL expiration and deletion for
shareable reports.

GET /report/{analysis_id} returned any analysis by UUID, forever, to
anyone with the link — no expiration. Fixed via a nullable
analyses.expires_at column (migration 008): save_analysis() sets a
default expiration window at write time, get_analysis() treats an
expired row exactly like a nonexistent one (same 404, no "this link used
to work" leak), and a new DELETE /report/{id} lets a signed-in owner
revoke their own link early via the same soft-delete mechanism
(expires_at = now()) rather than a hard DELETE.

Two layers covered: database.py's functions directly (against a fake
Supabase transport for the analyses table, so real PostgREST filter
behavior — the id AND user_id filter on expire_analysis's PATCH is the
actual authorization boundary, not just an app-level check — is exercised
for real), and the /report/{id} GET+DELETE routes via TestClient with
those functions mocked (matching this test suite's existing pattern in
test_main.py).
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_current_user
from app.utils import database as database_module

client = TestClient(app)

VALID_ID = "11111111-1111-1111-1111-111111111111"


# ── database.py: fake Supabase transport for the `analyses` table ──────────


class FakeAnalysesTable:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.path == "/rest/v1/analyses"
        query = parse_qs(request.url.query.decode())

        if request.method == "GET":
            row_id = query.get("id", [""])[0].removeprefix("eq.")
            row = self.rows.get(row_id)
            return httpx.Response(200, json=[row] if row else [])

        if request.method == "POST":
            import json

            body = json.loads(request.content)
            row_id = body.setdefault("id", f"generated-{len(self.rows) + 1}")
            self.rows[row_id] = body
            return httpx.Response(201, json=[body])

        if request.method == "PATCH":
            row_id = query.get("id", [""])[0].removeprefix("eq.")
            filter_user_id = query.get("user_id", [None])[0]
            row = self.rows.get(row_id)
            if not row:
                return httpx.Response(200, json=[])
            if filter_user_id is not None and row.get("user_id") != filter_user_id.removeprefix("eq."):
                return httpx.Response(200, json=[])  # filter matched nothing, PostgREST-style
            import json

            body = json.loads(request.content)
            row.update(body)
            return httpx.Response(200, json=[row])

        raise AssertionError(f"unexpected {request.method}")


@pytest.fixture
def fake_analyses(monkeypatch):
    fake = FakeAnalysesTable()
    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")

    transport = httpx.MockTransport(fake.handle)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(database_module.httpx, "AsyncClient", _FakeAsyncClient)
    return fake


class TestIsExpired:
    def test_none_never_expires(self):
        assert database_module._is_expired(None) is False

    def test_empty_string_never_expires(self):
        assert database_module._is_expired("") is False

    def test_malformed_string_treated_as_not_expired(self):
        assert database_module._is_expired("not-a-timestamp") is False

    def test_future_timestamp_not_expired(self):
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        assert database_module._is_expired(future) is False

    def test_past_timestamp_is_expired(self):
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        assert database_module._is_expired(past) is True


@pytest.mark.asyncio
async def test_save_analysis_sets_default_expiration(fake_analyses):
    await database_module.save_analysis({"original_query": "SELECT 1", "db_type": "postgresql"})

    post_requests = [r for r in fake_analyses.requests if r.method == "POST"]
    assert len(post_requests) == 1
    import json

    body = json.loads(post_requests[0].content)
    expires_at = datetime.fromisoformat(body["expires_at"])
    expected = datetime.now(UTC) + timedelta(days=database_module.ANALYSIS_EXPIRATION_DAYS)
    # Within a minute of the expected window — avoids flaking on exact timing.
    assert abs((expires_at - expected).total_seconds()) < 60


@pytest.mark.asyncio
async def test_get_analysis_returns_none_for_expired_row(fake_analyses):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "original_query": "SELECT 1", "expires_at": past}

    result = await database_module.get_analysis(VALID_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_analysis_returns_row_when_not_expired(fake_analyses):
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "original_query": "SELECT 1", "expires_at": future}

    result = await database_module.get_analysis(VALID_ID)
    assert result is not None
    assert result["id"] == VALID_ID


@pytest.mark.asyncio
async def test_get_analysis_returns_row_when_expires_at_is_null(fake_analyses):
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "original_query": "SELECT 1", "expires_at": None}

    result = await database_module.get_analysis(VALID_ID)
    assert result is not None


@pytest.mark.asyncio
async def test_expire_analysis_owned_by_caller_succeeds(fake_analyses):
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "user_id": "user_owner", "expires_at": None}

    result = await database_module.expire_analysis(VALID_ID, "user_owner")

    assert result is True
    assert database_module._is_expired(fake_analyses.rows[VALID_ID]["expires_at"]) is True


@pytest.mark.asyncio
async def test_expire_analysis_not_owned_by_caller_fails(fake_analyses):
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "user_id": "user_owner", "expires_at": None}

    result = await database_module.expire_analysis(VALID_ID, "user_someone_else")

    assert result is False
    # The row is untouched — the WHERE clause, not app logic, is what
    # prevented this.
    assert fake_analyses.rows[VALID_ID]["expires_at"] is None


@pytest.mark.asyncio
async def test_expire_analysis_anonymous_row_unreachable(fake_analyses):
    """Anonymous-authored analyses (user_id IS NULL) have no owner to
    authorize a delete against — no real caller's user_id can ever equal
    NULL in a PostgREST eq. filter, so this is naturally unreachable
    rather than needing a special-cased check."""
    fake_analyses.rows[VALID_ID] = {"id": VALID_ID, "user_id": None, "expires_at": None}

    result = await database_module.expire_analysis(VALID_ID, "any_user")

    assert result is False


@pytest.mark.asyncio
async def test_expire_analysis_nonexistent_row_fails(fake_analyses):
    result = await database_module.expire_analysis("does-not-exist", "user_owner")
    assert result is False


# ── /report/{id} routes ─────────────────────────────────────────────────────


def test_get_report_404_for_expired_analysis(monkeypatch):
    async def fake_get_analysis(analysis_id):
        return None  # get_analysis() already returns None for expired rows

    monkeypatch.setattr("app.main.get_analysis", fake_get_analysis)

    resp = client.get(f"/report/{VALID_ID}")
    assert resp.status_code == 404
    assert "expired" in resp.json()["detail"].lower()


def test_delete_report_requires_sign_in():
    resp = client.delete(f"/report/{VALID_ID}")
    assert resp.status_code == 401


def test_delete_report_invalid_id_returns_400():
    app.dependency_overrides[get_current_user] = lambda: "user_x"
    try:
        resp = client.delete("/report/short")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_delete_report_not_owned_returns_404(monkeypatch):
    async def fake_expire_analysis(analysis_id, user_id):
        return False

    monkeypatch.setattr("app.main.expire_analysis", fake_expire_analysis)
    app.dependency_overrides[get_current_user] = lambda: "user_x"
    try:
        resp = client.delete(f"/report/{VALID_ID}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_report_owned_succeeds(monkeypatch):
    captured = {}

    async def fake_expire_analysis(analysis_id, user_id):
        captured["analysis_id"] = analysis_id
        captured["user_id"] = user_id
        return True

    monkeypatch.setattr("app.main.expire_analysis", fake_expire_analysis)
    app.dependency_overrides[get_current_user] = lambda: "user_owner"
    try:
        resp = client.delete(f"/report/{VALID_ID}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "deleted"}
        assert captured == {"analysis_id": VALID_ID, "user_id": "user_owner"}
    finally:
        app.dependency_overrides.clear()
