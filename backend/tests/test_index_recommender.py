"""
Tests for backend/app/tools/index_recommender.py — Phase 5 quick wins
#117 (composite-index column ordering) and #118 (write/storage cost
estimate per index recommendation).

#117: before this fix, _detect_composite_opportunity() built each
composite's column list in raw extraction order (WHERE columns, then JOIN
columns, then ORDER BY columns, in whatever order the parser happened to
find them) rather than standard composite-index ordering (equality
predicates first, then JOIN keys, then range/inequality predicates, then
sort-only columns last). A composite index with the wrong column order
can perform close to a single-column index or worse for the query it was
suggested for — a correctness gap, not just polish, per the design doc.

#118: every suggestion already carried estimated_improvement (the
read-side benefit) with no cost-side counterpart. cost_estimate is
heuristic-only (no live DB/row counts): column count, and column data
type when schema_info was provided. See _is_large_column_type's docstring
for why that type check is narrower than "any big-looking SQL type" —
query_parser.py's schema normalization discards information (length
specs, and varchar/char/text/clob all collapse into one canonical "text"
bucket) that would be needed for a broader check to be honest rather than
just plausible-looking.
"""

import asyncio

import pytest

from app.agents.sql_analyzer import SQLAnalyzerAgent
from app.tools.index_recommender import (
    _detect_composite_opportunity,
    _estimate_index_cost,
    _extract_where_columns,
    _is_large_column_type,
)


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


# ── #118: _is_large_column_type — narrow, honest large-type detection ──────


class TestIsLargeColumnType:
    @pytest.mark.parametrize("large_type", ["json", "blob", "longblob", "xml", "image", "JSON", "Blob"])
    def test_recognized_large_types(self, large_type):
        # Not "jsonb" — query_parser's alias groups normalize json/jsonb
        # to the single canonical string "json" before this function ever
        # sees it, same as varchar -> text; "jsonb" is never actually a
        # value schema[table][col] holds.
        assert _is_large_column_type(large_type) is True

    @pytest.mark.parametrize(
        "not_large",
        [
            None,
            "",
            "text",  # the exact bug this test guards: "text" is query_parser's
            # canonical bucket for varchar/char/nchar/text/clob alike — a
            # VARCHAR(20) status column normalizes to "text" too, so it
            # can't be trusted as a large-column signal.
            "integer",
            "timestamp",
            "boolean",
            "numeric",
            "uuid",
        ],
    )
    def test_not_flagged(self, not_large):
        assert _is_large_column_type(not_large) is False


# ── #118: _estimate_index_cost — three-tier label ───────────────────────────


class TestEstimateIndexCost:
    def test_single_column_no_schema_is_low(self):
        assert _estimate_index_cost(["status"], "<o_table>", {}) == "Low write cost"

    def test_two_to_three_columns_is_moderate(self):
        label = _estimate_index_cost(["status", "customer_id"], "<o_table>", {})
        assert label.startswith("Moderate write cost")
        assert "2-column composite" in label

        label3 = _estimate_index_cost(["a", "b", "c"], "<o_table>", {})
        assert label3.startswith("Moderate write cost")
        assert "3-column composite" in label3

    def test_four_plus_columns_is_higher(self):
        label = _estimate_index_cost(["a", "b", "c", "d"], "<o_table>", {})
        assert label.startswith("Higher write cost")
        assert "4-column composite" in label

    def test_large_type_column_noted_even_for_single_column(self):
        schema = {"orders": {"payload": "json"}}
        label = _estimate_index_cost(["payload"], "orders", schema)
        assert "large-text column" in label
        assert "`payload`" in label

    def test_short_varchar_normalized_to_text_does_not_trigger_large_note(self):
        # "text" here is query_parser's normalized form of VARCHAR(20) —
        # see TestIsLargeColumnType's test_not_flagged for why this must
        # not be treated as large.
        schema = {"orders": {"status": "text"}}
        label = _estimate_index_cost(["status"], "orders", schema)
        assert label == "Low write cost"

    def test_unresolved_table_placeholder_falls_back_to_count_only(self):
        # table_ph is a "<alias_table>" placeholder when the real table
        # couldn't be resolved from schema_info — schema.get() on that
        # finds nothing, which is the intended graceful fallback, not an
        # error.
        schema = {"orders": {"payload": "json"}}
        label = _estimate_index_cost(["payload"], "<o_table>", schema)
        assert label == "Low write cost"


# ── #118: end-to-end — cost_estimate present on real suggestions ───────────


def test_cost_estimate_present_on_single_column_and_composite_suggestions(analyzer):
    query = """
        SELECT o.id FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'pending'
        ORDER BY o.created_at DESC
    """
    suggestions = run(analyzer, query)
    index_suggs = [s for s in suggestions if s["type"].startswith("index_review_")]

    assert index_suggs, "Expected at least one index suggestion for this query"
    for s in index_suggs:
        assert s.get("cost_estimate"), f"{s['type']} is missing a cost_estimate"

    composites = composite_suggestions(suggestions)
    assert composites
    assert (
        "3-column composite" in composites[0]["cost_estimate"] or "Higher write cost" in composites[0]["cost_estimate"]
    )


def test_cost_estimate_flags_large_type_end_to_end(analyzer):
    query = "SELECT * FROM orders o WHERE o.payload = 'x'"
    schema = """
        CREATE TABLE orders (
          id INT PRIMARY KEY,
          payload JSON
        );
    """
    suggestions = run(analyzer, query)  # no schema_info — sanity baseline
    with_schema = asyncio.run(
        SQLAnalyzerAgent().analyze(
            query=query, db_type="postgresql", use_llm=False, focus="performance", schema_info=schema
        )
    )["optimization_suggestions"]

    payload_suggestion = next(s for s in with_schema if s["type"].startswith("index_review_"))
    assert "large-text column" in payload_suggestion["cost_estimate"]
    # Without schema_info, the same column can't be flagged as large —
    # there's genuinely no type information available.
    baseline_suggestion = next(s for s in suggestions if s["type"].startswith("index_review_"))
    assert "large-text column" not in baseline_suggestion["cost_estimate"]
