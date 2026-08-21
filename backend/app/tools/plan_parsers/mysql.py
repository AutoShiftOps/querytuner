"""
Issue #62: parses a pasted MySQL EXPLAIN FORMAT=JSON plan.

Not a copy-paste of the Postgres parser (postgres.py) — MySQL's JSON shape
is a distinct format per the UI's own placeholder example
(QueryInput.jsx's explainPlaceholders.mysql: `{"query_block": {"table":
{"table_name": "orders", "access_type": "ALL", ...}}}`), keyed by
`query_block`/`table`/`nested_loop` rather than Postgres's `Node
Type`/`Plan`/`Plans`. JSON-only, no plain-text fallback — unlike Postgres
(#61), the UI never invites a MySQL plain-text EXPLAIN paste, only
EXPLAIN FORMAT=JSON, so there's no second input shape to support here.

Walks the JSON tree generically (recurse into every dict/list, collect
every "table" object found) rather than modeling MySQL's full JSON EXPLAIN
grammar exactly (nested_loop arrays, materialized subqueries, hash join
representation in MySQL 8+, ...) — robust to the different nesting shapes
a real query can produce without needing to enumerate all of them, which
is more scope than #62 needs (see design doc: "at minimum parses
request.explain_plan the same way the Postgres path does").
"""

from __future__ import annotations

import json

from app.schemas.models import Finding, PlanArtifact

from .models import ParsedPlan, PlanNode


def _walk_mysql_json(node, nodes: list[PlanNode]) -> None:
    if isinstance(node, dict):
        table = node.get("table")
        if isinstance(table, dict):
            table_name = table.get("table_name")
            access_type = table.get("access_type") or ""
            rows = table.get("rows_examined_per_scan")
            if rows is None:
                rows = table.get("rows_produced_per_join")
            key = table.get("key")  # the index actually used, if any — None for a full scan

            cost_info = table.get("cost_info") or {}
            cost = None
            raw_cost = cost_info.get("read_cost") or cost_info.get("prefix_cost") or cost_info.get("query_cost")
            if raw_cost is not None:
                try:
                    cost = float(raw_cost)
                except (TypeError, ValueError):
                    cost = None

            nodes.append(
                PlanNode(
                    node_type=access_type or "unknown",
                    relation=table_name,
                    rows=int(rows) if rows is not None else None,
                    cost=cost,
                    index_name=key,
                    # Issue #62's explicit mapping: access_type == "ALL" is
                    # MySQL's equivalent of Postgres's Seq Scan. Any other
                    # access_type ("ref", "eq_ref", "range", "index",
                    # "const", ...) means the planner is using an index to
                    # at least some degree.
                    is_full_scan=(access_type == "ALL"),
                    is_index_access=bool(access_type) and access_type != "ALL",
                )
            )
        for value in node.values():
            _walk_mysql_json(value, nodes)
    elif isinstance(node, list):
        for item in node:
            _walk_mysql_json(item, nodes)


def _findings_from_nodes(nodes: list[PlanNode]) -> list[Finding]:
    findings: list[Finding] = []
    for node in nodes:
        if node.is_full_scan and (node.rows or 0) > 1000:
            findings.append(
                Finding(
                    type="full_table_scan",
                    severity="high",
                    title=f"Full table scan on '{node.relation or 'unknown'}'",
                    evidence=f"access_type=ALL, estimated {node.rows} rows",
                    recommendation="Consider adding an index on the filter column(s)",
                )
            )
        elif node.is_index_access:
            findings.append(
                Finding(
                    type="index_scan_confirmed",
                    severity="low",
                    title=f"Index usage confirmed on '{node.relation or 'unknown'}' (access_type={node.node_type})",
                    evidence=(f"Using key `{node.index_name}`" if node.index_name else f"access_type={node.node_type}"),
                    recommendation="No action needed — the planner is already using an index here.",
                )
            )
    return findings


def parse_mysql_explain(raw: str) -> ParsedPlan | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        plan_json = json.loads(raw)
    except (ValueError, TypeError):
        return None

    nodes: list[PlanNode] = []
    _walk_mysql_json(plan_json, nodes)
    if not nodes:
        return None
    return ParsedPlan(
        artifact=PlanArtifact(format="json", raw=plan_json),
        nodes=nodes,
        findings=_findings_from_nodes(nodes),
    )


def nodes_from_artifact(artifact: PlanArtifact) -> list[PlanNode]:
    """Mirrors postgres.py's nodes_from_artifact — re-derives structured
    nodes from an already-built PlanArtifact for execution_planner.collect_facts()."""
    if artifact.format != "json":
        return []
    nodes: list[PlanNode] = []
    _walk_mysql_json(artifact.raw, nodes)
    return nodes
