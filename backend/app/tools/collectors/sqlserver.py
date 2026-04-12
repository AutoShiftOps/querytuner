from .base import BaseCollector
from app.schemas.models import AnalysisFacts, QueryRequest


class SQLServerCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        # full implementation coming Week 2, requires pyodbc and SQL Server setup
        return self.not_configured("sqlserver")
