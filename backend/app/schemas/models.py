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
    # Issue #60: EXPLAIN plan paste-in — was missing, silently dropped by FastAPI
    explain_plan: str | None = Field(
        None, description="Raw EXPLAIN plan output pasted by user (dialect-specific format)"
    )
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
    # Issue #72: dialect-aware DDL fields — optional so existing suggestions
    # without them (e.g. from index_recommender before Phase 1.7) still validate
    ddl_hint: str | None = None
    ddl_note: str | None = None
    columns: list[str] | None = None
    schema_verified: bool | None = None
    rollback_ddl: str | None = None
    # Human-facing evidence tier — schema_verified remains the underlying
    # boolean used for schema cross-reference logic; this is the label.
    # Values: "deterministic" | "schema-verified" | "needs-runtime-evidence"
    evidence_level: str | None = None
    # Issue #118: the write/storage-cost counterpart to estimated_improvement
    # (which only ever states the read-side benefit). Same free-text pattern
    # deliberately, not a structured numeric model — there's no live DB/row-count
    # access to back a byte-precise estimate with. None for non-index
    # suggestion types, which don't carry a write/storage cost of their own.
    cost_estimate: str | None = None
    # Issue #63: confirmed against a REAL EXPLAIN plan (not just pasted
    # schema DDL). Kept separate from schema_verified — that field's name
    # specifically means "cross-referenced against schema DDL," and this
    # doesn't touch it, to avoid two different verification sources
    # silently sharing one boolean. evidence_level is still set to
    # "schema-verified" either way (same tier, reused per the design
    # doc's explicit recommendation — that's the literal word
    # QueryInput.jsx's UI copy already promises); plan_verified is the
    # detail of *which* source did the confirming.
    plan_verified: bool | None = None
    # Issue #63: the real plan shows an index already being used on this
    # exact column — this suggestion (which assumes the column is
    # unindexed) is likely wrong: stale heuristic, or schema drift since
    # the suggestion's column-extraction ran. Surfaced explicitly rather
    # than silently upgrading evidence, so a wrong suggestion doesn't ship
    # with false confidence.
    plan_contradicts: bool | None = None


class ExecutionPlan(BaseModel):
    plan_type: str
    operations: list[dict[str, Any]]
    total_cost: float | None = None
    estimated_rows: int | None = None


class BatchSource(StrEnum):
    """Phase 5 (#115/#120): the three production-workload export formats
    POST /analyze/batch accepts — an explicit selector, not auto-detected
    from pasted content, same reasoning #61/#62's gap-followup gives for
    not auto-detecting EXPLAIN dialect (overlapping column-naming
    conventions across sources make a wrong guess a real correctness
    risk, not just an inconvenience)."""

    QUERY_STORE = "query_store"
    PG_STAT_STATEMENTS = "pg_stat_statements"
    PERFORMANCE_SCHEMA = "performance_schema"


class BatchAnalysisRequest(BaseModel):
    source: BatchSource
    export_text: str = Field(..., description="Pasted export from the chosen production source")
    schema_info: str | None = Field(None, description="Schema DDL — improves both per-query and reconciled results")
    top_n: int = Field(default=20, ge=1, le=100, description="Analyze only the top-N by total time — not every row")


class BatchQuerySummary(BaseModel):
    index: int
    query: str
    calls: int | None = None
    total_time_ms: float | None = None
    index_suggestions: list[OptimizationSuggestion] = Field(default_factory=list)


class ReconciledIndexSuggestion(OptimizationSuggestion):
    table: str | None = None
    # Indices into BatchAnalysisResult.queries — which original queries
    # this one reconciled suggestion covers, including ones that only
    # asked for a narrower subset now subsumed by this entry.
    satisfies_queries: list[int] = Field(default_factory=list)


class DroppedIndexSuggestion(BaseModel):
    table: str | None = None
    columns: list[str]
    suggestion: str
    source_query_indices: list[int]
    reason: str
    superseded_by_columns: list[str]


class ColumnOrderConflictVariant(BaseModel):
    order: list[str]
    queries: list[int]


class ColumnOrderConflict(BaseModel):
    table: str | None = None
    columns: list[str]
    variants: list[ColumnOrderConflictVariant]


class BatchAnalysisResult(BaseModel):
    source: BatchSource
    db_type: str
    total_parsed: int
    analyzed_count: int
    queries: list[BatchQuerySummary]
    reconciled_index_suggestions: list[ReconciledIndexSuggestion]
    dropped_suggestions: list[DroppedIndexSuggestion]
    column_order_conflicts: list[ColumnOrderConflict]
    warnings: list[str] = Field(default_factory=list)
    analysis_time_ms: float


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
    ai_truncated: bool = False
    analysis_id: str | None = None
    share_url: str | None = None
