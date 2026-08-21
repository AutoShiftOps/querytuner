"""
Integration tests for Issue #61/#62/#63's full wiring — the pieces that
test_plan_parsers_postgres.py, test_plan_parsers_mysql.py, and
test_plan_crossref.py each test in isolation actually connecting end to
end: PostgresCollector/MySQLCollector picking a pasted plan over a live
DSN attempt, execution_planner.collect_facts()'s new tuple return, and
SQLAnalyzerAgent.analyze() cross-referencing the parsed plan against the
suggestions from the exact same request.

These are the scenarios traced out in
docs/querytuner-explain-parser-issue.md's "why this matters" section —
confirming QueryInput.jsx's "pasting a real EXPLAIN plan upgrades
heuristic findings from estimated to schema-verified" claim is now
actually true, not just that the individual parsing/cross-referencing
functions work when called directly.
"""

import pytest

from app.agents.sql_analyzer import SQLAnalyzerAgent
from app.schemas.models import DatabaseType, QueryRequest
from app.tools.collectors.mysql import MySQLCollector
from app.tools.collectors.postgres import PostgresCollector
from app.tools.execution_planner import collect_facts


def index_suggestions(suggestions):
    return [s for s in suggestions if s["type"].startswith("index_review_")]


class TestPostgresCollectorPrefersPastedPlan:
    @pytest.mark.asyncio
    async def test_pasted_plan_used_without_touching_dsn(self, monkeypatch):
        """No POSTGRES_DSN set in this test environment at all — if the
        collector tried a live connection it would fail/warn. Asserting
        it doesn't even try when a plan was pasted."""
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        request = QueryRequest(
            query="SELECT * FROM orders WHERE status = 'pending'",
            db_type=DatabaseType.POSTGRES,
            explain_plan="Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)",
        )
        facts = await PostgresCollector().collect(request)

        assert facts.plan is not None
        assert facts.plan.format == "text"
        assert any(f.type == "seq_scan" for f in facts.findings)
        assert not facts.warnings  # no "not configured" warning — the pasted path was taken

    @pytest.mark.asyncio
    async def test_no_plan_and_no_dsn_falls_back_to_not_configured(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        request = QueryRequest(query="SELECT 1", db_type=DatabaseType.POSTGRES, explain_plan=None)
        facts = await PostgresCollector().collect(request)

        assert facts.plan is None
        assert facts.warnings  # the pre-existing "not configured" warning

    @pytest.mark.asyncio
    async def test_unparseable_pasted_plan_warns_instead_of_attempting_dsn(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        request = QueryRequest(query="SELECT 1", db_type=DatabaseType.POSTGRES, explain_plan="garbage, not a plan")
        facts = await PostgresCollector().collect(request)

        assert facts.plan is None
        assert any("could not be parsed" in w for w in facts.warnings)


class TestMySQLCollector:
    @pytest.mark.asyncio
    async def test_pasted_plan_parsed(self):
        request = QueryRequest(
            query="SELECT * FROM orders",
            db_type=DatabaseType.MYSQL,
            explain_plan='{"query_block": {"table": {"table_name": "orders", "access_type": "ALL", "rows_examined_per_scan": 10000}}}',
        )
        facts = await MySQLCollector().collect(request)

        assert facts.plan is not None
        assert any(f.type == "full_table_scan" for f in facts.findings)

    @pytest.mark.asyncio
    async def test_no_plan_stays_not_configured(self):
        request = QueryRequest(query="SELECT 1", db_type=DatabaseType.MYSQL, explain_plan=None)
        facts = await MySQLCollector().collect(request)

        assert facts.plan is None
        assert facts.warnings


class TestCollectFactsReturnsNodes:
    @pytest.mark.asyncio
    async def test_postgres_returns_populated_nodes(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        request = QueryRequest(
            query="SELECT * FROM orders",
            db_type=DatabaseType.POSTGRES,
            explain_plan="Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)",
        )
        facts, nodes = await collect_facts(request)

        assert facts.plan is not None
        assert len(nodes) == 1
        assert nodes[0].relation == "orders"

    @pytest.mark.asyncio
    async def test_sqlite_returns_empty_nodes_not_an_error(self):
        """A dialect with no plan parser wired up (#61/#62 scope is
        Postgres/MySQL only) must degrade to an empty nodes list, not
        raise — collect_facts() is called on every /analyze request
        regardless of db_type."""
        request = QueryRequest(query="SELECT 1", db_type=DatabaseType.SQLITE, explain_plan=None)
        facts, nodes = await collect_facts(request)

        assert nodes == []
        assert facts.db_type == "sqlite"


class TestFullPipelineCrossReference:
    """Formalizes the exact scenarios verified manually against the live
    agent before writing this test — see this task's own verification
    notes. Postgres only; MySQL's cross-referencing is exercised at the
    plan_crossref.py level (test_plan_crossref.py) since the matching
    logic is dialect-agnostic once nodes are produced."""

    @pytest.mark.asyncio
    async def test_confirmation_upgrades_evidence_level(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        analyzer = SQLAnalyzerAgent()
        query = "SELECT * FROM orders WHERE status = 'pending'"
        explain = "Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)\n  Filter: (status = 'pending'::text)"

        result = await analyzer.analyze(
            query=query, db_type="postgresql", use_llm=False, focus="performance", explain_plan=explain
        )
        suggestions = index_suggestions(result["optimization_suggestions"])

        assert suggestions, "Expected at least one index suggestion for an unindexed WHERE column"
        status_suggestion = next(s for s in suggestions if "status" in str(s.get("columns")))
        assert status_suggestion["evidence_level"] == "schema-verified"
        assert status_suggestion["plan_verified"] is True

    @pytest.mark.asyncio
    async def test_contradiction_flagged_without_false_confidence(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        analyzer = SQLAnalyzerAgent()
        query = "SELECT * FROM orders WHERE customer_id = 5"
        explain = (
            "Index Scan using idx_orders_customer_id on orders  (cost=0.42..8.44 rows=1 width=244)\n"
            "  Index Cond: (customer_id = 5)"
        )

        result = await analyzer.analyze(
            query=query, db_type="postgresql", use_llm=False, focus="performance", explain_plan=explain
        )
        suggestions = index_suggestions(result["optimization_suggestions"])

        assert suggestions
        customer_id_suggestion = next(s for s in suggestions if "customer_id" in str(s.get("columns")))
        assert customer_id_suggestion["plan_contradicts"] is True
        # The critical assertion per the design doc's own risk framing —
        # a contradicted suggestion must NOT also read as confirmed.
        assert customer_id_suggestion["evidence_level"] != "schema-verified"
        assert customer_id_suggestion.get("plan_verified") is not True

    @pytest.mark.asyncio
    async def test_no_explain_plan_baseline_unaffected(self, monkeypatch):
        """Confirms this whole chain is additive — a request with no
        pasted plan behaves exactly as it did before #61/#62/#63."""
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        analyzer = SQLAnalyzerAgent()
        query = "SELECT * FROM orders WHERE status = 'pending'"

        result = await analyzer.analyze(query=query, db_type="postgresql", use_llm=False, focus="performance")
        suggestions = index_suggestions(result["optimization_suggestions"])

        assert suggestions
        assert all(s["evidence_level"] != "schema-verified" for s in suggestions)
        assert all(not s.get("plan_verified") for s in suggestions)
        assert all(not s.get("plan_contradicts") for s in suggestions)
