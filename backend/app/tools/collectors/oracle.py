from .base import BaseCollector
from app.schemas.models import AnalysisFacts, QueryRequest


class OracleCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        # full implementation coming Week 2, requires cx_Oracle and Oracle DB setup
        return self.not_configured("oracle")
