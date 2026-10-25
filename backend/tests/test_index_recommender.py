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
import re

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


# ── Analysis correctness: only suggest indexes that can exist ────────────────

MULTI_JOIN = """SELECT u.id, u.name, u.email, recent.last_order_date, COUNT(oi.id) AS total_items
FROM users u
JOIN orders o ON o.user_id = u.id
JOIN order_items oi ON oi.order_id = o.id
JOIN (SELECT user_id, MAX(created_at) AS last_order_date FROM orders GROUP BY user_id) recent ON recent.user_id = u.id
WHERE YEAR(o.created_at) = 2024 AND u.status = 'active'
GROUP BY u.id, u.name, u.email, recent.last_order_date
ORDER BY total_items DESC;"""


def _index_columns(suggestions):
    return [c for s in suggestions if s["type"].startswith("index_review_") for c in s.get("columns", [])]


def test_no_index_on_derived_table_or_aggregate_alias(analyzer):
    cols = _index_columns(run(analyzer, MULTI_JOIN))
    assert not [c for c in cols if c.startswith("recent.")], cols
    assert "total_items" not in cols, cols


def test_group_by_columns_collapse_into_one_composite(analyzer):
    sugg = [s for s in run(analyzer, MULTI_JOIN) if s["type"] == "index_review_group_by_index"]
    assert len(sugg) == 1
    assert sugg[0]["columns"] == ["u.name", "u.email"]
    assert "ON users(" in sugg[0]["ddl_hint"] and "name, email" in sugg[0]["ddl_hint"]


def test_select_alias_correlated_subquery_not_indexed(analyzer):
    q = (
        "SELECT p.id, (SELECT COUNT(*) FROM order_items oi WHERE oi.product_id = p.id) AS times_ordered "
        "FROM products p WHERE p.category = 'electronics' ORDER BY times_ordered DESC"
    )
    assert "times_ordered" not in _index_columns(run(analyzer, q))


# ── Regression: indented multi-line SELECT lists (the app's own samples) ─────

INDENTED_MULTI_JOIN = """SELECT
  u.id,
  u.name,
  u.email,
  recent.last_order_date,
  COUNT(oi.id) AS total_items
FROM users u
JOIN orders o ON o.user_id = u.id
JOIN order_items oi ON oi.order_id = o.id
JOIN (
  SELECT user_id, MAX(created_at) AS last_order_date
  FROM orders
  GROUP BY user_id
) recent ON recent.user_id = u.id
WHERE YEAR(o.created_at) = 2024
  AND u.status = 'active'
GROUP BY u.id, u.name, u.email, recent.last_order_date
ORDER BY total_items DESC;"""


def test_indented_select_list_keeps_full_alias():
    from app.tools.query_parser import QueryParser

    items = QueryParser().parse(INDENTED_MULTI_JOIN)["select_items"]
    assert items[-1] == {"output": "total_items", "expr": "COUNT(oi.id)", "has_alias": True}


@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlserver", "oracle", "sqlite"])
def test_indented_sample_has_no_unindexable_suggestions(analyzer, db_type):
    cols = _index_columns(run(analyzer, INDENTED_MULTI_JOIN, db_type=db_type))
    assert "total_items" not in cols, (db_type, cols)
    assert not [c for c in cols if c.startswith("recent.")], (db_type, cols)


# ── Rollback names must match the CREATE statement ───────────────────────────


@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlserver", "oracle", "sqlite"])
def test_rollback_drops_the_index_that_create_names(analyzer, db_type):
    from app.tools.index_recommender import _index_name_from_ddl

    checked = 0
    for s in run(analyzer, INDENTED_MULTI_JOIN, db_type=db_type):
        if not s["type"].startswith("index_review_") or not s.get("rollback_ddl"):
            continue
        name = _index_name_from_ddl(s["ddl_hint"])
        assert name and name in s["rollback_ddl"], (db_type, s["ddl_hint"], s["rollback_ddl"])
        checked += 1
    assert checked >= 3


def test_group_by_composite_has_rollback(analyzer):
    sugg = [s for s in run(analyzer, INDENTED_MULTI_JOIN) if s["type"] == "index_review_group_by_index"]
    assert sugg and "idx_users_name_email" in sugg[0]["rollback_ddl"]


def test_oracle_partial_candidate_indexes_the_column_not_the_pk(analyzer):
    sugg = [s for s in run(analyzer, INDENTED_MULTI_JOIN, db_type="oracle") if "partial" in s["type"]]
    assert sugg and "(status)" in sugg[0]["ddl_hint"] and "(id)" not in sugg[0]["ddl_hint"]


