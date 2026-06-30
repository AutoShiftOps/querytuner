import pytest

from app.agents.sql_analyzer import SQLAnalyzerAgent

# ── Shared fixture ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def analyzer():
    return SQLAnalyzerAgent()


def get_types(suggestions):
    """Extract heuristic type strings from a suggestions list."""
    return [s["type"] for s in suggestions]


def run(analyzer, query, db_type="postgresql", focus="performance"):
    """Run heuristics synchronously using a helper."""
    import asyncio

    return asyncio.run(analyzer.analyze(query=query, db_type=db_type, use_llm=False, focus=focus))[
        "optimization_suggestions"
    ]


# ── 1. SELECT * triggers column_selection ─────────────────────────────────────


def test_select_star(analyzer):
    suggestions = run(analyzer, "SELECT * FROM orders")
    assert "column_selection" in get_types(suggestions), "SELECT * should trigger column_selection heuristic"


# ── 2. SELECT * with alias also triggers ─────────────────────────────────────


def test_select_star_with_alias(analyzer):
    suggestions = run(analyzer, "SELECT * FROM orders o WHERE o.status = 'active'")
    assert "column_selection" in get_types(suggestions)


# ── 3. No WHERE clause triggers full_scan_risk ───────────────────────────────


def test_no_where_clause(analyzer):
    suggestions = run(analyzer, "SELECT id, name FROM customers")
    assert "full_scan_risk" in get_types(suggestions), "Missing WHERE should trigger full_scan_risk"


# ── 4. Query WITH WHERE does not trigger full_scan_risk ──────────────────────


def test_with_where_no_full_scan(analyzer):
    suggestions = run(analyzer, "SELECT id FROM customers WHERE id = 1")
    assert "full_scan_risk" not in get_types(suggestions)


# ── 5. LIKE with leading wildcard triggers like_wildcard ─────────────────────


def test_like_leading_wildcard(analyzer):
    suggestions = run(analyzer, "SELECT * FROM products WHERE name LIKE '%widget'")
    assert "like_wildcard" in get_types(suggestions), "LIKE '%value' should trigger like_wildcard heuristic"


# ── 6. LIKE with trailing wildcard only does NOT trigger ─────────────────────


def test_like_trailing_wildcard_only(analyzer):
    suggestions = run(analyzer, "SELECT id FROM products WHERE name LIKE 'widget%'")
    assert "like_wildcard" not in get_types(suggestions), "Trailing wildcard only should not trigger like_wildcard"


# ── 7. YEAR() in WHERE triggers function_in_where ────────────────────────────


def test_year_function_in_where(analyzer):
    suggestions = run(analyzer, "SELECT * FROM orders WHERE YEAR(created_at) = 2024")
    assert "function_in_where" in get_types(suggestions)


# ── 8. LOWER() in WHERE triggers function_in_where ───────────────────────────


def test_lower_function_in_where(analyzer):
    suggestions = run(analyzer, "SELECT id FROM users WHERE LOWER(email) = 'test@example.com'")
    assert "function_in_where" in get_types(suggestions)


# ── 9. MONTH() in WHERE triggers function_in_where ───────────────────────────


def test_month_function_in_where(analyzer):
    suggestions = run(analyzer, "SELECT * FROM invoices WHERE MONTH(invoice_date) = 3")
    assert "function_in_where" in get_types(suggestions)


# ── 10. ORDER BY without LIMIT triggers order_by_no_limit ───────────────────


def test_order_by_no_limit(analyzer):
    suggestions = run(analyzer, "SELECT id, name FROM products ORDER BY name")
    assert "order_by_no_limit" in get_types(suggestions)


# ── 11. ORDER BY WITH LIMIT does not trigger ─────────────────────────────────


def test_order_by_with_limit(analyzer):
    suggestions = run(analyzer, "SELECT id FROM products ORDER BY name LIMIT 20")
    assert "order_by_no_limit" not in get_types(suggestions)


