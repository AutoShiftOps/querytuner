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
    pro_openai_daily_store,
    rate_limit_store,
    settings,
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
    """anonymous_daily_store, rate_limit_store, and pro_openai_daily_store
    are module-level dicts shared across every test in the process (all
    keyed by the same TestClient IP, or by user_id for the Pro-OpenAI
    ceiling) — without clearing all three, an earlier test's requests would
    count against a later test's limit, including the pre-existing
    per-minute abuse throttle in rate_limit_middleware (unrelated to the
    anonymous-daily-limit logic under test here, but it shares the same
    /analyze path and IP key)."""
    anonymous_daily_store.clear()
    rate_limit_store.clear()
    pro_openai_daily_store.clear()
    yield
    anonymous_daily_store.clear()
    rate_limit_store.clear()
    pro_openai_daily_store.clear()


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


class TestOpenAiProGate:
    """Phase 4 audit (#53): the real, live gap this audit found — a
    signed-in free-tier user could select llm_provider="openai" and the
    backend honored it, with nothing checking is_pro anywhere in the call
    path. These pin the fix down."""

    def test_signed_in_free_tier_selecting_openai_gets_structured_403(self, client, monkeypatch):
        _patch_persistence(monkeypatch, is_pro=False)
        app.dependency_overrides[get_current_user] = lambda: "user_free_test"
        try:
            resp = client.post(
                "/analyze",
                json={
                    "query": SIMPLE_QUERY,
                    "db_type": "postgresql",
                    "use_llm": True,
                    "llm_provider": "openai",
                },
            )
            assert resp.status_code == 403
            body = resp.json()
            assert body["error"] == "pro_required"
            assert body["upgrade_available"] is True
        finally:
            app.dependency_overrides.clear()

    def test_signed_in_pro_selecting_openai_succeeds(self, client, monkeypatch):
        _patch_persistence(monkeypatch, is_pro=True)
        app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
        try:
            resp = client.post(
                "/analyze",
                json={
                    "query": SIMPLE_QUERY,
                    "db_type": "postgresql",
                    "use_llm": True,
                    "llm_provider": "openai",
                },
            )
            assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

    def test_signed_in_free_tier_selecting_huggingface_unaffected(self, client, monkeypatch):
        """The gate is OpenAI-specific — free tier must still be able to
        run heuristic-only or Hugging-Face-backed AI insights."""
        _patch_persistence(monkeypatch, is_pro=False)
        app.dependency_overrides[get_current_user] = lambda: "user_free_test"
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
        finally:
            app.dependency_overrides.clear()

    def test_free_tier_openai_selected_but_use_llm_false_unaffected(self, client, monkeypatch):
        """Selecting "openai" in the dropdown without checking "Use AI
        insights" must not trip the gate — the provider is irrelevant when
        no AI call is actually being requested."""
        _patch_persistence(monkeypatch, is_pro=False)
        app.dependency_overrides[get_current_user] = lambda: "user_free_test"
        try:
            resp = client.post(
                "/analyze",
                json={
                    "query": SIMPLE_QUERY,
                    "db_type": "postgresql",
                    "use_llm": False,
                    "llm_provider": "openai",
                },
            )
            assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()


