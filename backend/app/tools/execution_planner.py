from app.schemas.models import AnalysisFacts, DatabaseType, QueryRequest
from app.tools.plan_parsers.models import PlanNode


async def collect_facts(request: QueryRequest) -> tuple[AnalysisFacts, list[PlanNode]]:
    """
    Routes to the correct DB collector based on db_type.
    Returns (AnalysisFacts, structured plan nodes) — AnalysisFacts is
    unchanged (what the API response's `facts` field is built from); the
    second element is new (Issue #61/#62/#63) and backs cross-referencing
    the parsed plan against index_recommender's suggestions in
    sql_analyzer.py. BaseCollector's own contract is untouched — each
    collector still just returns AnalysisFacts; nodes are re-derived from
    the resulting facts.plan artifact (nodes_from_artifact in
    plan_parsers/postgres.py and .../mysql.py) rather than changing every
    collector's return type for the two dialects that actually parse a
    plan today.
    """
    db_type = request.db_type

    if db_type == DatabaseType.POSTGRES:
        from app.tools.collectors.postgres import PostgresCollector
        from app.tools.plan_parsers.postgres import nodes_from_artifact

        facts = await PostgresCollector().collect(request)
        nodes = nodes_from_artifact(facts.plan) if facts.plan else []
        return facts, nodes

    elif db_type == DatabaseType.MYSQL:
        from app.tools.collectors.mysql import MySQLCollector
        from app.tools.plan_parsers.mysql import nodes_from_artifact as mysql_nodes_from_artifact

        facts = await MySQLCollector().collect(request)
        nodes = mysql_nodes_from_artifact(facts.plan) if facts.plan else []
        return facts, nodes

    elif db_type == DatabaseType.SQLITE:
        from app.tools.collectors.sqlite import SQLiteCollector

        return await SQLiteCollector().collect(request), []

    elif db_type == DatabaseType.SQL_SERVER:
        from app.tools.collectors.sqlserver import SQLServerCollector

        return await SQLServerCollector().collect(request), []

    elif db_type == DatabaseType.ORACLE:
        from app.tools.collectors.oracle import OracleCollector

        return await OracleCollector().collect(request), []

    else:
        return AnalysisFacts(db_type=db_type.value, warnings=["No collector available for this DB type"]), []
