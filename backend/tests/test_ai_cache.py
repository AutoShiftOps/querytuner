"""
Tests for the built-in sample-query AI cache (app/utils/ai_cache.py and its
wiring in /analyze): a repeat request for a sample query reuses the stored AI
output, makes no LLM call and does not spend the visitor's free daily AI limit,
while every other query is untouched.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import (
    anonymous_daily_store,
    app,
    free_ai_daily_store,
    get_current_user,
    pro_openai_daily_store,
    rate_limit_store,
    settings,
)
from app.utils import ai_cache
from app.utils import database as database_module

SAMPLES = json.loads(ai_cache.SAMPLES_PATH.read_text(encoding="utf-8"))
SAMPLE = SAMPLES[0]
LLM_CALLS: list[dict] = []


async def _fake_save_analysis(payload):
    return "fake-analysis-id"


async def _fake_increment_user_usage(user_id, month):
    return None


async def _fake_call_llm(prompt, provider=None, max_tokens=600, db_type="postgresql", model=None):
    LLM_CALLS.append({"provider": provider, "model": model})
    return {"text": '{"most_impactful_improvements": []}', "model": model or "fake-model", "error": None}


async def _fake_usage(user_id, month):
    return {"count": 0, "is_pro": False, "limit": 10}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr("app.main.save_analysis", _fake_save_analysis)
    monkeypatch.setattr("app.main.get_user_usage", _fake_usage)
    monkeypatch.setattr("app.main.increment_user_usage", _fake_increment_user_usage)
    monkeypatch.setattr(database_module, "get_user_usage", _fake_usage)
    monkeypatch.setattr("app.agents.sql_analyzer.call_llm", _fake_call_llm)
    for store in (anonymous_daily_store, rate_limit_store, pro_openai_daily_store, free_ai_daily_store):
        store.clear()
    LLM_CALLS.clear()
    ai_cache.clear()
    app.dependency_overrides[get_current_user] = lambda: "user_cache_test"
    yield
    app.dependency_overrides.clear()
    ai_cache.clear()


def _body(sample=SAMPLE, **extra):
    return {"query": sample["sql"], "db_type": sample["db_type"], "use_llm": True, "llm_provider": "anthropic", **extra}


def test_all_nine_samples_are_registered():
    assert len(SAMPLES) == 9
    assert len(ai_cache.SAMPLE_SIGNATURES) == 9


def test_second_sample_request_reuses_ai_output_and_skips_llm():
    client = TestClient(app)
    first = client.post("/analyze", json=_body())
    second = client.post("/analyze", json=_body())
    assert first.status_code == second.status_code == 200
    assert len(LLM_CALLS) == 1
    assert second.json()["used_ai"] is True
    assert second.json()["ai_insights"] == first.json()["ai_insights"]


def test_cache_hit_does_not_spend_the_free_daily_ai_limit(monkeypatch):
    monkeypatch.setattr(settings, "free_ai_daily_limit", 1)
    client = TestClient(app)
    assert client.post("/analyze", json=_body()).status_code == 200  # uses the 1 allowed AI call
    for _ in range(3):
        assert client.post("/analyze", json=_body()).status_code == 200  # served from cache
    other = {"query": "SELECT id FROM accounts WHERE email = 'x@example.com'", "db_type": "postgresql"}
    resp = client.post("/analyze", json={**other, "use_llm": True, "llm_provider": "anthropic"})
    assert resp.status_code == 429  # a non-sample query still counts
    assert resp.json()["error"] == "free_ai_daily_limit_reached"
    assert len(LLM_CALLS) == 1


def test_non_sample_query_is_never_cached():
    client = TestClient(app)
    body = {
        "query": "SELECT id FROM accounts WHERE email = 'x@example.com'",
        "db_type": "postgresql",
        "use_llm": True,
        "llm_provider": "anthropic",
    }
    client.post("/analyze", json=body)
    client.post("/analyze", json=body)
    assert len(LLM_CALLS) == 2


def test_schema_or_explain_plan_bypasses_the_cache():
    client = TestClient(app)
    client.post("/analyze", json=_body())
    client.post("/analyze", json=_body(schema_info="CREATE TABLE users (id int primary key);"))
    assert len(LLM_CALLS) == 2


def test_cache_key_is_per_provider_and_model():
    sql, db = SAMPLE["sql"], SAMPLE["db_type"]
    a = ai_cache.cache_key(sql, db, "anthropic", "m1", "performance", None, None)
    b = ai_cache.cache_key(sql, db, "anthropic", "m2", "performance", None, None)
    c = ai_cache.cache_key(sql, db, "openai", "m1", "performance", None, None)
    assert a and b and c and len({a, b, c}) == 3
    assert ai_cache.cache_key(sql + " -- tweak", db, "anthropic", "m1", "performance", None, None) is None


def test_whitespace_differences_still_match_a_sample():
    sql = SAMPLE["sql"].replace("\n", "   \n  ")
    assert ai_cache.cache_key(sql, SAMPLE["db_type"], "anthropic", "m", "performance", None, None) is not None


def test_entries_expire(monkeypatch):
    key = ai_cache.cache_key(SAMPLE["sql"], SAMPLE["db_type"], "anthropic", "m", "performance", None, None)
    ai_cache.put(key, {"ai_insights": "x", "ai_model": "m"})
    assert ai_cache.get(key) is not None
    monkeypatch.setattr(ai_cache, "CACHE_TTL_SECONDS", -1)
    assert ai_cache.get(key) is None


def test_failed_or_empty_ai_output_is_not_cached():
    key = ai_cache.cache_key(SAMPLE["sql"], SAMPLE["db_type"], "anthropic", "m", "performance", None, None)
    ai_cache.put(key, {"ai_insights": "", "ai_model": "m"})
    assert ai_cache.get(key) is None
