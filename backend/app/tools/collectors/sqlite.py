from app.schemas.models import AnalysisFacts, QueryRequest

from .base import BaseCollector


class SQLiteCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        # full implementation coming Week 2, requires a live SQLite DB setup
        # and aiosqlite for async queries
        return self.not_configured("sqlite")
