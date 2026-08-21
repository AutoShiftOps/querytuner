"""
Internal (non-Pydantic, not part of the public API schema) representation
of a parsed EXPLAIN plan — shared between the Postgres and MySQL parsers
(Issue #61/#62) and the cross-referencing logic that consumes them
(Issue #63, backend/app/tools/plan_crossref.py).

Deliberately separate from app.schemas.models: PlanArtifact/AnalysisFacts
already have exactly the right shape for what the API actually returns
(the design doc confirmed this — no schema changes needed there). This
module is the intermediate, structured form the parsers produce on the
way to building a PlanArtifact/list[Finding], and on the way to feeding
plan_crossref.py's suggestion matching — neither of which needs to be
serialized to the frontend, so a plain dataclass is enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.models import Finding, PlanArtifact


@dataclass
class PlanNode:
    """One node from a parsed EXPLAIN plan, normalized across the
    Postgres (Node Type / Relation Name / Alias) and MySQL
    (access_type / table_name) shapes so plan_crossref.py doesn't need
    dialect-specific branches."""

    node_type: str
    relation: str | None = None
    alias: str | None = None
    rows: int | None = None
    cost: float | None = None
    index_name: str | None = None
    # The column referenced by this node's own filter/index condition
    # (Postgres: "Index Cond"/"Filter"/"Recheck Cond"; not populated for
    # MySQL v1 — its JSON shape doesn't expose per-table conditions the
    # same direct way). None when not extractable — callers must treat
    # that as "unknown," not "no condition."
    condition_column: str | None = None
    # A scan that reads the whole table with no index narrowing it down —
    # Postgres "Seq Scan", MySQL access_type "ALL".
    is_full_scan: bool = False
    # A scan that IS using an index to narrow rows — Postgres "Index
    # Scan"/"Index Only Scan"/"Bitmap Heap Scan", MySQL any access_type
    # other than "ALL".
    is_index_access: bool = False


@dataclass
class ParsedPlan:
    artifact: PlanArtifact
    nodes: list[PlanNode] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
