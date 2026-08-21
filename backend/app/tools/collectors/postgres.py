import os

import asyncpg

from app.schemas.models import AnalysisFacts, PlanArtifact, QueryRequest
from app.tools.plan_parsers.postgres import json_nodes_for_live_plan, parse_postgres_explain

from .base import BaseCollector


class PostgresCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        # Issue #61: a pasted EXPLAIN plan is parsed directly, no DSN
        # needed, and takes priority over attempting a live connection.
        # This is what actually backs QueryInput.jsx's "pasting a real
        # EXPLAIN plan upgrades heuristic findings from estimated to
        # schema-verified" promise — POSTGRES_DSN has never been set in
        # this deployment, so before this fix that promise was false for
        # every real user; the pasted text was silently dropped and only a
        # live connection (which never existed) would have done anything.
        explain_plan = (request.explain_plan or "").strip()
        if explain_plan:
            parsed = parse_postgres_explain(explain_plan)
            facts = AnalysisFacts(db_type="postgresql")
            if parsed:
                facts.plan = parsed.artifact
                facts.findings = parsed.findings
            else:
                facts.warnings.append(
                    "Pasted EXPLAIN plan could not be parsed — expected JSON "
                    "(EXPLAIN (FORMAT JSON) ...) or plain-text tabular output "
                    "(EXPLAIN (ANALYZE, BUFFERS) ...)."
                )
            return facts

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
                # Shares the exact same node-walking/finding-generation
                # logic the pasted-JSON path above uses — not a second,
                # hand-kept-in-sync copy of the old _extract_findings/_walk_node.
                _nodes, findings = json_nodes_for_live_plan(plan_json)
                facts.findings = findings
            finally:
                await conn.close()
        except Exception as e:
            facts.warnings.append(f"EXPLAIN failed: {str(e)}")
        return facts
