"""
Tests for backend/app/tools/plan_parsers/mysql.py — Issue #62.

MySQL's EXPLAIN FORMAT=JSON output has a different tree shape than
Postgres (query_block.table.access_type, not Node Type) — this is not a
copy-paste of the Postgres parser, per the design doc. JSON-only: unlike
Postgres, the UI never invites a MySQL plain-text EXPLAIN paste.
"""

import json

from app.tools.plan_parsers.mysql import parse_mysql_explain


class TestMysqlJsonParsing:
    def test_ui_placeholder_example_parses(self):
        """The literal example QueryInput.jsx shows the user."""
        raw = json.dumps(
            {"query_block": {"table": {"table_name": "orders", "access_type": "ALL", "rows_examined_per_scan": 10000}}}
        )
        result = parse_mysql_explain(raw)

        assert result is not None
        assert len(result.nodes) == 1
        node = result.nodes[0]
        assert node.relation == "orders"
        assert node.node_type == "ALL"
        assert node.rows == 10000
        assert node.is_full_scan is True
        assert node.is_index_access is False

    def test_access_type_all_maps_to_full_table_scan_finding(self):
        raw = json.dumps(
            {"query_block": {"table": {"table_name": "orders", "access_type": "ALL", "rows_examined_per_scan": 10000}}}
        )
        result = parse_mysql_explain(raw)
        assert any(f.type == "full_table_scan" for f in result.findings)

    def test_access_type_ref_is_index_access_not_full_scan(self):
        raw = json.dumps(
            {
                "query_block": {
                    "table": {
                        "table_name": "orders",
                        "access_type": "ref",
                        "key": "idx_orders_customer_id",
                        "rows_examined_per_scan": 1,
                    }
                }
            }
        )
        result = parse_mysql_explain(raw)
        node = result.nodes[0]
        assert node.is_full_scan is False
        assert node.is_index_access is True
        assert node.index_name == "idx_orders_customer_id"
        assert any(f.type == "index_scan_confirmed" for f in result.findings)

    def test_nested_loop_join_finds_both_tables(self):
        raw = json.dumps(
            {
                "query_block": {
                    "nested_loop": [
                        {"table": {"table_name": "orders", "access_type": "ALL", "rows_examined_per_scan": 10000}},
                        {
                            "table": {
                                "table_name": "customers",
                                "access_type": "eq_ref",
                                "key": "PRIMARY",
                                "rows_examined_per_scan": 1,
                            }
                        },
                    ]
                }
            }
        )
        result = parse_mysql_explain(raw)
        relations = {n.relation for n in result.nodes}
        assert relations == {"orders", "customers"}

    def test_access_types_other_than_all_are_not_full_scans(self):
        for access_type in ("ref", "eq_ref", "range", "index", "const"):
            raw = json.dumps(
                {"query_block": {"table": {"table_name": "t", "access_type": access_type, "rows_examined_per_scan": 5}}}
            )
            result = parse_mysql_explain(raw)
            assert result.nodes[0].is_full_scan is False, f"access_type={access_type} should not be a full scan"


class TestMysqlGracefulFailure:
    def test_empty_string_returns_none(self):
        assert parse_mysql_explain("") is None

    def test_invalid_json_returns_none(self):
        assert parse_mysql_explain("not json at all") is None

    def test_valid_json_with_no_table_returns_none(self):
        assert parse_mysql_explain(json.dumps({"query_block": {"select_id": 1}})) is None
