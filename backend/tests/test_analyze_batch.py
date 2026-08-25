"""
Tests for POST /analyze/batch (backend/app/main.py) — Phase 5, #115/#120.

Covers: Pro-gating (same structured-error pattern as GET /history —
test_history.py's own docstring explains why that shape matters), a full
happy-path run against a real pg_stat_statements-shaped export
(top_n ranking, per-query suggestions, and #115's reconciliation all
actually wired together end to end, not just unit-tested in isolation),
and the unparseable-export 400 path.

get_user_usage is monkeypatched (never touches real Supabase), same as
test_history.py. Everything downstream of that (parsing, IndexRecommender,
reconciliation) is the real thing — no other mocking, since none of it
touches the network.
"""

import json

from fastapi.testclient import TestClient

from app.main import app, get_current_user

client = TestClient(app)


def _fake_get_user_usage(*, is_pro):
    async def _inner(user_id, month):
        return {"count": 0, "is_pro": is_pro, "limit": 10}

    return _inner


def test_anonymous_gets_structured_401():
    resp = client.post("/analyze/batch", json={"source": "pg_stat_statements", "export_text": "x"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "sign_in_required"
    assert body["sign_in_required"] is True


def test_signed_in_free_tier_gets_structured_403(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=False))
    app.dependency_overrides[get_current_user] = lambda: "user_free_test"
    try:
        resp = client.post("/analyze/batch", json={"source": "pg_stat_statements", "export_text": "x"})
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "pro_required"
        assert body["upgrade_available"] is True
    finally:
        app.dependency_overrides.clear()


def test_invalid_source_rejected_by_request_validation(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.post("/analyze/batch", json={"source": "not_a_real_source", "export_text": "x"})
        assert resp.status_code == 422  # FastAPI's own enum validation, before this endpoint's body runs
    finally:
        app.dependency_overrides.clear()


def test_unparseable_export_gets_400(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.post(
            "/analyze/batch",
            json={"source": "pg_stat_statements", "export_text": "this is not any recognizable export format"},
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_pro_user_gets_full_batch_analysis(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        export = json.dumps(
            [
                {
                    "query": "SELECT * FROM orders o WHERE o.customer_id = $1",
                    "calls": 500,
                    "total_exec_time": 9000.0,
                },
                {
                    "query": (
                        "SELECT * FROM orders o WHERE o.customer_id = $1 AND o.status = $2 ORDER BY o.created_at"
                    ),
                    "calls": 50,
                    "total_exec_time": 100.0,
                },
            ]
        )
        resp = client.post(
            "/analyze/batch",
            json={"source": "pg_stat_statements", "export_text": export, "top_n": 20},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["source"] == "pg_stat_statements"
        assert body["db_type"] == "postgresql"
        assert body["total_parsed"] == 2
        assert body["analyzed_count"] == 2
        assert len(body["queries"]) == 2
        # Ranked by total_time_ms descending — the 9000ms query first.
        assert body["queries"][0]["calls"] == 500
        assert body["queries"][0]["total_time_ms"] == 9000.0

        # #115's reconciliation: query 0's single-column customer_id
        # suggestion should be subsumed by query 1's composite
        # (customer_id, status) on the same table.
        reconciled_column_sets = [set(s["columns"] or []) for s in body["reconciled_index_suggestions"]]
        assert any({"o.customer_id", "o.status"} <= cols for cols in reconciled_column_sets)
        assert body["dropped_suggestions"], "expected the narrower customer_id-only suggestion to be dropped"
        assert any("customer_id" in d["columns"] for d in body["dropped_suggestions"])
    finally:
        app.dependency_overrides.clear()


def test_top_n_caps_analyzed_count(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        export = json.dumps(
            [{"query": f"SELECT * FROM t{i}", "calls": 1, "total_exec_time": float(i)} for i in range(10)]
        )
        resp = client.post(
            "/analyze/batch",
            json={"source": "pg_stat_statements", "export_text": export, "top_n": 3},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_parsed"] == 10
        assert body["analyzed_count"] == 3
        assert len(body["queries"]) == 3
        # Ranked descending by total_time_ms -> t9, t8, t7 survive.
        analyzed_queries = {q["query"] for q in body["queries"]}
        assert analyzed_queries == {"SELECT * FROM t9", "SELECT * FROM t8", "SELECT * FROM t7"}
    finally:
        app.dependency_overrides.clear()


def test_mysql_performance_schema_source_maps_to_mysql_db_type(monkeypatch):
    monkeypatch.setattr("app.main.get_user_usage", _fake_get_user_usage(is_pro=True))
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        export = json.dumps(
            [
                {
                    "digest_text": "SELECT * FROM `orders` WHERE `status` = ?",
                    "count_star": 10,
                    "sum_timer_wait": 1_000_000_000,
                }
            ]
        )
        resp = client.post("/analyze/batch", json={"source": "performance_schema", "export_text": export})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["db_type"] == "mysql"
        assert body["analyzed_count"] == 1
    finally:
        app.dependency_overrides.clear()
