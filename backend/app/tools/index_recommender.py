from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Helpers — column name extraction from SQL clauses
# ---------------------------------------------------------------------------


def _extract_col_name(expr: str) -> str | None:
    """
    Given a raw clause expression like 'o.user_id', 'u.status', 'created_at DESC',
    return a clean (table_alias, column) tuple string or just the column name.
    Strips ASC/DESC, function wrappers, comparison operators.
    """
    e = expr.strip()
    # Remove ASC / DESC
    e = re.sub(r"\s+(ASC|DESC)\s*$", "", e, flags=re.IGNORECASE).strip()
    # If wrapped in a function — skip (function_in_where handles those)
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(", e):
        return None
    # Remove comparison operators and everything after
    e = re.split(r"[=<>!]", e)[0].strip()
    # Accept qualified names like table.col or just col
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", e):
        return e
    return None


def _qualified_col(expr: str) -> tuple[str | None, str] | None:
    """
    Returns (table_alias_or_none, column_name) from 'o.user_id' or 'status'.
    """
    col = _extract_col_name(expr)
    if not col:
        return None
    parts = col.split(".")
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


def _extract_where_columns(where_clause: str) -> list[tuple[str | None, str]]:
    """
    Extract all column references from a WHERE clause.
    Skips literals, functions, subqueries.
    """
    if not where_clause:
        return []
    cols: list[tuple[str | None, str]] = []
    # Split on AND / OR at top level (rough, good enough for heuristics)
    conditions = re.split(r"\bAND\b|\bOR\b", where_clause, flags=re.IGNORECASE)
    for cond in conditions:
        cond = cond.strip()
        # Skip IS NULL / IS NOT NULL — these are separate (low-cardinality hint)
        is_null_m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]+)\s+IS\s+(NOT\s+)?NULL$", cond, re.IGNORECASE)
        if is_null_m:
            qc = _qualified_col(is_null_m.group(1))
            if qc:
                cols.append(qc)
            continue
        # Standard: col op value  OR  col BETWEEN x AND y  OR  col LIKE 'x'
        m = re.match(
            r"^([A-Za-z_][A-Za-z0-9_.]+)\s*" r"(?:=|!=|<>|<=|>=|<|>|\bLIKE\b|\bIN\b|\bBETWEEN\b|\bNOT\s+IN\b)",
            cond,
            re.IGNORECASE,
        )
        if m:
            qc = _qualified_col(m.group(1))
            if qc:
                cols.append(qc)
    return cols


def _extract_join_columns(joins_raw: list[dict[str, Any]], query: str) -> list[tuple[str | None, str]]:
    """
    Extract columns used in JOIN ... ON conditions.
    Regex over raw query for ON col = col patterns.
    """
    cols: list[tuple[str | None, str]] = []
    # Match: ON t1.col = t2.col  or  ON col = col
    for m in re.finditer(
        r"\bON\s+([A-Za-z_][A-Za-z0-9_.]+)\s*=\s*([A-Za-z_][A-Za-z0-9_.]+)",
        query,
        re.IGNORECASE,
    ):
        for grp in (m.group(1), m.group(2)):
            qc = _qualified_col(grp)
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


# ---------------------------------------------------------------------------
# Composite index detection
# ---------------------------------------------------------------------------


def _detect_composite_opportunity(
    where_cols: list[tuple[str | None, str]],
    join_cols: list[tuple[str | None, str]],
    order_by_cols: list[tuple[str | None, str]],
) -> list[dict[str, Any]]:
    """
    If the same table alias has 2+ columns across JOIN + WHERE + ORDER BY,
    a composite index likely helps more than individual indexes.
    """
    from collections import defaultdict

    table_cols: dict[str, list[str]] = defaultdict(list)
    for alias, col in where_cols + join_cols + order_by_cols:
        if alias:
            if col not in table_cols[alias]:
                table_cols[alias].append(col)

    composites = []
    for alias, cols in table_cols.items():
        if len(cols) >= 2:
            composites.append(
                {
                    "table_alias": alias,
                    "columns": cols,
                    "suggestion": (
                        f"Consider a composite index on `{alias}` table columns "
                        f"({', '.join(f'`{c}`' for c in cols)}) — "
                        f"all appear in JOIN/WHERE/ORDER BY together"
                    ),
                    "ddl_hint": (
                        f"CREATE INDEX CONCURRENTLY idx_{alias}_{'_'.join(cols)} "
                        f"ON <table_name>({', '.join(cols)});"
                    ),
                }
            )
    return composites


