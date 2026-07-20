"""
Tests for parse_schema_ddl / get_indexed_columns (Issue #8), the two
standalone schema-DDL helpers appended to the bottom of query_parser.py.

Every case here was run against the live functions first to establish
ground truth (not guessed), the same way test_comprehensive.py was built.
"""

from app.tools.index_recommender import IndexRecommender
from app.tools.query_parser import QueryParser, get_indexed_columns, parse_schema_ddl

# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════


def test_postgres_schema_columns_and_types():
    ddl = """
        CREATE TABLE public.orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            total NUMERIC(10,2),
            created_at TIMESTAMP DEFAULT NOW(),
            notes TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """
    schema = parse_schema_ddl(ddl)
    assert schema == {
        "orders": {
            "customer_id": "integer",
            "status": "text",
            "total": "numeric",
            "created_at": "timestamp",
            "notes": "text",
        }
    }


def test_postgres_schema_qualified_table_name_strips_schema():
    schema = parse_schema_ddl("CREATE TABLE public.orders (customer_id INTEGER);")
    assert "orders" in schema
    assert "public.orders" not in schema
    assert "public" not in schema


def test_foreign_key_constraint_line_is_not_a_column():
    ddl = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """
    schema = parse_schema_ddl(ddl)
    cols = schema["orders"]
    assert "foreign" not in {c.lower() for c in cols}
    assert set(cols) == {"customer_id"}


def test_check_constraint_line_is_not_a_column():
    ddl = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            status VARCHAR(20),
            CHECK (status IN ('a', 'b'))
        );
    """
    schema = parse_schema_ddl(ddl)
    assert set(schema["orders"]) == {"status"}


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — MySQL
# ═══════════════════════════════════════════════════════════════════════════


