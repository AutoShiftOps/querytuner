"""
Comprehensive coverage for IndexRecommender + SQLAnalyzerAgent's heuristic layer.

Every scenario below was run against the live code first (not guessed) to
establish ground truth. Where the tool's actual behavior contradicts what a
DBA would reasonably expect, the test is marked xfail(strict=True) with the
concrete reason — these are documented regressions, not aspirational specs.
A strict xfail flips to a hard failure the moment someone fixes the
underlying code, so it can't silently rot into a permanent skip.
"""

import asyncio

import pytest

INDEX_SEVERITIES = {"critical", "high", "medium", "low"}
_UNRESOLVED_TEMPLATE = ("{table}", "{column}", "{name}")


def run(analyzer, query, db_type="postgresql", focus="performance"):
    return asyncio.run(analyzer.analyze(query=query, db_type=db_type, use_llm=False, focus=focus))[
        "optimization_suggestions"
    ]


def get_types(suggestions):
    return [s["type"] for s in suggestions]


def index_suggestions(suggestions):
    """Only the column-level suggestions produced by IndexRecommender."""
    return [s for s in suggestions if s["type"].startswith("index_review_")]


def columns_of(suggestions):
    """Flatten every column reference (e.g. 'o.customer_id') across index suggestions."""
    cols = set()
    for s in index_suggestions(suggestions):
        cols.update(s.get("columns") or [])
    return cols


def assert_well_formed(suggestions):
    """Shared shape contract for every index_review_* suggestion."""
    for s in index_suggestions(suggestions):
        assert s["confirmed"] is False, f"{s['type']} must be unconfirmed (heuristic, not EXPLAIN-verified)"
        assert s["severity"] in INDEX_SEVERITIES, f"{s['type']} has unexpected severity {s['severity']!r}"
        ddl = s.get("ddl_hint") or ""
        assert ddl, f"{s['type']} is missing a ddl_hint"
        for token in _UNRESOLVED_TEMPLATE:
            assert token not in ddl, f"{s['type']} ddl_hint has an unrendered template token: {ddl!r}"
        assert "<placeholder>" not in ddl.lower(), f"{s['type']} ddl_hint leaked a literal placeholder: {ddl!r}"


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 1 — Large schema, simple query
# ═══════════════════════════════════════════════════════════════════════════


def test_large_schema_where_on_nonindexed_column(analyzer):
    query = """
        SELECT id, first_name, last_name, email, phone, address_line1, address_line2,
               city, state, zip_code, country, created_at, updated_at, last_login_at,
               account_status
        FROM customers
        WHERE loyalty_tier = 'gold'
    """
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)

    idx = index_suggestions(suggestions)
    assert idx, "A WHERE filter on a non-indexed column must produce at least one index suggestion"
    assert "loyalty_tier" in columns_of(suggestions), "The real filtered column name must appear in suggestions"
    assert any(s["type"] == "index_review_where_filter" for s in idx)


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 2 — Medium complexity (3 JOINs, WHERE, GROUP BY, ORDER BY)
# ═══════════════════════════════════════════════════════════════════════════


def test_medium_complexity_join_where_groupby_orderby(analyzer):
    query = """
        SELECT o.id, c.name, p.title, COUNT(*) AS cnt
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN products p ON o.product_id = p.id
        JOIN shipments s ON o.shipment_id = s.id
        WHERE o.status = 'shipped' AND c.region = 'US'
        GROUP BY o.id, c.name, p.title
        ORDER BY o.created_at DESC
    """
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    cols = columns_of(suggestions)

    # All three JOIN keys must appear
    for join_key in ("o.customer_id", "o.product_id", "o.shipment_id"):
        assert join_key in cols, f"JOIN key {join_key} missing from suggestions"

    # WHERE columns must appear (o.status is low-cardinality -> partial index, not where_filter)
    assert "c.region" in cols
    assert any(
        s["type"] == "index_review_partial_index_candidate" and "o.status" in s["columns"]
        for s in index_suggestions(suggestions)
    ), "Low-cardinality WHERE column o.status should surface as a partial_index_candidate"

    # Composite index for the multi-column 'o' alias (status, customer_id, product_id, shipment_id, created_at)
    composites = [s for s in index_suggestions(suggestions) if s["type"] == "index_review_composite_index"]
    assert composites, "Composite index must be suggested when one alias has 2+ query-relevant columns"
    o_composite = [s for s in composites if s["columns"][0].startswith("o.")]
    assert o_composite, "Composite index for the 'o' alias specifically was not found"
    assert len(o_composite[0]["columns"]) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 3 — High complexity (5+ JOINs, correlated subqueries, CTEs)