# ---------------------------------------------------------------------------
# Low-cardinality / partial index detection
# ---------------------------------------------------------------------------

_LOW_CARDINALITY_PATTERNS = re.compile(
    r"\b(status|type|flag|is_[a-z_]+|active|enabled|deleted|state|role|" r"gender|priority|category|kind|mode|tier)\b",
    re.IGNORECASE,
)


def _is_low_cardinality(col_name: str) -> bool:
    return bool(_LOW_CARDINALITY_PATTERNS.search(col_name))


# ---------------------------------------------------------------------------
# Main IndexRecommender
# ---------------------------------------------------------------------------


class IndexRecommender:
    """
    Deterministic, heuristic-based index recommendation engine.

    Detects:
    1. JOIN keys without apparent index coverage
    2. WHERE filter columns (equality + range)
    3. ORDER BY columns likely needing index support
    4. GROUP BY columns
    5. Composite index opportunities (same table, multiple columns)
    6. Low-cardinality columns → partial index suggestion
    7. IS NULL columns (often unindexed)

    Output: list of structured finding dicts compatible with sql_analyzer.py
    suggestion format.
    """

    def recommend(
        self,
        query: str,
        parsed: dict[str, Any],
        db_type: str = "postgresql",
    ) -> list[dict[str, Any]]:
        """
        Main entry point. Returns a list of index suggestion dicts.
        Each dict matches the _suggest() shape in SQLAnalyzerAgent.
        """
        suggestions: list[dict[str, Any]] = []

        where_clause = parsed.get("where_clause") or ""
        joins = parsed.get("joins") or []
        order_by = parsed.get("order_by") or []
        group_by = parsed.get("group_by") or []

        where_cols = _extract_where_columns(where_clause)
        join_cols = _extract_join_columns(joins, query)
        order_cols = _extract_order_by_columns(order_by)
        group_cols = _extract_group_by_columns(group_by)

        # ── 1. JOIN key suggestions ──────────────────────────────────────────
        seen_join_cols: set[str] = set()
        for alias, col in join_cols:
            key = f"{alias}.{col}" if alias else col
            if key in seen_join_cols:
                continue
            seen_join_cols.add(key)
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl = self._ddl_hint(alias, col, db_type, index_type="standard")
            suggestions.append(
                self._make(
                    index_type="join_key",
                    severity="high",
                    columns=[key],
                    suggestion=(
                        f"JOIN key {label} may lack an index — "
                        f"each matched row triggers a lookup on the joined table"
                    ),
                    reason=(
                        "Unindexed JOIN keys cause nested-loop full scans. "
                        "An index on the foreign key column is one of the highest-ROI changes."
                    ),
                    estimated="50–90% faster JOINs on large tables",
                    ddl_hint=ddl,
                )
            )

        # ── 2. WHERE filter column suggestions ──────────────────────────────
        seen_where_cols: set[str] = set()
        for alias, col in where_cols:
            key = f"{alias}.{col}" if alias else col
            if key in seen_where_cols or key in seen_join_cols:
                continue
            seen_where_cols.add(key)
            label = f"`{alias}.{col}`" if alias else f"`{col}`"

            if _is_low_cardinality(col):
                # Partial index suggestion
                ddl = self._ddl_partial_hint(alias, col, db_type)
                suggestions.append(
                    self._make(
                        index_type="partial_index_candidate",
                        severity="medium",
                        columns=[key],
                        suggestion=(
                            f"WHERE column {label} looks low-cardinality (status/flag/type). "
                            f"A partial index may be more efficient than a full index"
                        ),
                        reason=(
                            "Low-cardinality columns have poor selectivity for full indexes. "
                            "A partial index (WHERE status = 'active') is smaller and faster."
                        ),
                        estimated="Significant if active rows << total rows",
                        ddl_hint=ddl,
                    )
                )
            else:
                ddl = self._ddl_hint(alias, col, db_type, index_type="standard")
                suggestions.append(
                    self._make(
                        index_type="where_filter",
                        severity="high",
                        columns=[key],
                        suggestion=(f"WHERE column {label} may lack an index — " f"used as a filter condition"),
                        reason=(
                            "Unindexed WHERE columns force full table or full index scans. "
                            "Adding a B-tree index enables seek access."
                        ),
                        estimated="Often large — enables index seek vs full scan",
                        ddl_hint=ddl,
                    )
                )

        # ── 3. ORDER BY column suggestions ──────────────────────────────────
        seen_order_cols: set[str] = set()
        for alias, col in order_cols:
            key = f"{alias}.{col}" if alias else col
            if key in seen_where_cols or key in seen_join_cols or key in seen_order_cols:
                continue
            seen_order_cols.add(key)
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl = self._ddl_hint(alias, col, db_type, index_type="standard")
            suggestions.append(
                self._make(
                    index_type="order_by_index",
                    severity="medium",
                    columns=[key],
                    suggestion=(
                        f"ORDER BY column {label} may benefit from an index — " f"avoids filesort on large result sets"
                    ),
                    reason=(
                        "Without an index matching the ORDER BY, the DB sorts all matching "
                        "rows in memory or on disk before returning results."
                    ),
                    estimated="Eliminates filesort — often 30–70% faster",
                    ddl_hint=ddl,
                )
            )

        # ── 4. GROUP BY column suggestions ──────────────────────────────────
        for alias, col in group_cols:
            key = f"{alias}.{col}" if alias else col
            if key in seen_where_cols or key in seen_join_cols or key in seen_order_cols:
                continue
            label = f"`{alias}.{col}`" if alias else f"`{col}`"
            ddl = self._ddl_hint(alias, col, db_type, index_type="standard")
            suggestions.append(
                self._make(
                    index_type="group_by_index",
                    severity="medium",
                    columns=[key],
                    suggestion=(
                        f"GROUP BY column {label} may benefit from an index — "
                        f"avoids temporary table for aggregation"
                    ),
                    reason=(
                        "An index on GROUP BY columns lets the planner use an index scan "
                        "for grouping instead of a hash aggregate or temp table."
                    ),
                    estimated="15–50% faster GROUP BY on large tables",
                    ddl_hint=ddl,
                )
            )

        # ── 5. Composite index opportunities ────────────────────────────────
        composites = _detect_composite_opportunity(where_cols, join_cols, order_cols)
        for comp in composites:
            alias = comp["table_alias"]
            cols = comp["columns"]
            col_keys = [f"{alias}.{c}" for c in cols]
            suggestions.append(
                self._make(
                    index_type="composite_index",
                    severity="high",
                    columns=col_keys,
                    suggestion=comp["suggestion"],
                    reason=(
                        "A composite index covering multiple query columns is more efficient "
                        "than separate single-column indexes — one index scan satisfies "
                        "JOIN, filter, and sort in a single pass."
                    ),
                    estimated="Often the highest-ROI index change for multi-column queries",
                    ddl_hint=comp["ddl_hint"],
                )
            )

        return self._dedupe(suggestions)

    # ── DDL hint builders ────────────────────────────────────────────────────

    def _ddl_hint(
        self,
        alias: str | None,
        col: str,
        db_type: str,
        index_type: str = "standard",
    ) -> str:
        table_placeholder = f"<{alias}_table>" if alias else "<table_name>"
        idx_name = f"idx_{alias or 'tbl'}_{col}"
        if db_type in ("postgresql",):
            return f"CREATE INDEX CONCURRENTLY {idx_name} ON {table_placeholder}({col});"
        return f"CREATE INDEX {idx_name} ON {table_placeholder}({col});"

    def _ddl_partial_hint(self, alias: str | None, col: str, db_type: str) -> str:
        table_placeholder = f"<{alias}_table>" if alias else "<table_name>"
        idx_name = f"idx_{alias or 'tbl'}_{col}_partial"
        if db_type == "postgresql":
            return (
                f"CREATE INDEX CONCURRENTLY {idx_name} " f"ON {table_placeholder}(id) WHERE {col} = '<active_value>';"
            )
        # MySQL does not support partial indexes natively
        return (
            f"-- MySQL: no native partial indexes. "
            f"Consider a covering index: CREATE INDEX {idx_name} "
            f"ON {table_placeholder}({col}, id);"
        )

    # ── Suggestion builder (matches SQLAnalyzerAgent._suggest shape) ─────────

    def _make(
        self,
        index_type: str,
        severity: str,
        columns: list[str],
        suggestion: str,
        reason: str,
        estimated: str,
        ddl_hint: str,
    ) -> dict[str, Any]:
        return {
            "type": f"index_review_{index_type}",
            "severity": severity,
            "confirmed": False,
            "columns": columns,
            "suggestion": suggestion,
            "reason": reason,
            "estimated_improvement": estimated,
            "ddl_hint": ddl_hint,
        }

    def _dedupe(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for s in suggestions:
            key = s["suggestion"][:80]
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out
