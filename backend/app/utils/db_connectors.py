from app.schemas.models import DatabaseType
from typing import Optional
import os


def get_connection_params(db_type: DatabaseType, dsn: Optional[str] = None) -> dict:
    """
    Returns connection params from env or passed DSN.
    Used by collectors — not for direct query execution.
    """
    if db_type == DatabaseType.POSTGRES:
        return {"dsn": dsn or os.getenv("POSTGRES_DSN", "")}
    elif db_type == DatabaseType.MYSQL:
        return {"dsn": dsn or os.getenv("MYSQL_DSN", "")}
    elif db_type == DatabaseType.SQLITE:
        return {"path": dsn or os.getenv("SQLITE_PATH", ":memory:")}
    elif db_type == DatabaseType.SQL_SERVER:
        return {"dsn": dsn or os.getenv("SQLSERVER_DSN", "")}
    elif db_type == DatabaseType.ORACLE:
        return {"dsn": dsn or os.getenv("ORACLE_DSN", "")}
    return {}
