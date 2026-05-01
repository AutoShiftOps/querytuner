from app.schemas.models import AnalysisFacts, QueryRequest

from .base import BaseCollector


class MySQLCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        return self.not_configured("mysql")  # full impl coming Week 2
