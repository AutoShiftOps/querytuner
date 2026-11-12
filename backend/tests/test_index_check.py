"""AI index suggestions are checked against the query and their DDL rebuilt server-side."""

import json

from app.llm.index_check import _structured, check_ai_indexes
from app.llm.rewrite_check import review_ai_output
from app.tools.index_recommender import _filter_predicate
from app.tools.query_parser import QueryParser

QUERY = """SELECT o.id, u.email, COUNT(*) AS n
FROM dbo.Orders o
JOIN dbo.[Order Lines] ol ON ol.order_id = o.id
JOIN users u ON u.id = o.user_id
WHERE o.status = 'open' AND ol.[Document No] > 5
GROUP BY o.id, u.email
ORDER BY n"""


def _check(items, db_type="sqlserver", query=QUERY, schema_info=None):
    return check_ai_indexes(query, items, db_type=db_type, parsed=QueryParser().parse(query), schema_info=schema_info)


def test_ddl_is_built_by_server_not_copied_from_model():
    model_ddl = "CREATE INDEX evil ON dbo.Orders(status); DROP TABLE users; --"
    kept, dropped = _check(
        [{"table": "o", "columns": ["status", "user_id"], "why": "filter then join", "ddl": model_ddl}]
    )
    assert dropped == []
    assert len(kept) == 1
    idx = kept[0]
    assert idx["ddl"] == (
        "CREATE NONCLUSTERED INDEX idx_Orders_status_user_id ON dbo.Orders(status, user_id) "
        "WITH (ONLINE=ON, FILLFACTOR=90);"
    )
    assert "DROP TABLE" not in idx["ddl"]
    assert idx["rollback_ddl"] == "DROP INDEX idx_Orders_status_user_id ON dbo.Orders;"
    assert idx["verified_against"] == "query"
    assert idx["reason"] == "filter then join"


def test_alias_resolves_to_real_table_and_brackets_are_kept():
    kept, _ = _check([{"table": "ol", "columns": ["Document No"]}])
    assert kept[0]["ddl"].startswith(
        "CREATE NONCLUSTERED INDEX idx_Order_Lines_Document_No ON dbo.[Order Lines]([Document No])"
    )


def test_unknown_table_column_cte_and_alias_are_dropped():
    kept, dropped = _check(
        [
            {"table": "payments", "columns": ["order_id"]},
            {"table": "orders", "columns": ["created_at"]},
            {"table": "orders", "columns": ["n"]},
            {"table": "users", "columns": ["LOWER(email)"]},
        ]
    )
    assert kept == []
    assert dropped == [
        "table `payments` is not used in this query",
        "column `created_at` does not appear in this query",
        "`n` is a computed SELECT alias, not a table column",
        "`LOWER(email)` is an expression, not a column (expression indexes are not checked yet)",
    ]


def test_column_on_another_table_is_dropped():
    kept, dropped = _check([{"table": "dbo.Orders", "columns": ["email"]}])
    assert kept == []
    assert dropped == ["column `email` belongs to another table in this query, not `dbo.Orders`"]


def test_cte_is_not_indexable():
    q = "WITH recent AS (SELECT user_id FROM orders WHERE status = 'x') SELECT * FROM recent r WHERE r.user_id = 5"
    kept, dropped = _check([{"table": "recent", "columns": ["user_id"]}], db_type="postgresql", query=q)
    assert kept == []
    assert "CTE or derived table" in dropped[0]


def test_model_ddl_strings_are_parsed_and_rebuilt():
    kept, dropped = _check(
        [
            "CREATE INDEX whatever ON users (email DESC) INCLUDE (id);",
            {"suggestion": "Speed up the join", "ddl_statement": "CREATE INDEX x ON dbo.[Order Lines] (order_id)"},
            "Consider indexing the foreign keys",
        ]
    )
    assert [k["ddl"].split(" WITH")[0] for k in kept] == [
        "CREATE NONCLUSTERED INDEX idx_users_email ON users(email) INCLUDE (id)",
        "CREATE NONCLUSTERED INDEX idx_Order_Lines_order_id ON dbo.[Order Lines](order_id)",
    ]
    assert kept[1]["suggestion"] == "Speed up the join"
    assert dropped == ["it did not name a table and columns"]


