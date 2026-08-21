"""
Tests for backend/app/tools/plan_crossref.py — Issue #63, the part of the
EXPLAIN-parser chain that actually makes QueryInput.jsx's UI promise true.
#61/#62 alone just produce another unused facts blob; this is what reads
it.

Per the design doc's own risk assessment, this is the one place in the
whole chain where a wrong answer is worse than no answer — a false
"schema-verified" upgrade actively misleads a user into trusting a bad
recommendation — so this file prioritizes the cross-referencing logic
itself (does it correctly match plan table/column names back to
suggestion table/column names) over broadening node-type coverage, per
the doc's explicit test-priority instruction.
"""

from app.tools.plan_crossref import cross_reference_plan
from app.tools.plan_parsers.models import PlanNode


def _suggestion(type_="index_review_where_filter", columns=None, evidence_level="needs-runtime-evidence"):
    return {
        "type": type_,
        "severity": "high",
        "suggestion": "WHERE column may lack an index",
        "reason": "...",
        "estimated_improvement": "...",
        "columns": columns or ["o.status"],
        "evidence_level": evidence_level,
    }


class TestConfirmation:
    def test_full_scan_on_matching_alias_upgrades_evidence(self):
        suggestions = [_suggestion(columns=["o.status"])]
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", alias="o", rows=10000, is_full_scan=True)]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "schema-verified"
        assert result[0]["plan_verified"] is True
        assert result[0].get("plan_contradicts") is None

    def test_no_alias_in_suggestion_matches_single_table_plan(self):
        """The common case: a simple, non-aliased query — exactly what
        QueryInput.jsx's own EXPLAIN placeholder shows
        (`Seq Scan on orders ...`, no alias)."""
        suggestions = [_suggestion(columns=["status"])]  # no "." — no alias was used in the query
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", rows=10000, is_full_scan=True)]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "schema-verified"

    def test_no_alias_with_multi_table_plan_does_not_guess(self):
        """Without an alias to match by, a multi-table plan is genuinely
        ambiguous — must not silently attribute the suggestion to either
        table."""
        suggestions = [_suggestion(columns=["status"])]
        nodes = [
            PlanNode(node_type="Seq Scan", relation="orders", rows=10000, is_full_scan=True),
            PlanNode(node_type="Seq Scan", relation="customers", rows=500, is_full_scan=True),
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "needs-runtime-evidence"
        assert result[0].get("plan_verified") is None

    def test_schema_resolved_alias_matches_real_table_name(self):
        """Alias in the suggestion doesn't literally appear in the plan,
        but schema DDL resolves it to a real table name the plan does
        reference."""
        suggestions = [_suggestion(columns=["ord.status"])]
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", rows=10000, is_full_scan=True)]
        schema = {"orders": {"status": "text"}}

        result = cross_reference_plan(suggestions, nodes, schema)

        assert result[0]["evidence_level"] == "schema-verified"

    def test_index_access_alone_does_not_confirm(self):
        """An Index Scan is not a full scan — it shouldn't upgrade a
        suggestion just by being present on the same table; only an
        actual full scan (proving the column truly is unindexed) does."""
        suggestions = [_suggestion(columns=["o.status"])]
        nodes = [
            PlanNode(
                node_type="Index Scan",
                relation="orders",
                alias="o",
                condition_column="customer_id",
                is_index_access=True,
            )
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "needs-runtime-evidence"

    def test_composite_suggestion_confirmed_if_any_column_full_scanned(self):
        suggestions = [
            _suggestion(
                type_="index_review_composite_index",
                columns=["o.status", "o.customer_id", "o.created_at"],
            )
        ]
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", alias="o", rows=10000, is_full_scan=True)]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "schema-verified"
        assert result[0]["plan_verified"] is True


class TestContradiction:
    def test_index_scan_on_exact_column_contradicts(self):
        """The core #63 case: heuristic thinks customer_id is unindexed,
        but the real plan proves an index already covers exactly that
        column via its own condition."""
        suggestions = [_suggestion(type_="index_review_where_filter", columns=["o.customer_id"])]
        nodes = [
            PlanNode(
                node_type="Index Scan",
                relation="orders",
                alias="o",
                index_name="idx_orders_customer_id",
                condition_column="customer_id",
                is_index_access=True,
            )
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["plan_contradicts"] is True
        # Contradiction must NOT also silently upgrade evidence — that
        # would be exactly the "false confidence" outcome #63 exists to
        # prevent.
        assert result[0]["evidence_level"] == "needs-runtime-evidence"
        assert result[0].get("plan_verified") is None

    def test_index_scan_on_different_column_does_not_contradict(self):
        """The plan shows SOME index being used on this table, but for a
        different column than the one this suggestion is about — must not
        be treated as evidence against a suggestion it says nothing about."""
        suggestions = [_suggestion(type_="index_review_where_filter", columns=["o.customer_id"])]
        nodes = [
            PlanNode(
                node_type="Index Scan",
                relation="orders",
                alias="o",
                index_name="idx_orders_status",
                condition_column="status",  # a different column
                is_index_access=True,
            )
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0].get("plan_contradicts") is None

    def test_composite_index_suggestion_never_contradicted(self):
        """Explicit v1 scope boundary: contradiction only applies to
        single-column suggestion types. A composite suggestion isn't
        necessarily wrong just because one of its columns already has its
        own index."""
        suggestions = [
            _suggestion(
                type_="index_review_composite_index",
                columns=["o.customer_id", "o.status"],
            )
        ]
        nodes = [
            PlanNode(
                node_type="Index Scan",
                relation="orders",
                alias="o",
                condition_column="customer_id",
                is_index_access=True,
            )
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0].get("plan_contradicts") is None

    def test_condition_column_unknown_does_not_contradict(self):
        """An index-access node whose condition_column couldn't be
        extracted must not be treated as matching anything — an unknown
        column is not evidence of contradiction."""
        suggestions = [_suggestion(type_="index_review_where_filter", columns=["o.customer_id"])]
        nodes = [
            PlanNode(node_type="Index Scan", relation="orders", alias="o", condition_column=None, is_index_access=True)
        ]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0].get("plan_contradicts") is None


class TestNonIndexSuggestionsUntouched:
    def test_non_index_review_type_is_ignored(self):
        suggestions = [
            {
                "type": "column_selection",
                "severity": "medium",
                "suggestion": "Avoid SELECT *",
                "reason": "...",
                "estimated_improvement": "...",
                "evidence_level": "deterministic",
            }
        ]
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", rows=10000, is_full_scan=True)]

        result = cross_reference_plan(suggestions, nodes)

        assert result[0]["evidence_level"] == "deterministic"
        assert "plan_verified" not in result[0]


class TestEmptyInputs:
    def test_no_plan_nodes_returns_suggestions_unchanged(self):
        suggestions = [_suggestion()]
        result = cross_reference_plan(suggestions, [])
        assert result == suggestions

    def test_no_suggestions_returns_empty_list(self):
        nodes = [PlanNode(node_type="Seq Scan", relation="orders", is_full_scan=True)]
        assert cross_reference_plan([], nodes) == []