def test_mysql_backtick_identifiers_and_key_syntax():
    ddl = """
        CREATE TABLE `orders` (
          `id` INT AUTO_INCREMENT PRIMARY KEY,
          `customer_id` INT NOT NULL,
          `status` VARCHAR(20),
          `email` VARCHAR(255) UNIQUE,
          KEY `idx_customer` (`customer_id`)
        );
    """
    schema = parse_schema_ddl(ddl)
    assert schema == {
        "orders": {
            "customer_id": "integer",
            "status": "text",
            "email": "text",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — Oracle
# ═══════════════════════════════════════════════════════════════════════════


def test_oracle_types_and_named_constraint():
    ddl = """
        CREATE TABLE orders (
            id NUMBER PRIMARY KEY,
            customer_id NUMBER NOT NULL,
            status VARCHAR2(20),
            created_at TIMESTAMP,
            CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """
    schema = parse_schema_ddl(ddl)
    assert schema == {
        "orders": {
            "customer_id": "numeric",
            "status": "text",
            "created_at": "timestamp",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — SQL Server
# ═══════════════════════════════════════════════════════════════════════════


def test_sqlserver_brackets_and_schema_prefix():
    ddl = """
        CREATE TABLE [dbo].[Orders] (
            [Id] INT IDENTITY(1,1) PRIMARY KEY,
            [CustomerId] INT NOT NULL,
            [Status] NVARCHAR(20),
            [CreatedAt] DATETIME2
        );
    """
    schema = parse_schema_ddl(ddl)
    assert "Orders" in schema
    assert schema["Orders"] == {
        "CustomerId": "integer",
        "Status": "text",
        "CreatedAt": "timestamp",
    }


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — quoted identifiers with spaces
# ═══════════════════════════════════════════════════════════════════════════


def test_quoted_identifiers_with_spaces():
    ddl = """
        CREATE TABLE "Order" (
            "Order Id" INTEGER PRIMARY KEY,
            "Total Amount" NUMERIC(10,2),
            "Customer Ref" INTEGER
        );
    """
    schema = parse_schema_ddl(ddl)
    assert "Order" in schema
    # "Order Id" is the PK but is NOT skipped: the skip-list matches exact
    # short PK-style names (id, pk, uuid, rowid, rownum, level), not any
    # column whose name merely contains "id" as a substring.
    assert schema["Order"] == {
        "Order Id": "integer",
        "Total Amount": "numeric",
        "Customer Ref": "integer",
    }


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — primary-key-style name skipping
# ═══════════════════════════════════════════════════════════════════════════


def test_pk_style_column_names_are_skipped():
    ddl = """
        CREATE TABLE widgets (
            id INTEGER,
            pk INTEGER,
            uuid VARCHAR(36),
            rowid INTEGER,
            rownum INTEGER,
            level INTEGER,
            name VARCHAR(50)
        );
    """
    schema = parse_schema_ddl(ddl)
    assert set(schema["widgets"]) == {"name"}


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — multi-table DDL
# ═══════════════════════════════════════════════════════════════════════════


def test_multi_table_ddl_kept_separate():
    ddl = """
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            region VARCHAR(50),
            UNIQUE (region)
        );
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER,
            UNIQUE (customer_id)
        );
    """
    schema = parse_schema_ddl(ddl)
    assert set(schema) == {"customers", "orders"}
    assert schema["customers"] == {"region": "text"}
    assert schema["orders"] == {"customer_id": "integer"}


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — type normalisation spot checks
# ═══════════════════════════════════════════════════════════════════════════


def test_type_normalisation_integer_variants():
    ddl = "CREATE TABLE t (a INT, b INT4, c BIGINT, d SMALLINT);"
    schema = parse_schema_ddl(ddl)["t"]
    assert schema == {"a": "integer", "b": "integer", "c": "integer", "d": "integer"}


def test_type_normalisation_text_variants():
    ddl = "CREATE TABLE t (a VARCHAR(50), b TEXT, c CLOB, d VARCHAR2(50));"
    schema = parse_schema_ddl(ddl)["t"]
    assert schema == {"a": "text", "b": "text", "c": "text", "d": "text"}


def test_type_normalisation_timestamp_variants():
    ddl = "CREATE TABLE t (a TIMESTAMP, b TIMESTAMPTZ, c DATETIME, d DATETIME2);"
    schema = parse_schema_ddl(ddl)["t"]
    assert schema == {"a": "timestamp", "b": "timestamp", "c": "timestamp", "d": "timestamp"}


def test_type_normalisation_numeric_and_boolean():
    ddl = "CREATE TABLE t (a NUMERIC(10,2), b DECIMAL(5,0), c BOOLEAN, d BOOL);"
    schema = parse_schema_ddl(ddl)["t"]
    assert schema == {"a": "numeric", "b": "numeric", "c": "boolean", "d": "boolean"}


# ═══════════════════════════════════════════════════════════════════════════
# parse_schema_ddl — no CREATE TABLE / empty input
# ═══════════════════════════════════════════════════════════════════════════


def test_empty_ddl_returns_empty_schema():
    assert parse_schema_ddl("") == {}
    assert parse_schema_ddl("SELECT * FROM orders;") == {}


def test_if_not_exists_supported():
    ddl = "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer_id INTEGER NOT NULL);"
    assert parse_schema_ddl(ddl) == {"orders": {"customer_id": "integer"}}


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — standalone CREATE INDEX
# ═══════════════════════════════════════════════════════════════════════════


def test_standalone_create_index_detected():
    ddl = """
        CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INTEGER);
        CREATE INDEX idx_orders_customer ON orders (customer_id);
    """
    indexed = get_indexed_columns(ddl)
    assert indexed["orders"] == {"id", "customer_id"}


def test_standalone_create_unique_index_detected():
    ddl = """
        CREATE TABLE customers (id SERIAL PRIMARY KEY, email VARCHAR(255));
        CREATE UNIQUE INDEX idx_customers_email ON customers (email);
    """
    indexed = get_indexed_columns(ddl)
    assert indexed["customers"] == {"id", "email"}


def test_schema_qualified_create_index_resolves_table():
    ddl = """
        CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INTEGER);
        CREATE INDEX idx_o_cust ON public.orders (customer_id);
    """
    indexed = get_indexed_columns(ddl)
    assert "orders" in indexed
    assert "customer_id" in indexed["orders"]


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — PRIMARY KEY (inline + table-level)
# ═══════════════════════════════════════════════════════════════════════════


def test_inline_primary_key_detected():
    ddl = "CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INTEGER);"
    assert get_indexed_columns(ddl)["orders"] == {"id"}


def test_table_level_primary_key_detected():
    ddl = """
        CREATE TABLE orders (
            id INTEGER,
            customer_id INTEGER,
            PRIMARY KEY (id)
        );
    """
    assert get_indexed_columns(ddl)["orders"] == {"id"}


def test_named_constraint_primary_key_detected():
    ddl = """
        CREATE TABLE orders (
            id INTEGER,
            customer_id INTEGER,
            CONSTRAINT pk_orders PRIMARY KEY (id)
        );
    """
    assert get_indexed_columns(ddl)["orders"] == {"id"}


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — UNIQUE (inline + table-level)
# ═══════════════════════════════════════════════════════════════════════════


def test_inline_unique_detected():
    ddl = "CREATE TABLE customers (id SERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE);"
    assert get_indexed_columns(ddl)["customers"] == {"id", "email"}


def test_table_level_unique_detected():
    ddl = """
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            region VARCHAR(50),
            UNIQUE (region)
        );
    """
    assert get_indexed_columns(ddl)["customers"] == {"id", "region"}


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — MySQL bare KEY syntax
# ═══════════════════════════════════════════════════════════════════════════


def test_mysql_bare_key_syntax_detected():
    ddl = """
        CREATE TABLE `orders` (
          `id` INT AUTO_INCREMENT PRIMARY KEY,
          `customer_id` INT NOT NULL,
          KEY `idx_customer` (`customer_id`)
        );
    """
    assert get_indexed_columns(ddl)["orders"] == {"id", "customer_id"}


def test_mysql_bare_index_syntax_detected():
    ddl = """
        CREATE TABLE `orders` (
          `id` INT AUTO_INCREMENT PRIMARY KEY,
          `customer_id` INT NOT NULL,
          INDEX `idx_customer` (`customer_id`)
        );
    """
    assert get_indexed_columns(ddl)["orders"] == {"id", "customer_id"}


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — the whole point: FK columns are NOT auto-indexed
# ═══════════════════════════════════════════════════════════════════════════


def test_foreign_key_alone_is_not_considered_indexed():
    """
    A FOREIGN KEY constraint does not create an index in Postgres/Oracle/SQL
    Server (MySQL is the exception, not modelled here). If get_indexed_columns
    counted FK columns as indexed, index_recommender would wrongly suppress
    join-key suggestions for genuinely unindexed foreign keys.
    """
    ddl = """
        CREATE TABLE orders (
            id NUMBER PRIMARY KEY,
            customer_id NUMBER NOT NULL,
            CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """
    indexed = get_indexed_columns(ddl)
    assert indexed["orders"] == {"id"}
    assert "customer_id" not in indexed["orders"]


def test_plain_column_with_no_constraint_is_not_indexed():
    ddl = "CREATE TABLE orders (id SERIAL PRIMARY KEY, notes TEXT);"
    assert "notes" not in get_indexed_columns(ddl)["orders"]


# ═══════════════════════════════════════════════════════════════════════════
# get_indexed_columns — multi-table DDL
# ═══════════════════════════════════════════════════════════════════════════


def test_multi_table_indexed_columns_kept_separate():
    ddl = """
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            region VARCHAR(50),
            UNIQUE (region)
        );
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER,
            UNIQUE (customer_id)
        );
    """
    indexed = get_indexed_columns(ddl)
    assert indexed["customers"] == {"id", "region"}
    assert indexed["orders"] == {"id", "customer_id"}


def test_empty_ddl_returns_empty_indexed_columns():
    assert get_indexed_columns("") == {}


# ═══════════════════════════════════════════════════════════════════════════
# IndexRecommender.recommend(schema_info=...) — schema-aware confirmation
# (Issue #8 phase 2: wiring parse_schema_ddl / get_indexed_columns into
# IndexRecommender so suggestions can be confirmed or suppressed against a
# real schema instead of always guessing from the query text alone.)
# ═══════════════════════════════════════════════════════════════════════════

_ORDERS_DDL = """
    CREATE TABLE orders (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        status VARCHAR(20),
        notes TEXT
    );
    CREATE INDEX idx_orders_customer ON orders (customer_id);
"""


def _recommend(query, db_type="postgresql", schema_info=None):
    parsed = QueryParser().parse(query)
    return IndexRecommender().recommend(query=query, parsed=parsed, db_type=db_type, schema_info=schema_info)


def _by_type(suggestions, type_):
    return [s for s in suggestions if s["type"] == type_]


def test_confirmed_true_when_table_and_column_in_schema():
    # 'status' is a real, unindexed column on 'orders' per _ORDERS_DDL
    suggestions = _recommend("SELECT * FROM orders o WHERE o.status = 'active'", schema_info=_ORDERS_DDL)
    partials = _by_type(suggestions, "index_review_partial_index_candidate")
    assert partials, "expected a partial_index_candidate suggestion for o.status"
    assert partials[0]["confirmed"] is True


def test_confirmed_false_when_schema_not_provided():
    suggestions = _recommend("SELECT * FROM orders o WHERE o.status = 'active'")
    partials = _by_type(suggestions, "index_review_partial_index_candidate")
    assert partials, "expected a partial_index_candidate suggestion for o.status"
    assert partials[0]["confirmed"] is False


def test_ddl_hint_uses_real_table_name_when_confirmed():
    suggestions = _recommend("SELECT * FROM orders o WHERE o.status = 'active'", schema_info=_ORDERS_DDL)
    partials = _by_type(suggestions, "index_review_partial_index_candidate")
    assert partials[0]["confirmed"] is True
    ddl = partials[0]["ddl_hint"]
    assert "orders" in ddl
    assert "<o_table>" not in ddl
    assert "<table_name>" not in ddl


def test_ddl_hint_falls_back_to_placeholder_when_not_confirmed():
    suggestions = _recommend("SELECT * FROM orders o WHERE o.status = 'active'")
    partials = _by_type(suggestions, "index_review_partial_index_candidate")
    assert "<o_table>" in partials[0]["ddl_hint"]


def test_suggestion_suppressed_when_index_already_exists_in_schema():
    # customer_id already has CREATE INDEX idx_orders_customer in _ORDERS_DDL
    query = "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id"
    suggestions = _recommend(query, schema_info=_ORDERS_DDL)
    join_keys = _by_type(suggestions, "index_review_join_key")
    assert not any(
        "o.customer_id" in s["columns"] for s in join_keys
    ), "customer_id is already indexed per the schema DDL — it must not be re-suggested"


def test_unindexed_join_key_still_suggested_with_schema_present():
    # Same query, but referencing a column the schema DDL does NOT index —
    # schema-awareness must suppress only what's genuinely covered, not everything.
    ddl = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL
        );
    """
    query = "SELECT * FROM orders o JOIN warehouses w ON o.warehouse_id = w.id"
    suggestions = _recommend(query, schema_info=ddl)
    join_keys = _by_type(suggestions, "index_review_join_key")
    assert any("o.warehouse_id" in s["columns"] for s in join_keys)
    assert join_keys[0]["confirmed"] is True


def test_alias_resolves_to_real_table_name():
    rec = IndexRecommender()
    schema = {"orders": {"customer_id": "integer"}, "customers": {"id": "integer"}}
    assert rec._real_table("o", schema) == "orders"
    assert rec._real_table("c", schema) == "customers"
    assert rec._real_table("zzz", schema) is None


def test_alias_exact_match_resolves_when_alias_is_the_table_name():
    rec = IndexRecommender()
    schema = {"orders": {}}
    assert rec._real_table("orders", schema) == "orders"


def test_no_schema_provided_never_confirms():
    rec = IndexRecommender()
    assert rec._real_table("o", {}) is None
