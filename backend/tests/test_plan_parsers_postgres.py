"""
Tests for backend/app/tools/plan_parsers/postgres.py — Issue #61.

Before this, the only Postgres EXPLAIN parsing in this codebase ran
against a live asyncpg connection's already-parsed JSON, never against
request.explain_plan (the raw string a user pastes) — QueryInput.jsx's
"pasting a real EXPLAIN plan upgrades heuristic findings..." promise was
false. This covers both input shapes the UI actually invites (its own
placeholder text): plain-text tabular EXPLAIN output, and
EXPLAIN (FORMAT JSON).
"""

from app.tools.plan_parsers.postgres import parse_postgres_explain


class TestPlainTextParsing:
    def test_ui_placeholder_example_parses(self):
        """The literal example QueryInput.jsx shows the user."""
        raw = "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)\n  Filter: (status = 'pending'::text)"
        result = parse_postgres_explain(raw)

        assert result is not None
        assert result.artifact.format == "text"
        assert len(result.nodes) == 1
        node = result.nodes[0]
        assert node.node_type == "Seq Scan"
        assert node.relation == "orders"
        assert node.rows == 10000
        assert node.cost == 431.0
        assert node.is_full_scan is True
        assert node.condition_column == "status"

    def test_seq_scan_over_1000_rows_produces_finding(self):
        raw = "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)"
        result = parse_postgres_explain(raw)
        assert any(f.type == "seq_scan" for f in result.findings)

    def test_seq_scan_under_1000_rows_no_finding(self):
        raw = "Seq Scan on orders  (cost=0.00..4.00 rows=50 width=244)"
        result = parse_postgres_explain(raw)
        assert not any(f.type == "seq_scan" for f in result.findings)

    def test_nested_hash_join_with_alias_and_index_scan(self):
        raw = """Hash Join  (cost=1.05..431.00 rows=10000 width=244)
  Hash Cond: (o.customer_id = c.id)
  ->  Seq Scan on orders o  (cost=0.00..300.00 rows=10000 width=200)
        Filter: (status = 'pending'::text)
  ->  Hash  (cost=1.00..1.00 rows=5 width=44)
        ->  Index Scan using idx_customers_id on customers c  (cost=0.42..1.00 rows=5 width=44)
              Index Cond: (id = 5)
"""
        result = parse_postgres_explain(raw)
        by_type = {n.node_type: n for n in result.nodes}

        assert by_type["Hash Join"].relation is None
        assert by_type["Seq Scan"].alias == "o"
        assert by_type["Seq Scan"].relation == "orders"
        assert by_type["Seq Scan"].condition_column == "status"
        assert by_type["Index Scan"].alias == "c"
        assert by_type["Index Scan"].relation == "customers"
        assert by_type["Index Scan"].index_name == "idx_customers_id"
        assert by_type["Index Scan"].condition_column == "id"
        assert by_type["Index Scan"].is_index_access is True

        types = [f.type for f in result.findings]
        assert "hash_join" in types
        assert "seq_scan" in types
        assert "index_scan_confirmed" in types

    def test_bitmap_index_scan_on_clause_is_an_index_not_a_table(self):
        """Postgres-specific quirk: "Bitmap Index Scan on X" — X is an
        index name, unlike every other "on X" node type where X is a
        table. Getting this wrong would misattribute an index name as a
        relation and break cross-referencing for this node type."""
        raw = """Bitmap Heap Scan on orders  (cost=4.30..245.00 rows=1000 width=244)
  Recheck Cond: (status = 'pending'::text)
  ->  Bitmap Index Scan on idx_orders_status  (cost=0.00..4.30 rows=1000 width=0)
"""
        result = parse_postgres_explain(raw)
        heap = next(n for n in result.nodes if n.node_type == "Bitmap Heap Scan")
        index = next(n for n in result.nodes if n.node_type == "Bitmap Index Scan")

        assert heap.relation == "orders"
        assert index.relation is None
        assert index.index_name == "idx_orders_status"

    def test_sort_over_1000_rows_produces_finding(self):
        raw = "Sort  (cost=908.00..933.00 rows=10000 width=244)"
        result = parse_postgres_explain(raw)
        assert any(f.type == "sort_high_cost" for f in result.findings)

    def test_nested_loop_over_cost_threshold_produces_finding(self):
        raw = "Nested Loop  (cost=0.42..8544.42 rows=10000 width=488)"
        result = parse_postgres_explain(raw)
        assert any(f.type == "nested_loop" for f in result.findings)


