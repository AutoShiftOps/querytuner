from __future__ import annotations

import re
from typing import Any

# Issue #8: schema-aware confirmation — cross-reference recommendations against
# a real CREATE TABLE/CREATE INDEX DDL instead of guessing from the query alone.
from app.tools.query_parser import get_indexed_columns, parse_schema_ddl

# Issue #72: dialect-aware index DDL
from app.utils.dialect_config import get_dialect, get_index_ddl

_PRIMARY_KEY_NAMES = frozenset({"id", "pk", "oid", "rowid", "uuid", "rownum", "level", "sysdate", "systimestamp"})


def _is_primary_key(col: str) -> bool:
    return col.lower() in _PRIMARY_KEY_NAMES


def _extract_col_name(expr: str) -> str | None:
    e = expr.strip()
    e = re.sub(r"\s+(ASC|DESC)\s*$", "", e, flags=re.IGNORECASE).strip()

    # Quoted identifier, optionally alias-qualified: "Col Name" or alias."Col Name"
    quoted_m = re.match(r'^(?:[A-Za-z_][A-Za-z0-9_]*\.)?"([^"]+)"', e)
    if quoted_m:
        return quoted_m.group(1)

    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(", e):
        return None
    e = re.split(r"[=<>!]", e)[0].strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", e):
        return e
    return None


def _qualified_col(expr: str) -> tuple[str | None, str] | None:
    col = _extract_col_name(expr)
    if not col:
        return None
    parts = col.split(".")
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


def _extract_where_columns(where_clause: str) -> list[tuple[str | None, str]]:
    if not where_clause:
        return []
    cols: list[tuple[str | None, str]] = []
    normalised = re.sub(r"\s+", " ", where_clause).strip()
    conditions = re.split(r"\bAND\b|\bOR\b", normalised, flags=re.IGNORECASE)
    for cond in conditions:
        cond = cond.strip()
        if not cond:
            continue
        is_null_m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]+)\s+IS\s+(NOT\s+)?NULL$", cond, re.IGNORECASE)
        if is_null_m:
            qc = _qualified_col(is_null_m.group(1))
            if qc:
                cols.append(qc)
            continue
        m = re.match(
            r'^([A-Za-z_][A-Za-z0-9_.]+|"[^"]+")\s*'
            r"(?:=|!=|<>|<=|>=|<|>|\bI?LIKE\b|\bIN\b|\bBETWEEN\b|\bNOT\s+IN\b)",
            cond,
            re.IGNORECASE,
        )
        if m:
            qc = _qualified_col(m.group(1))
            if qc:
                cols.append(qc)
    return cols


_ON_CLAUSE_END = r"(?:\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|;|$)"


def _extract_join_columns(joins_raw: list[dict[str, Any]], query: str) -> list[tuple[str | None, str]]:
    cols: list[tuple[str | None, str]] = []

    # ON clause — loop over every AND-joined col=col pair, not just the first
    for on_m in re.finditer(r"\bON\s+(.*?)(?=" + _ON_CLAUSE_END + r")", query, re.IGNORECASE | re.DOTALL):
        for cond in re.split(r"\bAND\b", on_m.group(1), flags=re.IGNORECASE):
            cond_m = re.match(
                r"^\s*([A-Za-z_][A-Za-z0-9_.]+)\s*=\s*([A-Za-z_][A-Za-z0-9_.]+)\s*$",
                cond.strip(),
            )
            if cond_m:
                for grp in (cond_m.group(1), cond_m.group(2)):
                    qc = _qualified_col(grp)
                    if qc:
                        cols.append(qc)

    # USING (col[, col...]) — shared column name, no left/right alias
    for using_m in re.finditer(r"\bUSING\s*\(\s*([^)]+?)\s*\)", query, re.IGNORECASE):
        for col_expr in using_m.group(1).split(","):
            qc = _qualified_col(col_expr.strip())
            if qc:
                cols.append(qc)

    return cols


def _extract_order_by_columns(order_by: list[str]) -> list[tuple[str | None, str]]:
    cols: list[tuple[str | None, str]] = []
    for expr in order_by:
        qc = _qualified_col(expr)
        if qc:
            cols.append(qc)
    return cols