def test_index_name_is_a_plain_identifier_for_quoted_schema_qualified_tables():
    from app.tools.index_recommender import _index_name

    assert _index_name("[dbo].[Metropolitan$Sales Header]", "No_") == "idx_Metropolitan_Sales_Header_No"
    assert _index_name('"public"."Order Items"', ["[Order No]"], "partial") == "idx_Order_Items_Order_No_partial"
    assert len(_index_name("orders", "x" * 100)) <= 63


@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlserver", "oracle", "sqlite"])
def test_bracketed_table_gives_valid_index_name_and_matching_rollback(analyzer, db_type):
    q = (
        "SELECT SH.No_ FROM [dbo].[Metropolitan$Sales Header] SH with(nolock) "
        "inner join @tmp t on t.id = SH.No_ where SH.[Order Status]=10000"
    )
    ddl = [s for s in run(analyzer, q, db_type=db_type) if s.get("ddl_hint")]
    assert ddl
    for s in ddl:
        name = re.search(r"INDEX(?:\s+CONCURRENTLY)?\s+(\S+)", s["ddl_hint"]).group(1)
        assert re.fullmatch(r"[A-Za-z_]\w*", name), s["ddl_hint"]
        if s.get("rollback_ddl"):
            assert name in s["rollback_ddl"]


BRACKETED_JOIN = (
    "SELECT SH.No_ FROM [dbo].[Metropolitan$Sales Header] SH "
    "INNER JOIN [dbo].[Metropolitan$Sales Linkup] SL ON SH.No_ = SL.[Document No] "
    "WHERE SH.[Order Status] = 10000"
)


def test_bracketed_tables_and_columns_get_join_key_indexes(analyzer):
    ddls = [s["ddl_hint"] for s in run(analyzer, BRACKETED_JOIN, db_type="sqlserver") if s.get("ddl_hint")]
    assert any("[dbo].[Metropolitan$Sales Linkup]([Document No])" in d for d in ddls), ddls
    assert any("[dbo].[Metropolitan$Sales Header](No_)" in d for d in ddls), ddls


@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlserver", "oracle", "sqlite"])
def test_every_rollback_uses_the_query_dialect(analyzer, db_type):
    for s in run(analyzer, BRACKETED_JOIN, db_type=db_type) + run(analyzer, INDENTED_MULTI_JOIN, db_type=db_type):
        rb = s.get("rollback_ddl")
        if rb and db_type != "postgresql":
            assert "CONCURRENTLY" not in rb, (db_type, s["type"], rb)


@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlserver", "oracle", "sqlite"])
def test_partial_index_never_targets_a_made_up_id_column(analyzer, db_type):
    for s in run(analyzer, BRACKETED_JOIN, db_type=db_type):
        if s["type"] == "index_review_partial_index_candidate":
            assert "(id)" not in s["ddl_hint"] and ", id)" not in s["ddl_hint"], s["ddl_hint"]


def test_commented_out_sql_produces_no_findings(analyzer):
    q = (
        "SELECT SH.No_ FROM [dbo].[Sales Header] SH INNER JOIN [dbo].[Sales Linkup] SL "
        "ON SH.No_ = SL.[Document No] WHERE SH.[Order Status] = 10000 --and SL.[CSR Assign To] in ('RETURNS')\n"
        "/* AND SL.[Hidden Col] = 1 */"
    )
    cols = [c for s in run(analyzer, q, db_type="sqlserver") for c in (s.get("columns") or [])]
    assert not any("CSR Assign To" in c or "Hidden Col" in c for c in cols), cols


def test_alias_in_later_statement_is_resolved(analyzer):
    q = (
        "DECLARE @t TABLE (id int);\n"
        "SELECT sll.[Sales Order No], COUNT(*) FROM [Sales Line Link] sll WITH(NOLOCK) "
        "LEFT JOIN [Scan History] bsh WITH(NOLOCK) ON bsh.[Order No] = sll.[Sales Order No] "
        "GROUP BY sll.[Sales Order No]"
    )
    ddls = [s["ddl_hint"] for s in run(analyzer, q, db_type="sqlserver") if s.get("ddl_hint")]
    assert ddls and not any("<sll_table>" in d for d in ddls), ddls


def test_single_column_index_dropped_when_composite_leads_with_it(analyzer):
    q = (
        "SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id "
        "WHERE o.status = 'paid' AND o.user_id = 5 ORDER BY o.created_at"
    )
    sugg = run(analyzer, q)
    leading = {s["columns"][0] for s in sugg if s["type"] == "index_review_composite_index"}
    singles = {
        s["columns"][0]
        for s in sugg
        if s["type"] in ("index_review_join_key", "index_review_where_filter", "index_review_order_by_index")
    }
    assert not (leading & singles), (leading, singles)