# ═══════════════════════════════════════════════════════════════════════════

_HIGH_COMPLEXITY_QUERY = """
    WITH recent_orders AS (
        SELECT id, customer_id, total FROM orders WHERE created_at > '2024-01-01'
    )
    SELECT c.id, c.name,
           (SELECT COUNT(*) FROM recent_orders ro WHERE ro.customer_id = c.id) AS order_count
    FROM customers c
    JOIN accounts a ON c.account_id = a.id
    JOIN regions r ON c.region_id = r.id
    JOIN tiers t ON c.tier_id = t.id
    JOIN sales_reps sr ON c.rep_id = sr.id
    JOIN territories ter ON sr.territory_id = ter.id
    WHERE c.status = 'active'
"""


def test_five_joins_with_cte_and_correlated_subquery_all_keys_found(analyzer):
    suggestions = run(analyzer, _HIGH_COMPLEXITY_QUERY)
    assert_well_formed(suggestions)
    cols = columns_of(suggestions)

    for join_key in ("c.account_id", "c.region_id", "c.tier_id", "c.rep_id", "sr.territory_id"):
        assert join_key in cols, f"JOIN key {join_key} missing — CTE or correlated subquery likely confused parsing"

    assert "subquery_refactor" in get_types(suggestions) or "subquery_to_join" in get_types(suggestions)


def test_cte_name_does_not_leak_into_or_break_table_extraction(analyzer):
    parsed = asyncio.run(analyzer.analyze(query=_HIGH_COMPLEXITY_QUERY, db_type="postgresql", use_llm=False))[
        "parsing_result"
    ]
    # Top-level FROM must resolve to 'customers', not the CTE body or a parse failure
    assert "customers" in parsed["tables"]


def test_subquery_alias_does_not_confuse_column_extraction(analyzer):
    query = "SELECT * FROM users u " "JOIN (SELECT id, customer_ref FROM orders) sub ON sub.customer_ref = u.id"
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    assert "sub.customer_ref" in columns_of(suggestions), "JOIN key on a derived-table alias must still be extracted"


def test_cartesian_join_still_fires_with_cte_present(analyzer):
    query = "WITH x AS (SELECT id FROM orders) SELECT * FROM x JOIN customers WHERE x.id > 0"
    suggestions = run(analyzer, query)
    assert "cartesian_join" in get_types(suggestions), "A CTE in the query must not mask a missing ON/USING clause"
    cartesian = [s for s in suggestions if s["type"] == "cartesian_join"][0]
    assert cartesian["severity"] == "critical"


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 4 — Edge cases that break regex-based parsers
# ═══════════════════════════════════════════════════════════════════════════


def test_underscore_and_numeric_column_names(analyzer):
    suggestions = run(analyzer, "SELECT * FROM orders WHERE order_id_2 = 5 AND user_uuid = 'abc'")
    assert_well_formed(suggestions)
    cols = columns_of(suggestions)
    assert "order_id_2" in cols
    assert "user_uuid" in cols


def test_schema_qualified_table_names_join_keys_still_found(analyzer):
    query = "SELECT * FROM public.orders o JOIN dbo.customers c ON o.customer_id = c.customer_id"
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    cols = columns_of(suggestions)
    assert "o.customer_id" in cols
    assert "c.customer_id" in cols


def test_quoted_identifiers_produce_index_suggestion(analyzer):
    suggestions = run(analyzer, 'SELECT * FROM "Order" WHERE "Total Amount" > 100')
    assert index_suggestions(suggestions), "Quoted-identifier WHERE column should still be recommended"


def test_using_clause_produces_join_key_suggestion(analyzer):
    query = "SELECT * FROM orders o JOIN customers c USING (customer_ref)"
    suggestions = run(analyzer, query)
    assert any(s["type"] == "index_review_join_key" for s in index_suggestions(suggestions))


def test_multiple_conditions_in_on_clause_all_captured(analyzer):
    query = "SELECT * FROM orders o JOIN customers c " "ON o.customer_id = c.id AND o.region_code = c.region_code"
    suggestions = run(analyzer, query)
    cols = columns_of(suggestions)
    assert "o.customer_id" in cols
    assert "o.region_code" in cols, "Second AND condition in ON clause was not scanned"


def test_implicit_comma_join_where_columns_detected(analyzer):
    query = "SELECT * FROM orders o, customers c WHERE o.customer_id = c.customer_id"
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    assert "o.customer_id" in columns_of(
        suggestions
    ), "Implicit comma-join condition in WHERE must still yield a column suggestion"


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 5 — Dialect-specific patterns
# ═══════════════════════════════════════════════════════════════════════════