def _extract_group_by_columns(group_by: list[str]) -> list[tuple[str | None, str]]:
    cols: list[tuple[str | None, str]] = []
    for expr in group_by:
        qc = _qualified_col(expr)
        if qc:
            cols.append(qc)
    return cols


def _resolve_real_table(alias: str | None, schema: dict[str, dict[str, str]]) -> str | None:
    """
    Best-effort alias -> real table name resolution against a parsed schema.

    Resolution order:
      a. Exact match: alias in schema
      b. Prefix match: any table name starts with alias
      c. First-letter match: alias == table_name[0]
    """
    if not alias or not schema:
        return None
    if alias in schema:
        return alias
    for table_name in schema:
        if table_name.startswith(alias):
            return table_name
    for table_name in schema:
        if table_name and alias == table_name[0]:
            return table_name
    return None


def _detect_composite_opportunity(
    where_cols: list[tuple[str | None, str]],
    join_cols: list[tuple[str | None, str]],
    order_by_cols: list[tuple[str | None, str]],
    db_type: str = "postgresql",  # Issue #72: added db_type param
    schema: dict[str, dict[str, str]] | None = None,  # Issue #8: schema-aware table resolution
) -> list[dict[str, Any]]:
    from collections import defaultdict

    schema = schema or {}
    table_cols: dict[str, list[str]] = defaultdict(list)
    for alias, col in where_cols + join_cols + order_by_cols:
        if alias and not _is_primary_key(col):
            if col not in table_cols[alias]:
                table_cols[alias].append(col)

    composites = []
    for alias, cols in table_cols.items():
        if len(cols) >= 2:
            # Issue #72: use dialect-correct DDL for composite index
            # Issue #8: prefer the real table name over the alias placeholder when known
            real_table = _resolve_real_table(alias, schema)
            idx_name = f"idx_{real_table or alias}_{'_'.join(cols)}"
            table_ph = real_table if real_table else f"<{alias}_table>"
            col_list = ", ".join(cols)
            ddl = get_index_ddl(db_type, table_ph, col_list, idx_name)
            note = get_dialect(db_type).index_ddl_note()

            composites.append(
                {
                    "table_alias": alias,
                    "columns": cols,
                    "suggestion": (
                        f"Consider a composite index on `{alias}` table columns "
                        f"({', '.join(f'`{c}`' for c in cols)}) — "
                        f"all appear in JOIN/WHERE/ORDER BY together"
                    ),
                    "ddl_hint": ddl,
                    "ddl_note": note,
                }
            )
    return composites


_LOW_CARDINALITY_PATTERNS = re.compile(
    r"\b(status|type|flag|is_[a-z_]+|active|enabled|deleted|state|role|" r"gender|priority|category|kind|mode|tier)\b",
    re.IGNORECASE,
)


def _is_low_cardinality(col_name: str) -> bool:
    return bool(_LOW_CARDINALITY_PATTERNS.search(col_name))


