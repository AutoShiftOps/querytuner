from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class LLMProvider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"

class DatabaseType(str, Enum):
    POSTGRES = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    SQL_SERVER = "sqlserver"
    ORACLE = "oracle"

class QueryRequest(BaseModel):
    query: str = Field(..., description="SQL query to analyze")
    db_type: DatabaseType = Field(default=DatabaseType.POSTGRES)
    schema_info: Optional[str] = Field(None, description="Schema DDL for better context")
    llm_provider: LLMProvider = Field(default=LLMProvider.HUGGINGFACE)
    use_llm: bool = Field(default=False)
    focus: str = Field(default="performance")

class Finding(BaseModel):
    type: str                        # e.g. "missing_index", "select_star", "security"
    severity: str                    # "critical" | "high" | "medium" | "low"
    title: str
    evidence: Optional[str] = None
    recommendation: Optional[str] = None

class PlanArtifact(BaseModel):
    format: str                      # "json" | "xml" | "text"
    raw: Any                         # dict for json, str for xml/text

class AnalysisFacts(BaseModel):
    db_type: str
    normalized_query: Optional[str] = None
    redacted_query: Optional[str] = None
    findings: List[Finding] = Field(default_factory=list)
    plan: Optional[PlanArtifact] = None
    warnings: List[str] = Field(default_factory=list)

class OptimizationSuggestion(BaseModel):
    type: str
    severity: str
    suggestion: str
    reason: str
    estimated_improvement: str

class ExecutionPlan(BaseModel):
    plan_type: str
    operations: List[Dict[str, Any]]
    total_cost: Optional[float] = None
    estimated_rows: Optional[int] = None

class QueryAnalysisResult(BaseModel):
    query: str
    parsed_query: Dict[str, Any]
    optimization_suggestions: List[OptimizationSuggestion]
    execution_plan: Optional[ExecutionPlan] = None
    optimized_query: Optional[str] = None
    performance_metrics: Dict[str, Any]
    security_issues: List[str]
    readability_score: float
    analysis_time_ms: float
    facts: Optional[AnalysisFacts] = None
    ai_attempted: bool = False
    used_ai: bool = False
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_insights: Optional[str] = None
    ai_error: Optional[str] = None