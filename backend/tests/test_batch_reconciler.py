"""
Tests for backend/app/tools/batch_reconciler.py — Issue #115.

Per the design doc's own risk framing, prioritizes the two reconciliation
moves it explicitly asks for: subset/superset collapse (over-indexing)
and column-order-conflict flagging (#117's ordering meeting a real
cross-query disagreement) — over broader coverage of every possible
suggestion shape.
"""

from app.tools.batch_reconciler import reconcile_index_suggestions


def _suggestion(type_="index_review_where_filter", columns=None, suggestion="text"):
    return {
        "type": type_,
        "severity": "high",
        "suggestion": suggestion,
        "reason": "...",
        "estimated_improvement": "...",
        "columns": columns or ["o.status"],
        "evidence_level": "needs-runtime-evidence",
    }


class TestSubsetSupersetCollapse:
    def test_single_column_subsumed_by_composite_on_same_table(self):
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"], suggestion="single-col")]),
            (
                1,
                [
                    _suggestion(
                        type_="index_review_composite_index",
                        columns=["o.customer_id", "o.status"],
                        suggestion="composite",
                    )
                ],
            ),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        kept_texts = {r.suggestion["suggestion"] for r in result.reconciled_suggestions}
        assert kept_texts == {"composite"}
        assert len(result.dropped_suggestions) == 1
        dropped = result.dropped_suggestions[0]
        assert dropped.columns == ["customer_id"]
        assert dropped.superseded_by_columns == ["customer_id", "status"]
        assert dropped.source_query_indices == [0]

    def test_surviving_superset_absorbs_dropped_queries(self):
        """A query that only asked for the narrower subset should still
        show up as satisfied by the kept composite — it wasn't wrong, it
        was just redundant once the composite exists."""
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"])]),
            (1, [_suggestion(type_="index_review_composite_index", columns=["o.customer_id", "o.status"])]),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        assert len(result.reconciled_suggestions) == 1
        assert result.reconciled_suggestions[0].satisfies_queries == [0, 1]

    def test_chain_of_three_collapses_onto_largest(self):
        query_suggestions = [
            (0, [_suggestion(columns=["o.a"], suggestion="a")]),
            (1, [_suggestion(type_="index_review_composite_index", columns=["o.a", "o.b"], suggestion="ab")]),
            (
                2,
                [_suggestion(type_="index_review_composite_index", columns=["o.a", "o.b", "o.c"], suggestion="abc")],
            ),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        kept_texts = {r.suggestion["suggestion"] for r in result.reconciled_suggestions}
        assert kept_texts == {"abc"}
        assert {d.suggestion_text for d in result.dropped_suggestions} == {"a", "ab"}
        survivor = result.reconciled_suggestions[0]
        assert survivor.satisfies_queries == [0, 1, 2]

    def test_unrelated_column_sets_on_same_table_both_kept(self):
        """Neither is a subset of the other — no over-indexing signal,
        both stay."""
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"], suggestion="cust")]),
            (1, [_suggestion(columns=["o.status"], suggestion="status")]),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        assert {r.suggestion["suggestion"] for r in result.reconciled_suggestions} == {"cust", "status"}
        assert result.dropped_suggestions == []

    def test_different_tables_never_collapsed_against_each_other(self):
        """customer_id looking like a subset of another table's composite
        columns must never collapse across tables — same column NAME on
        two different tables is not the same index need."""
        schema = {"orders": {"customer_id": "int"}, "customers": {"customer_id": "int", "status": "text"}}
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"], suggestion="orders-cust")]),
            (
                1,
                [
                    _suggestion(
                        type_="index_review_composite_index",
                        columns=["c.customer_id", "c.status"],
                        suggestion="customers-composite",
                    )
                ],
            ),
        ]
        result = reconcile_index_suggestions(query_suggestions, schema)

        assert {r.suggestion["suggestion"] for r in result.reconciled_suggestions} == {
            "orders-cust",
            "customers-composite",
        }
        assert result.dropped_suggestions == []


