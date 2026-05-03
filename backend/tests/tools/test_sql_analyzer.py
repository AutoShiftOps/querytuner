"""
tests/tools/test_index_recommender.py
pytest test suite for IndexRecommender — Issue #23
Run: pytest tests/tools/test_index_recommender.py -v
"""

import pytest
from backend.app.tools.index_recommender import IndexRecommender
from backend.app.tools.query_parser import QueryParser

recommender = IndexRecommender()
parser = QueryParser()


def analyze(sql: str, db_type: str = "postgresql"):
    parsed = parser.parse(sql)
    return recommender.recommend(sql, parsed, db_type=db_type)


# ── Fixture 1: JOIN key detected ─────────────────────────────────────────────
def test_join_key_detected():
    sql = """
        SELECT u.id, u.name, o.total
        FROM users u
        JOIN orders o ON o.user_id = u.id
        WHERE u.status = 'active'
    """
    suggestions = analyze(sql)
    types = [s["type"] for s in suggestions]
    assert any("join_key" in t for t in types), "Expected join_key suggestion for o.user_id"


# ── Fixture 2: WHERE range filter detected ───────────────────────────────────
def test_where_range_filter_detected():
    sql = """
        SELECT id, total
        FROM orders
        WHERE created_at >= '2024-01-01'
        ORDER BY created_at DESC
    """
    suggestions = analyze(sql)
    types = [s["type"] for s in suggestions]
    assert any("where_filter" in t for t in types), "Expected where_filter suggestion for created_at"


# ── Fixture 3: Composite index detected ─────────────────────────────────────
def test_composite_index_detected():
    sql = """
        SELECT u.id, u.name, o.total
        FROM users u
        JOIN orders o ON o.user_id = u.id
        WHERE o.created_at >= '2024-01-01'
        ORDER BY o.created_at DESC
    """
    suggestions = analyze(sql)
    types = [s["type"] for s in suggestions]
    assert any(
        "composite_index" in t for t in types
    ), "Expected composite_index suggestion for (user_id, created_at) on orders"


# ── Fixture 4: Low-cardinality partial index suggested ───────────────────────
def test_low_cardinality_partial_index():
    sql = """
        SELECT id, name
        FROM users
        WHERE status = 'active'
    """
    suggestions = analyze(sql)
    types = [s["type"] for s in suggestions]
    assert any(
        "partial_index" in t for t in types
    ), "Expected partial_index_candidate for low-cardinality 'status' column"


# ── Fixture 5: ORDER BY column without WHERE — order_by_index suggested ──────
def test_order_by_only_index():
    sql = """
        SELECT id, name, email
        FROM users
        ORDER BY created_at DESC
        LIMIT 100
    """
    suggestions = analyze(sql)
    types = [s["type"] for s in suggestions]
    assert any("order_by_index" in t for t in types), "Expected order_by_index suggestion for ORDER BY created_at"


# ── Fixture 6: No WHERE, no JOIN — no index suggestions ──────────────────────
def test_no_suggestions_for_simple_query():
    sql = "SELECT 1"
    suggestions = analyze(sql)
    assert suggestions == [], "Simple SELECT 1 should produce zero index suggestions"


@pytest.fixture
def cartesian_query():
    return "SELECT u.id, o.total FROM users u JOIN orders o WHERE u.status = 'active'"


def test_cartesian_join_detected(analyzer, cartesian_query):
    suggestions = analyzer._heuristic_suggestions(
        cartesian_query,
        parsed={},
        db_type="postgresql",
        focus="performance",
    )
    cartesian = [s for s in suggestions if s["type"] == "cartesian_join"]
    assert len(cartesian) == 1
    assert cartesian[0]["severity"] == "critical"


def test_valid_join_not_flagged(analyzer):
    query = """SELECT u.id, o.total FROM users u
               JOIN orders o ON o.user_id = u.id"""
    suggestions = analyzer._heuristic_suggestions(query, parsed={}, db_type="postgresql", focus="performance")
    cartesian = [s for s in suggestions if s["type"] == "cartesian_join"]
    assert len(cartesian) == 0


# ── Fixture 7: confirmed=False on all suggestions ────────────────────────────
def test_all_suggestions_confirmed_false():
    sql = """
        SELECT id FROM orders WHERE user_id = 1
    """
    suggestions = analyze(sql)
    assert suggestions, "Expected at least one suggestion"
    for s in suggestions:
        assert s.get("confirmed") is False, f"All heuristic suggestions must have confirmed=False, got: {s}"


# ── Fixture 8: DDL hint present and non-empty ────────────────────────────────
def test_ddl_hint_present():
    sql = """
        SELECT id FROM orders WHERE user_id = 1
    """
    suggestions = analyze(sql)
    for s in suggestions:
        assert s.get("ddl_hint"), f"Every suggestion must include a ddl_hint, got: {s}"


# ── Fixture 9: MySQL dialect produces correct DDL (no CONCURRENTLY) ──────────
def test_mysql_ddl_no_concurrently():
    sql = """
        SELECT id FROM orders WHERE user_id = 1
    """
    suggestions = analyze(sql, db_type="mysql")
    for s in suggestions:
        ddl = s.get("ddl_hint", "")
        assert "CONCURRENTLY" not in ddl, f"MySQL DDL must not include CONCURRENTLY: {ddl}"


# ── Fixture 10: Full test query — the live app screenshot query ───────────────
def test_full_screenshot_query():
    """
    This is the exact query that showed 0 issues in the live app.
    After #23, it must produce >= 3 suggestions.
    """
    sql = """
        SELECT u.id, u.name, o.total
        FROM users u
        JOIN orders o ON o.user_id = u.id
        WHERE u.status = 'active'
          AND o.created_at >= '2024-01-01'
        ORDER BY o.created_at DESC
    """
    suggestions = analyze(sql)
    assert len(suggestions) >= 3, (
        f"Expected >= 3 index suggestions for the screenshot query, got {len(suggestions)}:\n"
        + "\n".join(s["suggestion"] for s in suggestions)
    )
