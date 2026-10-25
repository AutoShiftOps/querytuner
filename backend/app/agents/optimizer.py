from __future__ import annotations

import re
from typing import Any

# Issue #73: dialect-aware rewrites
from app.utils.dialect_config import get_dialect


class QueryOptimizer:
    """
    Rule-based query rewriter.

    Only applies rewrites that return exactly the same rows and stay runnable,
    so the result is safe to copy and execute. Anything that needs a human
    decision (which columns to select, page size, CTE refactors, LIKE and
    LOWER() alternatives, MONTH() without a year) is reported as a finding
    instead of being written into the SQL as a placeholder or comment.

    Returns "" when no safe rewrite applies.
    """

    def rewrite(self, query: str, suggestions: list[dict[str, Any]], db_type: str) -> str:
        q = query.strip()
        cfg = get_dialect(db_type)
        applied: list[str] = []

        q, changed = self._rewrite_year_function(q, db_type)
        if changed:
            applied.append("YEAR(col) = N rewritten as a date range so an index on col can be used")

        if not applied:
            return ""

        header = [
            "-- QueryTuner safe rewrite: same results, review before applying",
            f"-- Dialect: {cfg.display}",
            *[f"-- Change: {a}" for a in applied],
        ]
        return "\n".join(header) + "\n\n" + q

    def _rewrite_year_function(self, q: str, db_type: str):
        """
        YEAR(col) = 2025 → (col >= '2025-01-01' AND col < '2026-01-01')
        Half-open range: same rows as YEAR() for date and datetime columns.
        Issue #73: Oracle uses DATE literal, others use string literal.
        """
        pattern = r"YEAR\s*\(\s*([\w.]+)\s*\)\s*=\s*(\d{4})"

        def _replace(m):
            col = m.group(1).strip()
            yr = m.group(2).strip()
            nxt = int(yr) + 1
            if db_type == "oracle":
                return f"({col} >= DATE '{yr}-01-01' AND {col} < DATE '{nxt}-01-01')"
            return f"({col} >= '{yr}-01-01' AND {col} < '{nxt}-01-01')"

        new_q, n = re.subn(pattern, _replace, q, flags=re.IGNORECASE)
        return new_q, n > 0