class IndexRecommender:
    def recommend(
        self,
        query: str,
        parsed: dict[str, Any],
        db_type: str = "postgresql",
        schema_info: str | None = None,
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []

        # Issue #8: parse schema DDL (if provided) to confirm/suppress recommendations
        schema = parse_schema_ddl(schema_info) if schema_info else {}
        already_indexed = get_indexed_columns(schema_info) if schema_info else {}

        where_clause = parsed.get("where_clause") or ""
        joins = parsed.get("joins") or []
        order_by = parsed.get("order_by") or []
        group_by = parsed.get("group_by") or []

        where_cols = _extract_where_columns(where_clause)
        join_cols = _extract_join_columns(joins, query)
        order_cols = _extract_order_by_columns(order_by)
        group_cols = _extract_group_by_columns(group_by)

        seen_join_cols: set[str] = set()
        for alias, col in join_cols:
            if _is_primary_key(col):
                continue
            key = f"{alias}.{col}" if alias else col
            if key in seen_join_cols:
                continue
            seen_join_cols.add(key)
            real = self._real_table(alias, schema)
            if real and col in already_indexed.get(real, set()):
                continue
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl, confirmed_flag = self._ddl_hint(alias, col, db_type, schema)
            suggestions.append(
                self._make(
                    index_type="join_key",
                    severity="high",
                    columns=[key],
                    suggestion=f"JOIN key {label} may lack an index — each matched row triggers a lookup on the joined table",
                    reason="Unindexed JOIN keys cause nested-loop full scans. An index on the foreign key column is one of the highest-ROI changes.",
                    estimated="50-90% faster JOINs on large tables",
                    ddl_hint=ddl,
                    ddl_note=get_dialect(db_type).index_ddl_note(),
                    confirmed=confirmed_flag,
                )
            )

        seen_where_cols: set[str] = set()
        for alias, col in where_cols:
            if _is_primary_key(col):
                continue
            key = f"{alias}.{col}" if alias else col
            if key in seen_join_cols or key in seen_where_cols:
                continue
            seen_where_cols.add(key)
            real = self._real_table(alias, schema)
            if real and col in already_indexed.get(real, set()):
                continue
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            if _is_low_cardinality(col):
                ddl, confirmed_flag = self._ddl_partial_hint(alias, col, db_type, schema)
                suggestions.append(
                    self._make(
                        index_type="partial_index_candidate",
                        severity="medium",
                        columns=[key],
                        suggestion=f"WHERE column {label} looks low-cardinality (status/flag/type). A partial index may be more efficient than a full index",
                        reason="Low-cardinality columns have poor selectivity for full indexes. A partial index (WHERE status = 'active') is smaller and faster.",
                        estimated="Significant if active rows are a small subset of the table",
                        ddl_hint=ddl,
                        ddl_note=get_dialect(db_type).index_ddl_note(),
                        confirmed=confirmed_flag,
                    )
                )
            else:
                ddl, confirmed_flag = self._ddl_hint(alias, col, db_type, schema)
                suggestions.append(
                    self._make(
                        index_type="where_filter",
                        severity="high",
                        columns=[key],
                        suggestion=f"WHERE column {label} may lack an index — used as a filter condition",
                        reason="Unindexed WHERE columns force full table or full index scans. Adding a B-tree index enables seek access.",
                        estimated="Often large — enables index seek vs full scan",
                        ddl_hint=ddl,
                        ddl_note=get_dialect(db_type).index_ddl_note(),
                        confirmed=confirmed_flag,
                    )
                )

        seen_order_cols: set[str] = set()
        for alias, col in order_cols:
            if _is_primary_key(col):
                continue
            key = f"{alias}.{col}" if alias else col
            if key in seen_join_cols or key in seen_where_cols or key in seen_order_cols:
                continue
            seen_order_cols.add(key)
            real = self._real_table(alias, schema)
            if real and col in already_indexed.get(real, set()):
                continue
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl, confirmed_flag = self._ddl_hint(alias, col, db_type, schema)
            suggestions.append(
                self._make(
                    index_type="order_by_index",
                    severity="medium",
                    columns=[key],
                    suggestion=f"ORDER BY column {label} may benefit from an index — avoids filesort on large result sets",
                    reason="Without an index matching the ORDER BY, the DB sorts all matching rows in memory or on disk before returning results.",
                    estimated="Eliminates filesort — often 30-70% faster",
                    ddl_hint=ddl,
                    ddl_note=get_dialect(db_type).index_ddl_note(),
                    confirmed=confirmed_flag,
                )
            )

        for alias, col in group_cols:
            if _is_primary_key(col):
                continue
            key = f"{alias}.{col}" if alias else col
            if key in seen_join_cols or key in seen_where_cols or key in seen_order_cols:
                continue
            real = self._real_table(alias, schema)
            if real and col in already_indexed.get(real, set()):
                continue
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl, confirmed_flag = self._ddl_hint(alias, col, db_type, schema)
            suggestions.append(
                self._make(
                    index_type="group_by_index",
                    severity="medium",
                    columns=[key],
                    suggestion=f"GROUP BY column {label} may benefit from an index — avoids temporary table for aggregation",
                    reason="An index on GROUP BY columns lets the planner use index scan for grouping instead of a hash aggregate or temp table.",
                    estimated="15-50% faster GROUP BY on large tables",
                    ddl_hint=ddl,
                    ddl_note=get_dialect(db_type).index_ddl_note(),
                    confirmed=confirmed_flag,
                )
            )

        # Issue #72: pass db_type to composite detector; Issue #8: pass schema too
        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols, db_type, schema)
        for comp in composites:
            alias = comp["table_alias"]
            cols = comp["columns"]
            suggestions.append(
                self._make(
                    index_type="composite_index",
                    severity="high",
                    columns=[f"{alias}.{c}" for c in cols],
                    suggestion=comp["suggestion"],
                    reason="A composite index covering multiple query columns is more efficient than separate single-column indexes — one index scan satisfies JOIN, filter, and sort in a single pass.",
                    estimated="Often the highest-ROI index change for multi-column queries",
                    ddl_hint=comp["ddl_hint"],
                    ddl_note=comp.get("ddl_note", ""),
                )
            )

        return self._dedupe(suggestions)

    # Issue #8: alias -> real table name resolution against a parsed schema
    def _real_table(self, alias: str | None, schema: dict[str, dict[str, str]]) -> str | None:
        return _resolve_real_table(alias, schema)

    # Issue #72: replaced hardcoded DDL with dialect_config lookup
    # Issue #8: schema-aware — returns (ddl, confirmed) instead of just ddl
    def _ddl_hint(self, alias: str | None, col: str, db_type: str, schema=None) -> tuple[str, bool]:
        schema = schema or {}
        real_table = self._real_table(alias, schema)
        confirmed = real_table is not None and col in schema.get(real_table, {})
        table_ph = real_table if real_table else (f"<{alias}_table>" if alias else "<table_name>")
        idx_name = f"idx_{real_table or alias or 'tbl'}_{col}"
        ddl = get_index_ddl(db_type, table_ph, col, idx_name)
        return ddl, confirmed

    def _ddl_partial_hint(self, alias: str | None, col: str, db_type: str, schema=None) -> tuple[str, bool]:
        """Dialect-correct partial/filtered index DDL. Returns (ddl, confirmed)."""
        schema = schema or {}
        real_table = self._real_table(alias, schema)
        confirmed = real_table is not None and col in schema.get(real_table, {})
        table_ph = real_table if real_table else (f"<{alias}_table>" if alias else "<table_name>")
        idx = f"idx_{real_table or alias or 'tbl'}_{col}_partial"
        cfg = get_dialect(db_type)

        if db_type == "postgresql":
            ddl = (
                f"CREATE INDEX CONCURRENTLY {idx} ON {table_ph}(id) "
                f"WHERE {col} = '<active_value>';  -- {cfg.index_ddl_note()}"
            )
        elif db_type == "mysql":
            ddl = (
                f"-- MySQL has no native partial indexes.\n"
                f"-- Option A: ALTER TABLE {table_ph} ADD INDEX {idx} ({col}, id);\n"
                f"-- Option B: partition the table by {col} value."
            )
        elif db_type == "sqlserver":
            ddl = (
                f"CREATE NONCLUSTERED INDEX {idx} ON {table_ph}(id) "
                f"WHERE {col} = '<active_value>' WITH (ONLINE=ON);"
            )
        elif db_type == "oracle":
            ddl = (
                f"-- Oracle: use a function-based index or partition:\n"
                f"CREATE INDEX {idx} ON {table_ph}(id) NOLOGGING;\n"
                f"-- Or: use list partitioning on {col}."
            )
        else:
            # SQLite and fallback
            ddl = f"CREATE INDEX IF NOT EXISTS {idx} ON {table_ph}({col});"

        return ddl, confirmed

    def _make(
        self,
        index_type,
        severity,
        columns,
        suggestion,
        reason,
        estimated,
        ddl_hint,
        ddl_note: str = "",
        confirmed: bool = False,
    ):
        result = {
            "type": f"index_review_{index_type}",
            "severity": severity,
            "confirmed": confirmed,
            "columns": columns,
            "suggestion": suggestion,
            "reason": reason,
            "estimated_improvement": estimated,
            "ddl_hint": ddl_hint,
        }
        if ddl_note:
            result["ddl_note"] = ddl_note
        return result

    def _dedupe(self, suggestions):
        seen: set[str] = set()
        out = []
        for s in suggestions:
            key = s["suggestion"][:80]
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out
