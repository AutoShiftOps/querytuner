from .base import BaseCollector
from app.schemas.models import AnalysisFacts, QueryRequest

class SQLServerCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        return self.not_configured("sqlserver") # full implementation coming Week 2, requires pyodbc and SQL Server setup