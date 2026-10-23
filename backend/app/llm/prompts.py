"""Shared prompt fragments for the LLM providers."""

# Appended to every provider's system prompt. A rewritten query that returns
# different rows or aggregates than the original is worse than no rewrite.
REWRITE_GUARDRAILS = (
    "The rewritten_query MUST return exactly the same rows and aggregate values as the "
    "original: keep every WHERE/JOIN filter (never move a filter into a subquery in a way "
    "that changes what an outer aggregate counts), keep column names and ORDER BY, and use "
    "half-open date ranges (col >= 'YYYY-01-01' AND col < 'YYYY+1-01-01') instead of BETWEEN "
    "with a last-day end date. Never recommend an index on a SELECT alias, an aggregate result, "
    "or a column of a derived table/CTE; recommend indexes only on real base-table columns. "
    "Beware join fan-out: never LEFT JOIN two one-to-many child tables directly and then aggregate, "
    "because each child's rows multiply the other's (COUNT/SUM inflate). Pre-aggregate each child in its "
    "own subquery or CTE keyed by the parent id and join those results, or use COUNT(DISTINCT child_pk). "
    "Preserve NULL semantics: a correlated COUNT(*) subquery returns 0 when no rows match, but a LEFT JOIN "
    "to a pre-aggregated CTE returns NULL, which also changes ORDER BY placement, so wrap such columns in "
    "COALESCE(col, 0) (use the matching neutral value for SUM; AVG legitimately stays NULL). "
    "Format rewritten_query as readable multi-line SQL: one clause per line (SELECT, FROM, JOIN, WHERE, "
    "GROUP BY, ORDER BY), two-space indents, CTEs on their own lines. "
    "If you cannot rewrite safely, return the original query unchanged."
)
