from app.schemas.models import DatabaseType, AnalysisFacts, QueryRequest

async def collect_facts(request: QueryRequest) -> AnalysisFacts:
    """
    Routes to the correct DB collector based on db_type.
    Returns normalized AnalysisFacts regardless of dialect.
    """
    db_type = request.db_type

    if db_type == DatabaseType.POSTGRES:
        from app.tools.collectors.postgres import PostgresCollector
        return await PostgresCollector().collect(request)

    elif db_type == DatabaseType.MYSQL:
        from app.tools.collectors.mysql import MySQLCollector
        return await MySQLCollector().collect(request)

    elif db_type == DatabaseType.SQLITE:
        from app.tools.collectors.sqlite import SQLiteCollector
        return await SQLiteCollector().collect(request)

    elif db_type == DatabaseType.SQL_SERVER:
        from app.tools.collectors.sqlserver import SQLServerCollector
        return await SQLServerCollector().collect(request)

    elif db_type == DatabaseType.ORACLE:
        from app.tools.collectors.oracle import OracleCollector
        return await OracleCollector().collect(request)

    else:
        return AnalysisFacts(db_type=db_type.value,
                             warnings=["No collector available for this DB type"])