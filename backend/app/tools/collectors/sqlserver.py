from app.schemas.models import AnalysisFacts, QueryRequest

from .base import BaseCollector


class SQLServerCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        # full implementation coming Week 2, requires pyodbc and SQL Server setup
        return self.not_configured("sqlserver")
