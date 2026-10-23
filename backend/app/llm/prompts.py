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
    "If you cannot rewrite safely, return the original query unchanged."
)
