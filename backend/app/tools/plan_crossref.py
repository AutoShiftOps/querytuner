"""
Issue #63: cross-references a parsed EXPLAIN plan (Issue #61/#62) against
the index_recommender suggestions already computed for the same query —
the part of this chain that actually makes QueryInput.jsx's UI promise
true. #61/#62 alone just produce another unused `facts` blob; nothing
before this read `facts.plan` for anything.

Two directions, per the design doc:
  - Confirmation: a suggestion whose table shows a full scan (Seq Scan /
    MySQL access_type ALL) in the real plan is upgraded to
    evidence_level="schema-verified" — the literal word the UI already
    promises.
  - Contradiction: if the plan shows an index already being used on the
    EXACT column a heuristic flagged as unindexed, the suggestion is
    likely wrong (stale heuristic, or schema drift) — flagged via
    plan_contradicts rather than silently left as-is or wrongly upgraded.
    Scoped to single-column suggestion types only (see
    _CONTRADICTION_ELIGIBLE_TYPES) — a composite suggestion isn't
    necessarily wrong just because one of its columns already has its own
    index; that's a separate judgment call this v1 doesn't attempt.

The design doc calls out table/column name matching as "the likely
fragile point" — see _matching_nodes' docstring for exactly how aliases
are resolved, and test_plan_crossref.py for the cases this was actually
verified against.
"""

from __future__ import annotations

from typing import Any

# _resolve_real_table is underscore-prefixed (index_recommender.py-internal
# by convention) but reused here rather than duplicated — same alias ->
# real-table-name resolution _detect_composite_opportunity already uses,
# and getting that logic out of sync between the two call sites would be
# a worse outcome than the cross-module reach.
from app.tools.index_recommender import _resolve_real_table
from app.tools.plan_parsers.models import PlanNode

_INDEX_REVIEW_PREFIX = "index_review_"

_CONTRADICTION_ELIGIBLE_TYPES = {
    "index_review_join_key",
    "index_review_where_filter",
    "index_review_order_by_index",
    "index_review_group_by_index",
    "index_review_partial_index_candidate",
}


def cross_reference_plan(
    suggestions: list[dict[str, Any]],
    plan_nodes: list[PlanNode],
    schema: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Mutates and returns `suggestions` in place — only ever touches entries
    whose type starts with "index_review_" (the ones index_recommender.py
    produces about specific columns); every other heuristic type (SELECT
    *, cartesian join, ...) has nothing an EXPLAIN plan could confirm or
    contradict and is left untouched.
    """
    if not plan_nodes:
        return suggestions
    schema = schema or {}

    for suggestion in suggestions:
        s_type = suggestion.get("type", "")
        if not s_type.startswith(_INDEX_REVIEW_PREFIX):
            continue

        confirmed = False
        contradicted = False

        for qualified_col in suggestion.get("columns") or []:
            alias, sep, col = qualified_col.partition(".")
            if not sep:
                # No alias in the original column reference (e.g. a bare
                # `WHERE status = 'pending'` with no table prefix at all)
                # — _matching_nodes' single-relation fallback handles this.
                alias, col = None, alias

            for node in _matching_nodes(alias, schema, plan_nodes):
                if node.is_full_scan:
                    confirmed = True
                elif (
                    s_type in _CONTRADICTION_ELIGIBLE_TYPES
                    and node.is_index_access
                    and node.condition_column
                    and node.condition_column == col
                ):
                    contradicted = True

        if confirmed:
            suggestion["plan_verified"] = True
            suggestion["evidence_level"] = "schema-verified"
        if contradicted:
            suggestion["plan_contradicts"] = True

    return suggestions


def _matching_nodes(
    alias: str | None,
    schema: dict[str, dict[str, str]],
    plan_nodes: list[PlanNode],
) -> list[PlanNode]:
    """
    Resolves a suggestion's table alias to the plan node(s) that actually
    touch that table. Three ways a match can happen, tried in order:
      1. The plan node's own alias matches exactly (the common, reliable
         case — the EXPLAIN plan is generated from the same query the
         suggestion's alias came from, so an aliased query's plan carries
         the identical alias).
      2. No alias was used in the query at all, so the suggestion's
         "alias" is actually the bare table name — matches the plan
         node's relation name directly.
      3. (Only if schema_info was also pasted) the alias resolves to a
         real table name via schema DDL, matched against the plan node's
         relation name — covers a query that used an alias the EXPLAIN
         plan doesn't happen to echo (rare, but schema-verified table
         resolution is already how index_recommender.py itself handles
         this ambiguity elsewhere).

    If none of those match anything (including when the suggestion's
    column had no alias/table info at all), and the plan only touches ONE
    distinct relation, that relation is assumed to be the one in question
    — the common case for a simple single-table query, which is exactly
    what QueryInput.jsx's own EXPLAIN placeholder example shows
    (`Seq Scan on orders ...`, no alias). A multi-table plan with no
    direct match returns no matches rather than guessing.
    """
    real_table = _resolve_real_table(alias, schema) if alias and schema else None
    matches = [
        node
        for node in plan_nodes
        if (alias and node.alias == alias)
        or (alias and node.relation == alias)
        or (real_table and node.relation == real_table)
    ]
    if matches:
        return matches

    relations = {node.relation for node in plan_nodes if node.relation}
    if len(relations) == 1:
        (only_relation,) = relations
        return [node for node in plan_nodes if node.relation == only_relation]

    return []