def test_include_left_out_where_dialect_has_no_include():
    q = "SELECT o.total FROM orders o WHERE o.user_id = 3"
    kept, _ = _check([{"table": "orders", "columns": ["user_id"], "include": ["total"]}], db_type="mysql", query=q)
    assert kept[0]["ddl"] == "ALTER TABLE orders ADD INDEX idx_orders_user_id (user_id);"
    assert "MySQL has no INCLUDE clause" in kept[0]["reason"]


def test_schema_is_authoritative_when_pasted():
    q = "SELECT * FROM orders WHERE status = 'x'"
    schema = "CREATE TABLE orders (id INT PRIMARY KEY, status VARCHAR(20), user_id INT);"
    kept, dropped = _check(
        [{"table": "orders", "columns": ["status", "user_id"]}, {"table": "orders", "columns": ["state"]}],
        db_type="postgresql",
        query=q,
        schema_info=schema,
    )
    assert [k["columns"] for k in kept] == [["status", "user_id"]]
    assert kept[0]["verified_against"] == "schema"
    assert dropped == ["column `state` is not in your schema for `orders`"]


def test_duplicates_collapse():
    kept, _ = _check([{"table": "o", "columns": ["status"]}, {"table": "dbo.Orders", "columns": ["status"]}])
    assert len(kept) == 1


def test_review_ai_output_rewrites_index_list_and_records_drops():
    reply = json.dumps(
        {
            "recommended_indexes": [
                {"table": "o", "columns": ["status"], "severity": "HIGH"},
                {"table": "ghost", "columns": ["x"]},
            ]
        }
    )
    out = json.loads(review_ai_output(QUERY, reply, db_type="sqlserver", parsed=QueryParser().parse(QUERY)))
    assert [i["columns"] for i in out["recommended_indexes"]] == [["status"]]
    assert out["recommended_indexes"][0]["severity"] == "high"
    assert out["indexes_dropped"] == ["table `ghost` is not used in this query"]


def test_review_ai_output_without_db_type_leaves_indexes_alone():
    reply = json.dumps({"recommended_indexes": ["anything"]})
    assert json.loads(review_ai_output(QUERY, reply))["recommended_indexes"] == ["anything"]


def test_structured_handles_nested_parens():
    assert _structured("CREATE INDEX i ON t (LOWER(a), b)")[1] == ["LOWER(a)", "b"]


# ── Filtered/partial index uses the query's own literal ──────────────────────


def test_filter_predicate_uses_literal():
    assert _filter_predicate("o.status = 'active' AND o.total > 5", "o", "status") == "status = 'active'"
    assert _filter_predicate("Status = 10000", None, "Status") == "Status = 10000"
    assert _filter_predicate("type IN (1, 2) AND x = 3", None, "type") == "type IN (1, 2)"
    assert _filter_predicate("(kind = N'a, b''c')", None, "kind") == "kind = N'a, b''c'"
    assert _filter_predicate("o.deleted_at IS NULL", "o", "deleted_at") == "deleted_at IS NULL"


def test_filter_predicate_refuses_or_parameters_and_other_aliases():
    assert _filter_predicate("status = 'a' OR total > 5", None, "status") is None
    assert _filter_predicate("status = $1", None, "status") is None
    assert _filter_predicate("status = @status", None, "status") is None
    assert _filter_predicate("u.status = 'x'", "o", "status") is None


def test_partial_index_ddl_has_no_placeholder_when_literal_known():
    from app.tools.index_recommender import IndexRecommender

    q = "SELECT * FROM dbo.Orders WHERE Status = 10000"
    recs = IndexRecommender().recommend(q, QueryParser().parse(q), "sqlserver")
    partial = [r for r in recs if r["type"] == "index_review_partial_index_candidate"]
    assert partial and "WHERE Status = 10000" in partial[0]["ddl_hint"]
    assert "<" not in partial[0]["ddl_hint"]
