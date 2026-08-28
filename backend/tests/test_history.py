"""
Tests for GET /history (backend/app/main.py) — Phase 5, backlog #54.

Covers: anonymous callers get a structured 401 (not just a bare
sign-in-required, matching /analyze's other structured error shapes);
signed-in-but-not-Pro callers get a structured 403 — the data is gated
server-side, not just the frontend UI, same as /analyze's tier check;
signed-in Pro callers get the paginated list; limit/offset pass through
correctly and limit gets clamped to HISTORY_PAGE_SIZE_MAX; has_more is
derived from whether a full page came back.

get_user_usage and get_analysis_history are monkeypatched — these tests
never touch the network or real Supabase.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import HISTORY_PAGE_SIZE_MAX, app, get_current_user

client = TestClient(app)


def _fake_get_user_usage(*, is_pro):
    async def _inner(user_id, month):
        return {"count": 0, "is_pro": is_pro, "limit": 10}

    return _inner


def test_anonymous_gets_structured_401(monkeypatch):
    resp = client.get("/history")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "sign_in_required"
    assert body["sign_in_required"] is True


def test_signed_in_free_tier_gets_structured_403(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=False))
    app.dependency_overrides[get_current_user] = lambda: "user_free_test"
    try:
        resp = client.get("/history")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "pro_required"
        assert body["upgrade_available"] is True
    finally:
        app.dependency_overrides.clear()


def test_signed_in_pro_gets_history_list(monkeypatch):
    fake_items = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "db_type": "postgresql",
            "query_snippet": "SELECT * FROM orders WHERE status = 'pending'",
            "severity": "high",
            "issue_count": 3,
            "created_at": "2026-08-01T00:00:00+00:00",
        }
    ]

    async def fake_get_analysis_history(user_id, *, limit, offset, sanitized_only=False):
        assert user_id == "user_pro_test"
        assert limit == 20
        assert offset == 0
        assert sanitized_only is False
        return fake_items

    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    monkeypatch.setattr("app.main.get_analysis_history", fake_get_analysis_history)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.get("/history")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"] == fake_items
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert body["has_more"] is False  # fewer items than limit
    finally:
        app.dependency_overrides.clear()


def test_pagination_params_pass_through(monkeypatch):
    captured = {}

    async def fake_get_analysis_history(user_id, *, limit, offset, sanitized_only=False):
        captured["limit"] = limit
        captured["offset"] = offset
        return [{"id": str(i)} for i in range(limit)]  # a full page

    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    monkeypatch.setattr("app.main.get_analysis_history", fake_get_analysis_history)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.get("/history", params={"limit": 5, "offset": 10})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert captured == {"limit": 5, "offset": 10}
        assert body["has_more"] is True  # a full page came back -> might be more
    finally:
        app.dependency_overrides.clear()


def test_limit_clamped_to_max(monkeypatch):
    captured = {}

    async def fake_get_analysis_history(user_id, *, limit, offset, sanitized_only=False):
        captured["limit"] = limit
        return []

    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    monkeypatch.setattr("app.main.get_analysis_history", fake_get_analysis_history)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.get("/history", params={"limit": 9999})
        assert resp.status_code == 200, resp.text
        assert captured["limit"] == HISTORY_PAGE_SIZE_MAX
    finally:
        app.dependency_overrides.clear()


def test_negative_offset_clamped_to_zero(monkeypatch):
    captured = {}

    async def fake_get_analysis_history(user_id, *, limit, offset, sanitized_only=False):
        captured["offset"] = offset
        return []

    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    monkeypatch.setattr("app.main.get_analysis_history", fake_get_analysis_history)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.get("/history", params={"offset": -5})
        assert resp.status_code == 200, resp.text
        assert captured["offset"] == 0
    finally:
        app.dependency_overrides.clear()


def test_sanitized_filter_param_passes_through(monkeypatch):
    captured = {}

    async def fake_get_analysis_history(user_id, *, limit, offset, sanitized_only=False):
        captured["sanitized_only"] = sanitized_only
        return []

    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    monkeypatch.setattr("app.main.get_analysis_history", fake_get_analysis_history)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.get("/history", params={"sanitized": "true"})
        assert resp.status_code == 200, resp.text
        assert captured["sanitized_only"] is True

        resp = client.get("/history")
        assert resp.status_code == 200, resp.text
        assert captured["sanitized_only"] is False
    finally:
        app.dependency_overrides.clear()


# ── database.get_analysis_history: snippet truncation + issue_count ────────


@pytest.mark.asyncio
async def test_get_analysis_history_truncates_long_queries_and_counts_findings(monkeypatch):
    import httpx

    from app.utils import database as database_module

    long_query = "SELECT " + ", ".join(f"col_{i}" for i in range(100))  # well over 200 chars
    rows = [
        {
            "id": "aaaa",
            "db_type": "postgresql",
            "original_query": long_query,
            "severity": "high",
            "findings": [{"type": "a"}, {"type": "b"}, {"type": "c"}],
            "created_at": "2026-08-01T00:00:00+00:00",
        },
        {
            "id": "bbbb",
            "db_type": "mysql",
            "original_query": "SELECT 1",
            "severity": "low",
            "findings": [],
            "created_at": "2026-07-15T00:00:00+00:00",
        },
    ]

    async def fake_get(self, url, headers=None, params=None):
        return httpx.Response(200, json=rows, request=httpx.Request("GET", url))

    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await database_module.get_analysis_history("user_x", limit=20, offset=0)

    assert len(result) == 2
    # Truncated with an ellipsis, capped at _HISTORY_SNIPPET_CHARS, and the
    # full original_query is NOT included in the summary (list rows stay
    # light — GET /report/{id} has the full text).
    assert len(result[0]["query_snippet"]) <= database_module._HISTORY_SNIPPET_CHARS + 1
    assert result[0]["query_snippet"].endswith("…")
    assert "original_query" not in result[0]
    assert result[0]["issue_count"] == 3
    # Short query: no truncation.
    assert result[1]["query_snippet"] == "SELECT 1"
    assert result[1]["issue_count"] == 0


@pytest.mark.asyncio
async def test_get_analysis_history_returns_was_sanitized(monkeypatch):
    """Issue #124: the sanitized indicator's actual data source."""
    import httpx

    from app.utils import database as database_module

    rows = [
        {
            "id": "aaaa",
            "db_type": "postgresql",
            "original_query": "SELECT 1",
            "severity": "low",
            "findings": [],
            "created_at": "2026-08-01T00:00:00+00:00",
            "was_sanitized": True,
        },
        {
            "id": "bbbb",
            "db_type": "postgresql",
            "original_query": "SELECT 2",
            "severity": "low",
            "findings": [],
            "created_at": "2026-08-01T00:00:00+00:00",
            "was_sanitized": False,
        },
    ]

    async def fake_get(self, url, headers=None, params=None):
        return httpx.Response(200, json=rows, request=httpx.Request("GET", url))

    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await database_module.get_analysis_history("user_x", limit=20, offset=0)

    assert result[0]["was_sanitized"] is True
    assert result[1]["was_sanitized"] is False


