from .base import BaseCollector
from app.schemas.models import AnalysisFacts, Finding, PlanArtifact, QueryRequest
import asyncpg
import os

class PostgresCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        dsn = os.getenv("POSTGRES_DSN", "")
        if not dsn:
            return self.not_configured("postgresql")

        facts = AnalysisFacts(db_type="postgresql")
        try:
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {request.query}")
                plan_json = rows[0][0]  # list with one element, already parsed by asyncpg
                facts.plan = PlanArtifact(format="json", raw=plan_json)
                facts.findings = _extract_findings(plan_json)
            finally:
                await conn.close()
        except Exception as e:
            facts.warnings.append(f"EXPLAIN failed: {str(e)}")
        return facts


def _extract_findings(plan: list) -> list[Finding]:
    findings = []
    _walk_node(plan[0].get("Plan", {}), findings)
    return findings


def _walk_node(node: dict, findings: list):
    node_type = node.get("Node Type", "")
    rows = node.get("Plan Rows", 0)
    cost = node.get("Total Cost", 0)

    # Seq scan on large estimated row count
    if node_type == "Seq Scan" and rows > 1000:
        findings.append(Finding(
            type="seq_scan",
            severity="high",
            title=f"Sequential scan on '{node.get('Relation Name', 'unknown')}'",
            evidence=f"Estimated {rows} rows, cost {cost}",
            recommendation="Consider adding an index on the filter column(s)"
        ))

    # Nested Loop with high cost
    if node_type == "Nested Loop" and cost > 5000:
        findings.append(Finding(
            type="nested_loop",
            severity="medium",
            title="Expensive Nested Loop join detected",
            evidence=f"Total cost: {cost}",
            recommendation="Check join conditions and ensure join columns are indexed"
        ))

    # Hash join (informational)
    if node_type == "Hash Join":
        findings.append(Finding(
            type="hash_join",
            severity="low",
            title="Hash Join detected",
            evidence=f"Rows: {rows}, Cost: {cost}",
            recommendation="Hash joins are generally efficient; ensure adequate work_mem"
        ))

    # Recurse into child plans
    for child in node.get("Plans", []):
        _walk_node(child, findings)