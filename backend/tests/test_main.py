"""
Tests for backend/app/main.py's /analyze endpoint — specifically the
anonymous-usage gates added to close the "anonymous users have no usage
limit at all" gap:

  1. AI insights (use_llm=True) require signing in, regardless of the
     anonymous daily IP count.
  2. Heuristic-only analysis stays open to anonymous callers, capped at
     ANONYMOUS_DAILY_LIMIT requests/day/IP.
  3. Signed-in free-tier and Pro users are unaffected by either gate — the
     anonymous checks only apply when user_id is None.

Supabase calls (save_analysis, get_user_usage, increment_user_usage) and the
actual LLM call are monkeypatched to fast in-memory fakes — these tests must
not depend on network access, real database state, or a configured AI
provider.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import (
    ANONYMOUS_DAILY_LIMIT,
    anonymous_daily_store,
    app,
    get_current_user,
    rate_limit_store,
)
from app.utils import database as database_module

SIMPLE_QUERY = "SELECT * FROM orders WHERE id = 1"


async def _fake_save_analysis(payload):
    return "fake-analysis-id"


async def _fake_increment_user_usage(user_id, month):
    return None


async def _fake_call_llm(prompt, provider=None, max_tokens=600, db_type="postgresql"):
    return {"text": '{"most_impactful_improvements": []}', "model": "fake-model", "error": None}


def _fake_get_user_usage(*, is_pro, count=0):
    async def _inner(user_id, month):
        return {"count": count, "is_pro": is_pro, "limit": 10}

    return _inner


def _patch_persistence(monkeypatch, *, is_pro=False, count=0):
    """main.py imported these names with `from .utils.database import ...`,
    so patching app.utils.database's copies alone wouldn't affect main.py's
    already-bound references — patch both. Also stubs the actual LLM call
    (imported into app.agents.sql_analyzer's namespace) so use_llm=True
    tests don't depend on network access or a configured AI provider."""
    fake_usage = _fake_get_user_usage(is_pro=is_pro, count=count)
    monkeypatch.setattr("app.main.save_analysis", _fake_save_analysis)
    monkeypatch.setattr("app.main.get_user_usage", fake_usage)
    monkeypatch.setattr("app.main.increment_user_usage", _fake_increment_user_usage)
    monkeypatch.setattr(database_module, "get_user_usage", fake_usage)
    monkeypatch.setattr("app.agents.sql_analyzer.call_llm", _fake_call_llm)


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """anonymous_daily_store and rate_limit_store are module-level dicts
    shared across every test in the process (all keyed by the same
    TestClient IP) — without clearing both, an earlier test's requests
    would count against a later test's limit, including the pre-existing
    per-minute abuse throttle in rate_limit_middleware (unrelated to the
    anonymous-daily-limit logic under test here, but it shares the same
    /analyze path and IP key)."""
    anonymous_daily_store.clear()
    rate_limit_store.clear()
    yield
    anonymous_daily_store.clear()
    rate_limit_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_anonymous_under_daily_limit_succeeds_heuristic_only(client, monkeypatch):
    _patch_persistence(monkeypatch)
    for i in range(ANONYMOUS_DAILY_LIMIT):
        resp = client.post(
            "/analyze",
            json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
        )
        assert resp.status_code == 200, f"request {i + 1}/{ANONYMOUS_DAILY_LIMIT} failed: {resp.text}"


def test_anonymous_over_daily_limit_blocked(client, monkeypatch):
    _patch_persistence(monkeypatch)
    for _ in range(ANONYMOUS_DAILY_LIMIT):
        resp = client.post(
            "/analyze",
            json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
        )
        assert resp.status_code == 200

    resp = client.post(
        "/analyze",
        json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "anonymous_limit_reached"
    assert body["sign_in_available"] is True


def test_anonymous_ai_request_blocked_regardless_of_daily_limit(client, monkeypatch):
    _patch_persistence(monkeypatch)
    # Zero prior requests against the daily limit — still must be blocked,
    # since the AI gate is unconditional for anonymous callers.
    resp = client.post(
        "/analyze",
        json={
            "query": SIMPLE_QUERY,
            "db_type": "postgresql",
            "use_llm": True,
            "llm_provider": "openai",
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "sign_in_required"
    assert body["sign_in_required"] is True
    # Confirm the daily store was never touched by the AI request — it's
    # rejected before the counting logic runs, not counted-then-rejected.
    assert anonymous_daily_store == {}


def test_signed_in_free_tier_unaffected_by_anonymous_gates(client, monkeypatch):
    _patch_persistence(monkeypatch, is_pro=False, count=2)
    app.dependency_overrides[get_current_user] = lambda: "user_free_test"
    try:
        # More requests than ANONYMOUS_DAILY_LIMIT — the anonymous daily cap
        # must not apply once user_id is set, and AI must be reachable.
        for _ in range(ANONYMOUS_DAILY_LIMIT + 2):
            resp = client.post(
                "/analyze",
                json={
                    "query": SIMPLE_QUERY,
                    "db_type": "postgresql",
                    "use_llm": True,
                    "llm_provider": "huggingface",
                },
            )
            assert resp.status_code == 200, resp.text
        assert anonymous_daily_store == {}
    finally:
        app.dependency_overrides.clear()


def test_signed_in_pro_unaffected_by_anonymous_gates(client, monkeypatch):
    _patch_persistence(monkeypatch, is_pro=True, count=50)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.post(
            "/analyze",
            json={
                "query": SIMPLE_QUERY,
                "db_type": "postgresql",
                "use_llm": True,
                "llm_provider": "huggingface",
            },
        )
        assert resp.status_code == 200, resp.text
        assert anonymous_daily_store == {}
    finally:
        app.dependency_overrides.clear()


def test_rate_limit_middleware_11th_request_returns_429_not_500(client, monkeypatch):
    """rate_limit_middleware() raises HTTPException(429, ...) directly
    inside an @app.middleware("http") function — Starlette does not route
    exceptions raised in middleware through FastAPI's normal exception
    handlers, so this always surfaced as a generic 500, not the intended
    429. Pro tier + high monthly count so all 10 warm-up requests succeed
    cleanly (200) and only the 11th exercises the middleware's own
    10-per-minute cap, isolated from the free-tier/anonymous gates."""
    _patch_persistence(monkeypatch, is_pro=True, count=0)
    app.dependency_overrides[get_current_user] = lambda: "user_ratelimit_test"
    try:
        for i in range(10):
            resp = client.post(
                "/analyze",
                json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
            )
            assert resp.status_code == 200, f"warm-up request {i + 1}/10 failed: {resp.text}"

        resp = client.post(
            "/analyze",
            json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
        )
        assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
        body = resp.json()
        # Matches the anonymous-limit 429 shape elsewhere in this app
        # ({error, message, ...} — see anonymous_limit_reached) rather than
        # FastAPI's default HTTPException {"detail": ...} shape, so the
        # frontend can handle every 429 the same structured way.
        assert body["error"] == "rate_limit_exceeded"
        assert "message" in body
    finally:
        app.dependency_overrides.clear()