def test_oracle_rownum_is_not_recommended_as_an_indexable_column(analyzer):
    suggestions = run(analyzer, "SELECT * FROM orders WHERE ROWNUM <= 10", db_type="oracle")
    idx = index_suggestions(suggestions)
    assert not any(
        "ROWNUM" in s.get("columns", []) for s in idx
    ), "ROWNUM is a pseudo-column, not a real column — it must never appear in a CREATE INDEX hint"


def test_sqlserver_top_n_where_column_still_detected(analyzer):
    suggestions = run(analyzer, "SELECT TOP 10 * FROM orders WHERE status = 'open'", db_type="sqlserver")
    assert_well_formed(suggestions)
    idx = index_suggestions(suggestions)
    assert any("status" in s.get("columns", []) for s in idx), "TOP N syntax must not block WHERE-column extraction"


def test_postgres_ilike_where_column_detected(analyzer):
    suggestions = run(analyzer, "SELECT id FROM customers WHERE name ILIKE '%smith%'", db_type="postgresql")
    idx = index_suggestions(suggestions)
    assert any("name" in s.get("columns", []) for s in idx), "ILIKE filter column must still be recommended"


def test_mysql_straight_join_hint_join_key_detected(analyzer):
    query = (
        "SELECT STRAIGHT_JOIN o.id FROM orders o "
        "JOIN customers c ON o.customer_id = c.customer_id WHERE o.status = 'open'"
    )
    suggestions = run(analyzer, query, db_type="mysql")
    assert_well_formed(suggestions)
    cols = columns_of(suggestions)
    assert "o.customer_id" in cols
    assert "c.customer_id" in cols
    # MySQL DDL dialect check: ALTER TABLE ... ADD INDEX, never CONCURRENTLY (PostgreSQL-only)
    for s in index_suggestions(suggestions):
        assert "CONCURRENTLY" not in s["ddl_hint"]


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 6 — The specific failure modes reported
# ═══════════════════════════════════════════════════════════════════════════


def test_join_on_subquery_alias_specific_failure_mode(analyzer):
    query = "SELECT * FROM u JOIN (SELECT id FROM orders) sub ON sub.id = u.id"
    # Even when the extracted column is the suppressed PK-style name 'id',
    # the query must parse cleanly and return a (possibly empty) suggestion list —
    # not raise.
    suggestions = run(analyzer, query)
    assert isinstance(suggestions, list)


def test_cte_reference_where_clause_detected(analyzer):
    query = """
        WITH active AS (SELECT id, status, region FROM customers WHERE status = 'active')
        SELECT * FROM active WHERE region = 'US'
    """
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    assert "region" in columns_of(suggestions), "WHERE column referenced via a CTE alias must be extracted"


def test_window_function_partition_by_does_not_produce_order_by_index(analyzer):
    query = """
        SELECT customer_id, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at) AS rn
        FROM orders
    """
    suggestions = run(analyzer, query)
    assert_well_formed(suggestions)
    # The ORDER BY lives inside OVER(...), not at query top-level — it must not
    # generate a column-level order_by_index suggestion.
    assert not any(
        s["type"] == "index_review_order_by_index" for s in index_suggestions(suggestions)
    ), "ORDER BY inside a window function's OVER() clause must not be treated as a query-level ORDER BY"


def test_window_function_order_by_does_not_trigger_naive_order_by_no_limit(analyzer):
    query = """
        SELECT customer_id, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at) AS rn
        FROM orders
    """
    suggestions = run(analyzer, query)
    assert "order_by_no_limit" not in get_types(suggestions)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: the join-column regex only scans the top-level query text for "
        "'ON <col> = <col>'. A LATERAL join's correlation lives inside a nested "
        "subquery's own WHERE clause (paren depth > 0), which top-level extraction "
        "never sees — the correlated column is completely invisible to the recommender."
    ),
)
def test_lateral_join_correlated_column_detected(analyzer):
    query = """
        SELECT u.id, x.total
        FROM users u
        JOIN LATERAL (SELECT SUM(amount) AS total FROM orders o WHERE o.user_id = u.id) x ON true
    """
    suggestions = run(analyzer, query)
    idx = index_suggestions(suggestions)
    assert idx, "The correlated column inside a LATERAL join's subquery should surface an index suggestion"


def test_lateral_join_does_not_crash(analyzer):
    query = """
        SELECT u.id, x.total
        FROM users u
        JOIN LATERAL (SELECT SUM(amount) AS total FROM orders o WHERE o.user_id = u.id) x ON true
    """
    suggestions = run(analyzer, query)
    assert isinstance(suggestions, list)
