from .base import BaseCollector
from app.schemas.models import AnalysisFacts, QueryRequest

class SQLiteCollector(BaseCollector):
    async def collect(self, request: QueryRequest) -> AnalysisFacts:
        return self.not_configured("sqlite")  # full implementation coming Week 2, requires a live SQLite DB setup and aiosqlite for async queries