class TestProOpenAiDailyCeiling:
    """Security-audit follow-up (2026-09-28): Pro accounts have no monthly
    analysis-count cap, so nothing previously bounded a compromised or
    scripted Pro token's real OpenAI spend except the shared per-IP burst
    rate limiter. These pin down the new per-user daily ceiling on
    OpenAI-provider calls specifically (settings.pro_openai_daily_limit).

    pro_openai_daily_limit is monkeypatched low (3, or 1/5 where noted) so
    each test only needs a handful of requests — well under the unrelated
    10-per-minute burst limiter these requests also pass through.
    """

    def test_pro_under_daily_ceiling_succeeds(self, client, monkeypatch):
        monkeypatch.setattr(settings, "pro_openai_daily_limit", 3)
        _patch_persistence(monkeypatch, is_pro=True)
        app.dependency_overrides[get_current_user] = lambda: "user_pro_ceiling_test"
        try:
            for i in range(3):
                resp = client.post(
                    "/analyze",
                    json={
                        "query": SIMPLE_QUERY,
                        "db_type": "postgresql",
                        "use_llm": True,
                        "llm_provider": "openai",
                    },
                )
                assert resp.status_code == 200, f"request {i + 1}/3 failed: {resp.text}"
        finally:
            app.dependency_overrides.clear()

    def test_pro_over_daily_ceiling_blocked_with_structured_429(self, client, monkeypatch):
        monkeypatch.setattr(settings, "pro_openai_daily_limit", 3)
        _patch_persistence(monkeypatch, is_pro=True)
        app.dependency_overrides[get_current_user] = lambda: "user_pro_ceiling_test"
        try:
            for _ in range(3):
                resp = client.post(
                    "/analyze",
                    json={
                        "query": SIMPLE_QUERY,
                        "db_type": "postgresql",
                        "use_llm": True,
                        "llm_provider": "openai",
                    },
                )
                assert resp.status_code == 200, resp.text

            resp = client.post(
                "/analyze",
                json={
                    "query": SIMPLE_QUERY,
                    "db_type": "postgresql",
                    "use_llm": True,
                    "llm_provider": "openai",
                },
            )
            assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
            body = resp.json()
            assert body["error"] == "pro_openai_daily_limit_reached"
            assert "message" in body
        finally:
            app.dependency_overrides.clear()

    def test_ceiling_is_per_user_not_global(self, client, monkeypatch):
        """A different Pro user must have their own independent ceiling —
        the store is keyed by user_id, not shared across every Pro caller."""
        monkeypatch.setattr(settings, "pro_openai_daily_limit", 1)
        _patch_persistence(monkeypatch, is_pro=True)

        app.dependency_overrides[get_current_user] = lambda: "user_pro_a"
        try:
            resp = client.post(
                "/analyze",
                json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": True, "llm_provider": "openai"},
            )
            assert resp.status_code == 200, resp.text
            resp = client.post(
                "/analyze",
                json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": True, "llm_provider": "openai"},
            )
            assert resp.status_code == 429
        finally:
            app.dependency_overrides.clear()

        app.dependency_overrides[get_current_user] = lambda: "user_pro_b"
        try:
            resp = client.post(
                "/analyze",
                json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": True, "llm_provider": "openai"},
            )
            assert resp.status_code == 200, "a different user's own ceiling must not be pre-exhausted"
        finally:
            app.dependency_overrides.clear()

    def test_ceiling_does_not_affect_huggingface(self, client, monkeypatch):
        """The ceiling only counts/gates the OpenAI provider — Hugging Face
        stays uncapped for Pro, same as before this change."""
        monkeypatch.setattr(settings, "pro_openai_daily_limit", 1)
        _patch_persistence(monkeypatch, is_pro=True)
        app.dependency_overrides[get_current_user] = lambda: "user_pro_hf_test"
        try:
            for i in range(3):
                resp = client.post(
                    "/analyze",
                    json={
                        "query": SIMPLE_QUERY,
                        "db_type": "postgresql",
                        "use_llm": True,
                        "llm_provider": "huggingface",
                    },
                )
                assert resp.status_code == 200, f"request {i + 1}/3 failed: {resp.text}"
            assert pro_openai_daily_store == {}
        finally:
            app.dependency_overrides.clear()

    def test_logs_warning_on_crossing_80_percent_of_ceiling(self, client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "pro_openai_daily_limit", 5)
        _patch_persistence(monkeypatch, is_pro=True)
        app.dependency_overrides[get_current_user] = lambda: "user_pro_warn_test"
        try:
            with caplog.at_level("WARNING", logger="app.main"):
                for _ in range(4):  # 4/5 == 80% exactly — must warn on this 4th call, not before
                    resp = client.post(
                        "/analyze",
                        json={
                            "query": SIMPLE_QUERY,
                            "db_type": "postgresql",
                            "use_llm": True,
                            "llm_provider": "openai",
                        },
                    )
                    assert resp.status_code == 200, resp.text
            warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
            assert any("80%" in msg and "user_pro_warn_test" in msg for msg in warnings), warnings
            # Exactly one warning, not one per call once past the threshold.
            assert sum("80%" in msg for msg in warnings) == 1
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


class TestWasSanitizedPersistence:
    """Issue #124: was_sanitized is self-reported by the client and must
    reach save_analysis() unchanged, but never leak into the response
    schema (it's persistence-only, like user_id)."""

    def test_was_sanitized_true_reaches_save_analysis(self, client, monkeypatch):
        captured = {}

        async def fake_save_analysis(payload):
            captured["was_sanitized"] = payload.get("was_sanitized")
            return "fake-analysis-id"

        _patch_persistence(monkeypatch)
        monkeypatch.setattr("app.main.save_analysis", fake_save_analysis)
        resp = client.post(
            "/analyze",
            json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False, "was_sanitized": True},
        )
        assert resp.status_code == 200, resp.text
        assert captured["was_sanitized"] is True
        assert "was_sanitized" not in resp.json()

    def test_was_sanitized_defaults_to_false(self, client, monkeypatch):
        captured = {}

        async def fake_save_analysis(payload):
            captured["was_sanitized"] = payload.get("was_sanitized")
            return "fake-analysis-id"

        _patch_persistence(monkeypatch)
        monkeypatch.setattr("app.main.save_analysis", fake_save_analysis)
        resp = client.post(
            "/analyze",
            json={"query": SIMPLE_QUERY, "db_type": "postgresql", "use_llm": False},
        )
        assert resp.status_code == 200, resp.text
        assert captured["was_sanitized"] is False