class TestJsonParsing:
    def test_json_array_shape(self):
        import json

        plan = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Alias": "o",
                    "Plan Rows": 10000,
                    "Total Cost": 431.0,
                    "Filter": "(status = 'pending'::text)",
                }
            }
        ]
        result = parse_postgres_explain(json.dumps(plan))

        assert result is not None
        assert result.artifact.format == "json"
        node = result.nodes[0]
        assert node.relation == "orders"
        assert node.alias == "o"
        assert node.condition_column == "status"

    def test_json_with_nested_plans(self):
        import json

        plan = [
            {
                "Plan": {
                    "Node Type": "Hash Join",
                    "Total Cost": 431.0,
                    "Plans": [
                        {"Node Type": "Seq Scan", "Relation Name": "orders", "Plan Rows": 10000, "Total Cost": 300.0},
                        {
                            "Node Type": "Index Scan",
                            "Relation Name": "customers",
                            "Index Name": "idx_customers_id",
                            "Index Cond": "(id = 5)",
                            "Plan Rows": 5,
                            "Total Cost": 1.0,
                        },
                    ],
                }
            }
        ]
        result = parse_postgres_explain(json.dumps(plan))
        assert len(result.nodes) == 3
        index_node = next(n for n in result.nodes if n.node_type == "Index Scan")
        assert index_node.condition_column == "id"


class TestGapFollowupNodeTypes:
    """Gap-followup: Merge Join/Hash Aggregate/Group Aggregate — 3 of the
    10 node types #61's issue lists that shipped with no classification
    or Finding at all."""

    def test_merge_join_produces_finding_and_is_neither_scan_type(self):
        raw = "Merge Join  (cost=1.05..431.00 rows=10000 width=244)"
        result = parse_postgres_explain(raw)
        node = result.nodes[0]
        assert node.node_type == "Merge Join"
        assert node.is_full_scan is False
        assert node.is_index_access is False
        assert any(f.type == "join_or_aggregate_strategy" for f in result.findings)

    def test_hash_aggregate_produces_finding(self):
        raw = "Hash Aggregate  (cost=908.00..933.00 rows=100 width=44)"
        result = parse_postgres_explain(raw)
        assert any(f.type == "join_or_aggregate_strategy" for f in result.findings)

    def test_group_aggregate_produces_finding(self):
        raw = "Group Aggregate  (cost=908.00..933.00 rows=100 width=44)"
        result = parse_postgres_explain(raw)
        assert any(f.type == "join_or_aggregate_strategy" for f in result.findings)


class TestGapFollowupAnalyzeParsing:
    """Gap-followup: EXPLAIN ANALYZE's actual-time/actual-rows data —
    previously silently ignored (no $ anchor), not extracted at all."""

    def test_actual_time_and_rows_parsed_from_text(self):
        raw = (
            "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244) "
            "(actual time=0.008..12.441 rows=9800 loops=1)"
        )
        result = parse_postgres_explain(raw)
        node = result.nodes[0]
        assert node.actual_rows == 9800
        assert node.actual_time_ms == 12.441

    def test_plain_explain_without_analyze_leaves_actuals_none(self):
        raw = "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)"
        result = parse_postgres_explain(raw)
        node = result.nodes[0]
        assert node.actual_rows is None
        assert node.actual_time_ms is None

    def test_actual_time_parsed_from_json(self):
        import json

        plan = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Plan Rows": 10000,
                    "Total Cost": 431.0,
                    "Actual Rows": 9800,
                    "Actual Total Time": 12.441,
                }
            }
        ]
        result = parse_postgres_explain(json.dumps(plan))
        node = result.nodes[0]
        assert node.actual_rows == 9800
        assert node.actual_time_ms == 12.441

    def test_condition_text_carries_raw_filter_not_just_column(self):
        """New in the gap-followup — condition_column alone can't answer
        'is this column wrapped in a function call?' (#63's
        function_in_where cross-referencing need)."""
        raw = (
            "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)\n"
            "  Filter: (lower(status) = 'pending'::text)"
        )
        result = parse_postgres_explain(raw)
        node = result.nodes[0]
        assert node.condition_text == "(lower(status) = 'pending'::text)"


class TestGracefulFailure:
    def test_empty_string_returns_none(self):
        assert parse_postgres_explain("") is None
        assert parse_postgres_explain("   ") is None

    def test_unparseable_garbage_returns_none(self):
        assert parse_postgres_explain("this is not an EXPLAIN plan at all") is None

    def test_none_input_returns_none(self):
        assert parse_postgres_explain(None) is None
