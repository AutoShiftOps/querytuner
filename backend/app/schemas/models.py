from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LLMProvider(StrEnum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"


class DatabaseType(StrEnum):
    POSTGRES = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    SQL_SERVER = "sqlserver"
    ORACLE = "oracle"


class QueryRequest(BaseModel):
    query: str = Field(..., description="SQL query to analyze")
    db_type: DatabaseType = Field(default=DatabaseType.POSTGRES)
    schema_info: str | None = Field(None, description="Schema DDL for better context")
    llm_provider: LLMProvider = Field(default=LLMProvider.HUGGINGFACE)
    use_llm: bool = Field(default=False)
    focus: str = Field(default="performance")


class Finding(BaseModel):
    type: str  # e.g. "missing_index", "select_star", "security"
    severity: str  # "critical" | "high" | "medium" | "low"
    title: str
    evidence: str | None = None
    recommendation: str | None = None


class PlanArtifact(BaseModel):
    format: str  # "json" | "xml" | "text"
    raw: Any  # dict for json, str for xml/text


class AnalysisFacts(BaseModel):
    db_type: str
    normalized_query: str | None = None
    redacted_query: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    plan: PlanArtifact | None = None
    warnings: list[str] = Field(default_factory=list)


class OptimizationSuggestion(BaseModel):
    type: str
    severity: str
    suggestion: str
    reason: str
    estimated_improvement: str


class ExecutionPlan(BaseModel):
    plan_type: str
    operations: list[dict[str, Any]]
    total_cost: float | None = None
    estimated_rows: int | None = None


class QueryAnalysisResult(BaseModel):
    query: str
    parsed_query: dict[str, Any]
    optimization_suggestions: list[OptimizationSuggestion]
    execution_plan: ExecutionPlan | None = None
    optimized_query: str | None = None
    plain_explanation: str | None = None
    performance_metrics: dict[str, Any]
    security_issues: list[str]
    readability_score: float
    analysis_time_ms: float
    facts: AnalysisFacts | None = None
    ai_attempted: bool = False
    used_ai: bool = False
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_insights: str | None = None
    ai_error: str | None = None
