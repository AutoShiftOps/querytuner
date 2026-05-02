from __future__ import annotations

import re
from typing import Any

import sqlparse

# -----------------------------
# Top-level scanning helpers
# -----------------------------


def _strip_trailing_semicolon(s: str) -> str:
    return (s or "").strip().rstrip(";").strip()


def _split_top_level_commas(s: str) -> list[str]:
    """
    Split by commas only when not inside parentheses or quotes.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_sq = False  # '
    in_dq = False  # "

    for ch in s:
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif not in_sq and not in_dq:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                continue
        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_alias(expr: str) -> tuple[str, str | None]:
    """
    Returns: (expression_without_alias, alias_or_none)

    Handles:
      - expr AS alias
      - expr alias   (best-effort)
    """
    e = _strip_trailing_semicolon(expr)

    # Prefer: AS alias
    m = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*$", e, flags=re.IGNORECASE)
    if m:
        alias = m.group(1).strip().strip('"')
        expr_wo = e[: m.start()].strip()
        return expr_wo, alias

    # Best-effort: trailing alias without AS
    m2 = re.search(r"\s+([A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*$", e)
    if m2:
        alias = m2.group(1).strip().strip('"')
        if alias.lower() not in {
            "from",
            "where",
            "group",
            "order",
            "limit",
            "over",
            "join",
        }:
            expr_wo = e[: m2.start()].strip()
            # Accept only if it looks like an expression (reduces false positives)
            if expr_wo and (
                ("(" in expr_wo)
                or (" " in expr_wo)
                or ("+" in expr_wo)
                or ("-" in expr_wo)
                or ("/" in expr_wo)
                or ("*" in expr_wo)
            ):
                return expr_wo, alias

    return e, None


def _find_top_level_keyword_pos(sql: str, keyword: str, start_idx: int = 0) -> int:
    """
    Find the first top-level occurrence of `keyword` (case-insensitive),
    where top-level means paren depth == 0 and not inside quotes.

    keyword should be provided in lowercase, e.g. " from " or " order by ".
    """
    s = sql
    sl = sql.lower()
    key = keyword.lower()

    depth = 0
    in_sq = False
    in_dq = False

    i = start_idx
    while i < len(s):
        ch = s[i]

        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif not in_sq and not in_dq:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0:
                if sl.startswith(key, i):
                    return i

        i += 1

    return -1


def _extract_clause(sql: str, start_kw: str, end_kws: list[str]) -> str:
    """
    Extract clause body appearing after start_kw up to the earliest of end_kws, all at top-level.
    Example: start_kw=" where ", end_kws=[" group by ", " order by ", " limit ", " fetch "]
    """
    start = _find_top_level_keyword_pos(sql, start_kw, 0)
    if start == -1:
        return ""

    body_start = start + len(start_kw)
    end_positions = []
    for ek in end_kws:
        p = _find_top_level_keyword_pos(sql, ek, body_start)
        if p != -1:
            end_positions.append(p)

    body_end = min(end_positions) if end_positions else len(sql)
    return _strip_trailing_semicolon(sql[body_start:body_end].strip())


# -----------------------------
# QueryParser
# -----------------------------


class QueryParser:
    """
    JSON-safe SQL parser for common single-statement SELECT queries.

    Goals:
    - Never return sqlparse token objects (only JSON-serializable types)
    - Avoid false matches for ORDER BY / GROUP BY inside window functions (OVER ...)
    - Provide both:
        - columns: list[str] of output names
        - select_items: list[{"output","expr","has_alias"}]
    """

    def parse(self, query: str) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return self._empty()

        stmt = sqlparse.parse(q)[0]  # used only to detect query type safely

        select_items = self._extract_select_items(q)
        columns = [it["output"] for it in select_items if it.get("output")]

        parsed = {
            "query_type": self._get_query_type(stmt),
            "tables": self._extract_tables(q),
            "columns": self._dedupe_keep_order(columns),
            "select_items": select_items,
            "joins": self._extract_joins(q),
            "where_clause": self._extract_where(q),
            "group_by": self._extract_group_by(q),
            "having_clause": self._extract_having(q),
            "order_by": self._extract_order_by(q),
            "subqueries": self._count_subqueries(q),
            "complexity_score": self._complexity_score(q),
        }
        return parsed

    def _empty(self) -> dict[str, Any]:
        return {
            "query_type": "UNKNOWN",
            "tables": [],
            "columns": [],
            "select_items": [],
            "joins": [],
            "where_clause": "",
            "group_by": [],
            "having_clause": "",
            "order_by": [],
            "subqueries": 0,
            "complexity_score": 0.0,
        }

    def _get_query_type(self, stmt) -> str:
        tok = stmt.token_first(skip_ws=True, skip_cm=True)
        if not tok:
            return "UNKNOWN"
        val = getattr(tok, "normalized", None) or getattr(tok, "value", None) or "UNKNOWN"
        return str(val).upper()

    # -----------------------------
    # SELECT items (top-level)
    # -----------------------------

    def _extract_select_items(self, query: str) -> list[dict[str, Any]]:
        select_text = self._extract_select_clause_text(query)
        if not select_text:
            return []

        raw_items = _split_top_level_commas(select_text)
        items: list[dict[str, Any]] = []

        for raw in raw_items:
            expr_wo_alias, alias = _parse_alias(raw)
            output = alias if alias else self._best_output_name(expr_wo_alias)
            items.append(
                {
                    "output": output,
                    "expr": expr_wo_alias.strip(),
                    "has_alias": bool(alias),
                }
            )

        # de-dupe by (output, expr)
        seen = set()
        out = []
        for it in items:
            key = (it["output"], it["expr"])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    def _extract_select_clause_text(self, query: str) -> str:
        q = _strip_trailing_semicolon(query)

        s_idx = _find_top_level_keyword_pos(q, "select", 0)
        if s_idx == -1:
            return ""

        # Find FROM at top level after SELECT
        from_idx = _find_top_level_keyword_pos(q, " from ", s_idx)
        if from_idx == -1:
            # SELECT without FROM; return everything after SELECT
            return q[s_idx + len("select") :].strip()

        return q[s_idx + len("select") : from_idx].strip()

    def _best_output_name(self, expr: str) -> str:
        """
        If no alias, try to return a reasonable output label.
        - For simple identifiers: id, table.col => last part
        - For functions/expressions: return the whole expr (shortened)
        """
        e = expr.strip()
        # simple identifier or qualified name
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", e):
            return e.split(".")[-1]
        # wildcard
        if e == "*":
            return "*"
        # fallback: expression itself (trim a bit)
        return e[:80] + ("…" if len(e) > 80 else "")

    # -----------------------------
    # FROM / tables / joins
    # -----------------------------

    def _extract_tables(self, query: str) -> list[str]:
        """
        Best-effort: grab the first table token after top-level FROM.
        Also includes joined tables from JOIN parsing.
        """
        q = _strip_trailing_semicolon(query)

        from_body = _extract_clause(q, " from ", [" where ", " group by ", " order by ", " limit ", " fetch "])
        if not from_body:
            # Could be SELECT without FROM
            return self._dedupe_keep_order([j["table"] for j in self._extract_joins(q)])

        # If there are joins, they will be captured separately.
        # For base table, take the first token before JOIN/commas
        base = from_body
        # cut at first top-level join keyword
        cut = len(base)
        for kw in [
            " join ",
            " left join ",
            " right join ",
            " inner join ",
            " full join ",
            " cross join ",
        ]:
            p = base.lower().find(kw)
            if p != -1:
                cut = min(cut, p)
        base = base[:cut].strip()

        # if multiple tables in FROM (comma joins), take them top-level split
        base_tables = _split_top_level_commas(base)
        base_tables = [self._clean_table_ref(t) for t in base_tables if t.strip()]
        join_tables = [j["table"] for j in self._extract_joins(q)]

        return self._dedupe_keep_order(base_tables + join_tables)

    def _clean_table_ref(self, t: str) -> str:
        """
        Turn 'orders o' or 'schema.orders AS o' into 'orders' or 'schema.orders'
        without being too smart.
        """
        tt = t.strip()
        # remove trailing alias
        # split on whitespace at top-level (no parens expected here usually)
        parts = tt.split()
        if not parts:
            return tt
        # handle "schema.table"
        return parts[0].strip().strip('"')

    def _extract_joins(self, query: str) -> list[dict[str, str]]:
        q = query
        joins = []
        for m in re.finditer(
            r"\b(left|right|inner|full|cross)?\s*join\s+([a-zA-Z0-9_.\"]+)",
            q,
            flags=re.I,
        ):
            raw_type = (m.group(1) or "").strip()
            join_type = (raw_type if raw_type else "JOIN").upper()
            table = m.group(2).strip().strip('"')
            if table:  # never append empty table name
                joins.append({"type": join_type, "table": table})
        return joins

    # -----------------------------
    # WHERE / GROUP BY / ORDER BY (top-level only)
    # -----------------------------

    def _extract_where(self, query: str) -> str:
        q = _strip_trailing_semicolon(query)
        return _extract_clause(q, " where ", [" group by ", " order by ", " limit ", " fetch "])

    def _extract_group_by(self, query: str) -> list[str]:
        q = _strip_trailing_semicolon(query)
        body = _extract_clause(q, " group by ", [" having ", " order by ", " limit ", " fetch "])
        if not body:
            return []
        return [c.strip() for c in _split_top_level_commas(body) if c.strip()]

    def _extract_having(self, query: str) -> str:
        q = _strip_trailing_semicolon(query)
        return _extract_clause(q, " having ", [" order by ", " limit ", " fetch "])

    def _extract_order_by(self, query: str) -> list[str]:
        q = _strip_trailing_semicolon(query)
        body = _extract_clause(q, " order by ", [" limit ", " fetch "])
        if not body:
            return []
        return [c.strip() for c in _split_top_level_commas(body) if c.strip()]

    # -----------------------------
    # Heuristics helpers
    # -----------------------------

    def _count_subqueries(self, query: str) -> int:
        # counts additional SELECT occurrences beyond the first
        return max(0, len(re.findall(r"\bselect\b", query, flags=re.I)) - 1)

    def _complexity_score(self, query: str) -> float:
        q = query.upper()
        score = 0.0
        score += 5.0 * len(re.findall(r"\bJOIN\b", q))
        score += 15.0 * self._count_subqueries(query)
        score += 10.0 * len(re.findall(r"\bUNION\b", q))
        # count top-level clauses via our extractors
        if self._extract_where(query):
            score += 5.0
        if self._extract_group_by(query):
            score += 5.0
        if self._extract_order_by(query):
            score += 5.0
        return float(min(score, 100.0))

    def _dedupe_keep_order(self, xs: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in xs:
            if not x:
                continue
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out