class TestColumnOrderConflict:
    def test_same_set_different_order_flagged_not_merged(self):
        query_suggestions = [
            (
                0,
                [
                    _suggestion(
                        type_="index_review_composite_index",
                        columns=["o.customer_id", "o.status"],
                        suggestion="order-A",
                    )
                ],
            ),
            (
                1,
                [
                    _suggestion(
                        type_="index_review_composite_index",
                        columns=["o.status", "o.customer_id"],
                        suggestion="order-B",
                    )
                ],
            ),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        # Both variants stay as separate reconciled entries — not
        # auto-merged, per the design doc.
        assert {r.suggestion["suggestion"] for r in result.reconciled_suggestions} == {"order-A", "order-B"}
        assert result.dropped_suggestions == []

        assert len(result.column_order_conflicts) == 1
        conflict = result.column_order_conflicts[0]
        assert conflict.columns == ["customer_id", "status"]
        variant_orders = {tuple(v["order"]) for v in conflict.variants}
        assert variant_orders == {("customer_id", "status"), ("status", "customer_id")}

    def test_identical_order_from_two_queries_merges_into_one_entry(self):
        query_suggestions = [
            (0, [_suggestion(type_="index_review_composite_index", columns=["o.customer_id", "o.status"])]),
            (1, [_suggestion(type_="index_review_composite_index", columns=["o.customer_id", "o.status"])]),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        assert len(result.reconciled_suggestions) == 1
        assert result.reconciled_suggestions[0].satisfies_queries == [0, 1]
        assert result.column_order_conflicts == []


class TestTableResolution:
    def test_schema_resolves_different_aliases_to_the_same_table(self):
        schema = {"orders": {"customer_id": "int", "status": "text"}}
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"], suggestion="via-o")]),
            (1, [_suggestion(columns=["ord.customer_id"], suggestion="via-ord")]),
        ]
        result = reconcile_index_suggestions(query_suggestions, schema)

        # Same real table + same column -> collapses into one entry
        # (identical column sets merge like the "identical order" case).
        assert len(result.reconciled_suggestions) == 1
        assert result.reconciled_suggestions[0].table == "orders"
        assert result.reconciled_suggestions[0].satisfies_queries == [0, 1]
        assert result.warnings == []

    def test_unresolved_alias_still_reconciles_but_warns(self):
        query_suggestions = [
            (0, [_suggestion(columns=["o.customer_id"])]),
            (1, [_suggestion(type_="index_review_composite_index", columns=["o.customer_id", "o.status"])]),
        ]
        result = reconcile_index_suggestions(query_suggestions)  # no schema

        assert len(result.dropped_suggestions) == 1  # still collapsed
        assert result.warnings  # but flagged as alias-based, not schema-verified

    def test_unaliased_suggestions_from_different_queries_never_merge(self):
        """No alias at all -> no safe table identity signal; must not
        assume two unaliased suggestions from different queries are about
        the same table."""
        query_suggestions = [
            (0, [_suggestion(columns=["status"], suggestion="q0")]),
            (1, [_suggestion(columns=["status"], suggestion="q1")]),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        assert len(result.reconciled_suggestions) == 2
        assert result.dropped_suggestions == []


class TestNonIndexTypesIgnored:
    def test_non_index_review_types_never_appear_in_output(self):
        query_suggestions = [
            (
                0,
                [
                    {
                        "type": "cartesian_join",
                        "severity": "critical",
                        "suggestion": "x",
                        "reason": "",
                        "estimated_improvement": "",
                        "evidence_level": "deterministic",
                    }
                ],
            ),
        ]
        result = reconcile_index_suggestions(query_suggestions)

        assert result.reconciled_suggestions == []
        assert result.dropped_suggestions == []


class TestEmptyInputs:
    def test_no_queries(self):
        result = reconcile_index_suggestions([])
        assert result.reconciled_suggestions == []
        assert result.dropped_suggestions == []
        assert result.column_order_conflicts == []
        assert result.warnings == []

    def test_queries_with_no_suggestions(self):
        result = reconcile_index_suggestions([(0, []), (1, [])])
        assert result.reconciled_suggestions == []