@pytest.mark.asyncio
async def test_get_analysis_history_falls_back_when_was_sanitized_column_missing(monkeypatch):
    """Issue #124: a Supabase project that hasn't run migration 009 yet
    must not lose the ENTIRE history list over one unknown column — falls
    back to the pre-#124 column set, defaulting was_sanitized to False."""
    import httpx

    from app.utils import database as database_module

    call_count = {"n": 0}

    async def fake_get(self, url, headers=None, params=None):
        call_count["n"] += 1
        if "was_sanitized" in (params or {}).get("select", ""):
            return httpx.Response(
                400,
                json={"message": "column analyses.was_sanitized does not exist"},
                request=httpx.Request("GET", url),
            )
        rows = [
            {
                "id": "aaaa",
                "db_type": "postgresql",
                "original_query": "SELECT 1",
                "severity": "low",
                "findings": [],
                "created_at": "2026-08-01T00:00:00+00:00",
            }
        ]
        return httpx.Response(200, json=rows, request=httpx.Request("GET", url))

    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-key")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await database_module.get_analysis_history("user_x", limit=20, offset=0)

    assert call_count["n"] == 2  # first attempt (with column) + fallback retry
    assert len(result) == 1
    assert result[0]["was_sanitized"] is False


@pytest.mark.asyncio
async def test_get_analysis_history_empty_when_not_configured(monkeypatch):
    from app.utils import database as database_module

    monkeypatch.setattr(database_module.settings, "supabase_url", "")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "")

    result = await database_module.get_analysis_history("user_x", limit=20, offset=0)
    assert result == []
