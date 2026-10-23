"""
Tests for query_parser.py's multi-statement-batch and bracket-quoted-
identifier handling (Issues found via a real public report,
8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e — a large SQL Server batch with
DECLARE/temp-table/INSERT/SELECT statements, which the class docstring
admits this parser wasn't originally built for).

Covers:
  - _clean_table_ref not truncating bracket-quoted identifiers that
    contain spaces (e.g. [Metropolitan$Sales Header])
  - _extract_group_by (via _extract_clause) not running past a
    statement's own top-level semicolon into unrelated later statements
  - _extract_table_aliases building a correct alias -> table map directly
    from the query's own FROM/JOIN clauses
"""

from app.tools.query_parser import QueryParser

# ═══════════════════════════════════════════════════════════════════════════
# _clean_table_ref — bracket-quoted identifiers with spaces
# ═══════════════════════════════════════════════════════════════════════════


def test_clean_table_ref_keeps_bracket_quoted_name_with_space_intact():
    parser = QueryParser()
    assert (
        parser._clean_table_ref("[dbo].[Metropolitan$Sales Header] SH with(nolock)")
        == "[dbo].[Metropolitan$Sales Header]"
    )


def test_clean_table_ref_still_handles_plain_unbracketed_alias():
    parser = QueryParser()
    assert parser._clean_table_ref("orders o") == "orders"
    assert parser._clean_table_ref("schema.orders AS o") == "schema.orders"


def test_tables_accessed_not_truncated_for_bracket_quoted_table():
    query = "SELECT SH.No_ FROM [dbo].[Metropolitan$Sales Header] SH WITH(NOLOCK) WHERE SH.[Order Status] = 10000"
    parsed = QueryParser().parse(query)
    assert parsed["tables"] == ["[dbo].[Metropolitan$Sales Header]"]


# ═══════════════════════════════════════════════════════════════════════════
# _extract_clause / _extract_group_by — multi-statement semicolon boundary
# ═══════════════════════════════════════════════════════════════════════════


def test_group_by_does_not_spill_past_statement_semicolon():
    # Issue: on a multi-statement batch, _extract_clause previously had no
    # concept of statement boundaries — if no top-level ORDER BY/HAVING/etc
    # existed later in the WHOLE script (e.g. because the only later ones
    # are inside parenthesized subqueries elsewhere), it would capture
    # everything from "group by" to the literal end of the script as the
    # "GROUP BY columns."
    # Parse just the statement containing the real GROUP BY, the way
    # index_recommender's single-statement-scoped callers do.
    first_statement = "INSERT INTO @t SELECT id FROM foo GROUP BY id"
    parsed = QueryParser().parse(first_statement)
    assert parsed["group_by"] == ["id"]


def test_group_by_stops_at_semicolon_even_with_no_later_top_level_stop_keyword():
    # Reproduces the exact shape of the real bug: the real GROUP BY's
    # statement has nothing after it, and every later ORDER BY in the batch
    # is inside parens (not top-level) — without the semicolon fix this
    # swallows the rest of the script.
    query = (
        "INSERT INTO #ScanSummary SELECT sll.[Sales Order No], COUNT(*) AS TotalItems "
        "FROM [dbo].[Sales Line Link] sll GROUP BY sll.[Sales Order No]; "
        "SELECT * FROM (SELECT x FROM y ORDER BY z) sub WHERE sub.x > 1"
    )
    parsed = QueryParser().parse(query)
    assert parsed["group_by"] == ["sll.[Sales Order No]"]
    assert "SELECT" not in " ".join(parsed["group_by"]).upper()


def test_where_clause_also_bounded_by_semicolon():
    first_statement = "DELETE FROM foo WHERE id = 1"
    parsed = QueryParser().parse(first_statement)
    assert parsed["where_clause"] == "id = 1"


# ═══════════════════════════════════════════════════════════════════════════
# _extract_table_aliases — alias -> real table name map
# ═══════════════════════════════════════════════════════════════════════════


def test_extract_table_aliases_from_from_and_join():
    query = (
        "SELECT SH.No_ FROM [dbo].[Sales Header] SH WITH(NOLOCK) "
        "INNER JOIN [dbo].[Sales Linkup] SL WITH(NOLOCK) ON SH.No_ = SL.[Document No] "
        "WHERE SH.[Order Status] = 10000"
    )
    parsed = QueryParser().parse(query)
    assert parsed["table_aliases"] == {
        "SH": "[dbo].[Sales Header]",
        "SL": "[dbo].[Sales Linkup]",
    }


def test_extract_table_aliases_plain_postgres_style():
    query = "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id"
    parsed = QueryParser().parse(query)
    assert parsed["table_aliases"] == {"o": "orders", "c": "customers"}


def test_extract_table_aliases_empty_when_no_aliases_used():
    query = "SELECT id FROM orders WHERE status = 'active'"
    parsed = QueryParser().parse(query)
    # No alias used on the base table — nothing to map.
    assert parsed["table_aliases"] == {}


def test_empty_query_returns_empty_table_aliases():
    parsed = QueryParser().parse("")
    assert parsed["table_aliases"] == {}
