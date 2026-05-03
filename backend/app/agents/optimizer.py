from __future__ import annotations

import re
from typing import Any


class QueryOptimizer:
    """
    Rule-based query rewriter.
    Applies targeted, safe SQL rewrites based on heuristic findings.
    Never changes query semantics silently — uses comments to flag intent.
    Called by SQLAnalyzerAgent._compose_optimized_query().
    """

    def rewrite(self, query: str, suggestions: list[dict[str, Any]], db_type: str) -> str:
        q = query.strip()
        header_lines: list[str] = [
            "-- QueryTuner: Suggested optimized SQL (review before applying)",
            f"-- DB: {db_type}",
        ]
        applied: list[str] = []

        # --- Rewrite 1: YEAR(col) = N → range condition ---
        # Fixes: function_in_where for YEAR() — enables index seek
        q, changed = self._rewrite_year_function(q)
        if changed:
            applied.append("YEAR() rewritten as range condition to enable index seek")

        # --- Rewrite 2: MONTH(col) = N → range condition ---
        q, changed = self._rewrite_month_function(q)
        if changed:
            applied.append("MONTH() rewritten as range condition to enable index seek")

        # --- Rewrite 3: LOWER(col) = 'val' comment ---
        q, changed = self._rewrite_lower_function(q)
        if changed:
            applied.append("LOWER() in WHERE flagged — use case-insensitive collation or index instead")

        # --- Rewrite 4: SELECT * placeholder ---
        q, changed = self._rewrite_select_star(q)
        if changed:
            applied.append("SELECT * replaced with column placeholder — list only required columns")

        # --- Rewrite 5: Add LIMIT hint for ORDER BY without LIMIT ---
        ql = q.lower()
        has_order_by = bool(re.search(r"\border\s+by\b", ql, re.IGNORECASE))
        has_limit = (
            bool(re.search(r"\blimit\b", ql))
            or bool(re.search(r"\bfetch\s+first\b", ql))
            or "rownum" in ql
            or bool(re.search(r"\btop\s+\d", ql))
        )
        if has_order_by and not has_limit:
            q, changed = self._suggest_limit(q, db_type)
            if changed:
                applied.append("LIMIT placeholder added for ORDER BY without pagination")

        # --- Rewrite 6: Correlated subquery → CTE hint ---
        q, changed = self._suggest_cte_for_subquery(q)
        if changed:
            applied.append("Correlated subquery detected — CTE refactor suggested above query")

        if applied:
            header_lines.append("-- Changes applied:")
            for a in applied:
                header_lines.append(f"--   • {a}")
        else:
            header_lines.append("-- No automatic rewrites applied; see suggestions above")

        return "\n".join(header_lines) + "\n\n" + q

    # ------------------------------------------------------------------
    # Individual rewrite methods — each returns (new_query, was_changed)
    # ------------------------------------------------------------------

    def _rewrite_year_function(self, q: str):
        """YEAR(col) = 2025  →  col BETWEEN '2025-01-01' AND '2025-12-31'"""
        pattern = r"YEAR\s*\(\s*([\w.]+)\s*\)\s*=\s*(\d{4})"

        def _replace(m):
            col = m.group(1).strip()
            yr = m.group(2).strip()
            return f"{col} BETWEEN '{yr}-01-01' AND '{yr}-12-31'"

        new_q, n = re.subn(pattern, _replace, q, flags=re.IGNORECASE)
        return new_q, n > 0

    def _rewrite_month_function(self, q: str):
        """MONTH(col) = 3  →  col BETWEEN 'YYYY-03-01' AND 'YYYY-03-31' (approximate)"""
        pattern = r"MONTH\s*\(\s*([\w.]+)\s*\)\s*=\s*(\d{1,2})"

        def _replace(m):
            col = m.group(1).strip()
            mo = int(m.group(2).strip())
            mo_str = f"{mo:02d}"
            # last day approximation — safe, reviewer will confirm
            last_day = {
                1: 31,
                2: 28,
                3: 31,
                4: 30,
                5: 31,
                6: 30,
                7: 31,
                8: 31,
                9: 30,
                10: 31,
                11: 30,
                12: 31,
            }.get(mo, 30)
            return f"{col} BETWEEN 'YYYY-{mo_str}-01' AND 'YYYY-{mo_str}-{last_day}' /* replace YYYY */"

        new_q, n = re.subn(pattern, _replace, q, flags=re.IGNORECASE)
        return new_q, n > 0

    def _rewrite_lower_function(self, q: str):
        """LOWER(col) = 'val'  →  add comment about collation-based alternative"""
        pattern = r"LOWER\s*\(\s*([\w.]+)\s*\)\s*=\s*('[^']*')"

        def _replace(m):
            col = m.group(1).strip()
            val = m.group(2).strip()
            # Keep the condition but prepend an inline hint
            return f"/* TIP: use case-insensitive collation or index on {col} instead of LOWER() */ {col} = {val}"

        new_q, n = re.subn(pattern, _replace, q, flags=re.IGNORECASE)
        return new_q, n > 0

    def _rewrite_select_star(self, q: str):
        """SELECT *  →  SELECT /* TODO: list required columns */"""
        pattern = r"\bSELECT\s+\*"
        new_q, n = re.subn(pattern, "SELECT /* TODO: list required columns */", q, flags=re.IGNORECASE)
        return new_q, n > 0

    def _suggest_limit(self, q: str, db_type: str):
        """Append LIMIT / TOP / FETCH FIRST based on dialect at end of query."""
        db = (db_type or "").lower()
        q_stripped = "\n".join(line.rstrip() for line in q.rstrip().rstrip(";").splitlines())
        if db == "sqlserver":
            # For SQL Server, TOP goes after SELECT — too risky to auto-inject; add comment
            return (
                q_stripped + "\n-- TODO: Add TOP N or OFFSET/FETCH NEXT N ROWS ONLY",
                True,
            )
        elif db == "oracle":
            return q_stripped + "\nFETCH FIRST 100 ROWS ONLY -- TODO: adjust N", True
        else:
            return q_stripped + "\nLIMIT 100  -- adjust to your page size", True

    def _suggest_cte_for_subquery(self, q: str):
        """If a SELECT appears inside WHERE/FROM at depth > 0, prepend a CTE refactor hint."""
        # Count nested SELECTs beyond the first
        nested = len(re.findall(r"\bSELECT\b", q, re.IGNORECASE)) - 1
        if nested < 1:
            return q, False

        cte_hint = (
            "/* QueryTuner CTE hint: this query has nested subqueries that may be refactored.\n"
            "   Example pattern:\n"
            "   WITH subquery_name AS (\n"
            "       SELECT ... FROM ... WHERE ...\n"
            "   )\n"
            "   SELECT ... FROM main_table JOIN subquery_name ON ...\n"
            "*/\n"
        )
        return cte_hint + q, True