# ── 12. 4+ JOINs triggers join_complexity ────────────────────────────────────


def test_join_complexity(analyzer):
    query = """
        SELECT o.id
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN products p ON o.product_id = p.id
        JOIN shipments s ON o.shipment_id = s.id
        JOIN payments pay ON o.payment_id = pay.id
    """
    suggestions = run(analyzer, query)
    assert "join_complexity" in get_types(suggestions), "4+ JOINs should trigger join_complexity"


# ── 13. JOIN without ON triggers cartesian_join ──────────────────────────────


def test_cartesian_join(analyzer):
    query = "SELECT * FROM orders JOIN customers WHERE orders.id > 0"
    suggestions = run(analyzer, query)
    assert "cartesian_join" in get_types(suggestions), "JOIN without ON should trigger cartesian_join as critical"


# ── 14. Cartesian join has critical severity ──────────────────────────────────


def test_cartesian_join_is_critical(analyzer):
    query = "SELECT * FROM orders JOIN customers WHERE orders.id > 0"
    suggestions = run(analyzer, query)
    cartesian = [s for s in suggestions if s["type"] == "cartesian_join"]
    assert cartesian, "cartesian_join finding should exist"
    assert cartesian[0]["severity"] == "critical"


# ── 15. 2+ subqueries triggers subquery_refactor ─────────────────────────────


def test_subquery_refactor(analyzer):
    query = """
        SELECT * FROM orders
        WHERE customer_id IN (SELECT id FROM customers WHERE region = 'US')
        AND product_id IN (SELECT id FROM products WHERE active = 1)
    """
    suggestions = run(analyzer, query)
    assert "subquery_refactor" in get_types(suggestions)


# ── 16. Issue #26: Correlated subquery IN SELECT triggers subquery_to_join ───


def test_subquery_to_join(analyzer):
    query = """
        SELECT
            o.id,
            (SELECT MAX(p.price) FROM products p WHERE p.id = o.product_id) AS max_price
        FROM orders o
    """
    suggestions = run(analyzer, query)
    assert "subquery_to_join" in get_types(
        suggestions
    ), "Correlated subquery in SELECT list should trigger subquery_to_join"


# ── 17. Issue #25: PostgreSQL :: cast in WHERE triggers implicit_cast ─────────


def test_implicit_cast_postgres_operator(analyzer):
    query = "SELECT id FROM users WHERE user_id::text = '123'"
    suggestions = run(analyzer, query, db_type="postgresql")
    assert "implicit_cast" in get_types(suggestions), "PostgreSQL :: cast in WHERE should trigger implicit_cast"


# ── 18. Issue #25: ID column vs string literal triggers implicit_cast ─────────


def test_implicit_cast_id_string(analyzer):
    query = "SELECT * FROM orders WHERE customer_id = '42'"
    suggestions = run(analyzer, query)
    assert "implicit_cast" in get_types(
        suggestions
    ), "Comparing ID column to string literal should trigger implicit_cast"


# ── 19. Security: DROP statement detected ─────────────────────────────────────


def test_security_drop_detected(analyzer):
    # result = run(analyzer, "DROP TABLE orders")
    # security issues come through optimization_suggestions focus=security
    # but DROP is caught in _security_checks — verify via full analyze
    import asyncio

    full = asyncio.run(analyzer.analyze(query="DROP TABLE orders", db_type="postgresql", use_llm=False))
    assert any(
        "DROP" in issue.upper() for issue in full["security_issues"]
    ), "DROP should be detected as a security issue"


# ── 20. Clean simple query returns no critical findings ───────────────────────


def test_clean_query_no_critical(analyzer):
    query = """
        SELECT id, name, email
        FROM customers
        WHERE status = 'active'
        ORDER BY created_at DESC
        LIMIT 50
    """
    suggestions = run(analyzer, query)
    critical = [s for s in suggestions if s.get("severity") == "critical"]
    assert not critical, f"Clean query should have no critical findings, got: {critical}"
