"""
Tests for backend/app/tools/index_recommender.py — Phase 5 quick win #117:
composite-index column ordering.

Before this fix, _detect_composite_opportunity() built each composite's
column list in raw extraction order (WHERE columns, then JOIN columns,
then ORDER BY columns, in whatever order the parser happened to find
them) rather than standard composite-index ordering (equality predicates
first, then JOIN keys, then range/inequality predicates, then sort-only
columns last). A composite index with the wrong column order can perform
close to a single-column index or worse for the query it was suggested
for — a correctness gap, not just polish, per the design doc.
"""

import asyncio

import pytest

from app.tools.index_recommender import _detect_composite_opportunity, _extract_where_columns


def run(analyzer, query, db_type="postgresql", focus="performance"):
    return asyncio.run(analyzer.analyze(query=query, db_type=db_type, use_llm=False, focus=focus))[
        "optimization_suggestions"
    ]


def composite_suggestions(suggestions):
    return [s for s in suggestions if s["type"] == "index_review_composite_index"]


# ── _extract_where_columns: equality vs range classification ───────────────


class TestExtractWhereColumnsPredicateType:
    def test_equals_is_equality(self):
        cols = _extract_where_columns("status = 'active'")
        assert cols == [(None, "status", "equality")]

    def test_in_is_equality(self):
        cols = _extract_where_columns("status IN ('active', 'pending')")
        assert cols == [(None, "status", "equality")]

    def test_is_null_is_equality(self):
        cols = _extract_where_columns("deleted_at IS NULL")
        assert cols == [(None, "deleted_at", "equality")]

    @pytest.mark.parametrize(
        "clause,expected_col",
        [
            ("created_at > '2024-01-01'", "created_at"),
            ("amount >= 100", "amount"),
            ("amount <= 100", "amount"),
            ("age < 18", "age"),
            ("name LIKE 'A%'", "name"),
            ("created_at BETWEEN '2024-01-01' AND '2024-12-31'", "created_at"),
            ("status != 'archived'", "status"),
            ("status <> 'archived'", "status"),
            ("status NOT IN ('archived', 'deleted')", "status"),
        ],
    )
    def test_range_operators_are_range(self, clause, expected_col):
        cols = _extract_where_columns(clause)
        assert cols == [(None, expected_col, "range")]

    def test_mixed_clause_classifies_each_condition_independently(self):
        cols = _extract_where_columns("status = 'active' AND created_at > '2024-01-01'")
        assert (None, "status", "equality") in cols
        assert (None, "created_at", "range") in cols


# ── _detect_composite_opportunity: ordering ─────────────────────────────────


class TestDetectCompositeOpportunityOrdering:
    def test_equality_before_join_before_range_before_order_by(self):
        # WHERE: status = equality, created_at = range. JOIN: customer_id.
        # ORDER BY: name (sort-only, not otherwise referenced).
        where_cols = [
            ("o", "status", "equality"),
            ("o", "created_at", "range"),
        ]
        join_cols = [("o", "customer_id")]
        order_cols = [("o", "name")]

        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols)

        assert len(composites) == 1
        assert composites[0]["columns"] == ["status", "customer_id", "created_at", "name"]

    def test_ordering_note_appended_to_suggestion_text(self):
        where_cols = [("o", "status", "equality"), ("o", "created_at", "range")]
        join_cols = [("o", "customer_id")]
        order_cols = []

        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols)

        suggestion = composites[0]["suggestion"]
        assert "Column order:" in suggestion
        assert "`status` (equality filter)" in suggestion
        assert "`customer_id` (JOIN key)" in suggestion
        assert "`created_at` (range filter)" in suggestion
        # Order of the mentions in the text matches the actual column order.
        assert suggestion.index("`status`") < suggestion.index("`customer_id`") < suggestion.index("`created_at`")

    def test_column_used_in_both_where_equality_and_order_by_only_appears_once_in_equality_position(self):
        # A column that's both filtered on (equality) and sorted on should
        # land once, in the equality slot — not duplicated, and not pulled
        # to the end just because it's also in ORDER BY.
        where_cols = [("o", "status", "equality")]
        join_cols = [("o", "customer_id")]
        order_cols = [("o", "status"), ("o", "created_at")]

        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols)

        cols = composites[0]["columns"]
        assert cols.count("status") == 1
        assert cols.index("status") < cols.index("customer_id")

    def test_no_composite_when_fewer_than_two_columns(self):
        where_cols = [("o", "status", "equality")]
        composites = _detect_composite_opportunity(where_cols, [], [])
        assert composites == []

    def test_two_aliases_each_get_their_own_ordered_composite(self):
        # "id" is deliberately not used here — it's a recognized
        # primary-key name (_is_primary_key) and gets excluded from
        # composite consideration regardless of role, which isn't what
        # this test is checking.
        where_cols = [("o", "status", "equality"), ("c", "region", "equality")]
        join_cols = [("o", "customer_id"), ("c", "account_ref")]
        order_cols = [("o", "created_at"), ("c", "name")]

        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols)

        by_alias = {c["table_alias"]: c["columns"] for c in composites}
        assert by_alias["o"] == ["status", "customer_id", "created_at"]
        assert by_alias["c"] == ["region", "account_ref", "name"]


# ── End-to-end through the full analyzer, per the design doc's test ask ────


def test_composite_ddl_column_order_end_to_end(analyzer):
    """The design doc's explicit test ask: a query with WHERE-equality +
    JOIN + ORDER BY all present, asserting the DDL column order matches
    the rule — not just that a composite was suggested at all."""
    query = """
        SELECT o.id, o.total
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'pending'
        ORDER BY o.created_at DESC
    """
    suggestions = run(analyzer, query)
    composites = composite_suggestions(suggestions)
    o_composite = [c for c in composites if c["columns"][0] == "o.status"]

    assert o_composite, "Expected a composite index for the 'o' alias leading with the equality column"
    cols = o_composite[0]["columns"]
    # Equality (status) before JOIN key (customer_id) before ORDER BY-only (created_at).
    assert cols == ["o.status", "o.customer_id", "o.created_at"]
    assert "Column order:" in o_composite[0]["suggestion"]
