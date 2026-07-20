import logging
import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents.sql_analyzer import SQLAnalyzerAgent
from .schemas.models import QueryAnalysisResult, QueryRequest
from .utils.database import get_analysis, save_analysis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="SQL Query Analyzer",
    description="AI-powered SQL query analysis and optimization tool",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize analyzer
analyzer = SQLAnalyzerAgent()

# Simple in-memory rate limiter (use Redis for production)
rate_limit_store = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/analyze":
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old requests (keep last 60 seconds)
        rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < 60]

        # Check limit (10 requests per minute per IP)
        if len(rate_limit_store[client_ip]) >= 10:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in 1 minute.") from None

        rate_limit_store[client_ip].append(now)

    response = await call_next(request)
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "SQL Query Analyzer"}


@app.get("/capabilities")
async def capabilities():
    return {
        "default_provider": os.getenv("DEFAULT_LLM_PROVIDER", "huggingface"),
        "providers": {
            "huggingface": bool(os.getenv("HF_API_KEY", "").strip()),
            "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        },
    }


@app.post("/analyze", response_model=QueryAnalysisResult)
async def analyze_query(request: QueryRequest):
    """
    Analyze SQL query for optimization opportunities

    - Detects performance issues
    - Suggests indexes
    - Provides rewritten optimized query
    - Checks security implications
    """
    try:
        start_time = time.time()

        # Validate query
        if not request.query or len(request.query.strip()) < 5:
            raise HTTPException(status_code=400, detail="Query too short")

        logger.info(f"Analyzing query: {request.query[:50]}...")
        logger.info(
            "Analyze: db=%s use_llm=%s provider=%s focus=%s",
            request.db_type,
            request.use_llm,
            request.llm_provider,
            request.focus,
        )

        # Run analysis
        db_type_str = request.db_type.value if hasattr(request.db_type, "value") else str(request.db_type)
        llm_provider_str = (
            request.llm_provider.value if hasattr(request.llm_provider, "value") else str(request.llm_provider)
        )
        result = await analyzer.analyze(
            query=request.query,
            db_type=db_type_str,
            schema_info=request.schema_info,
            use_llm=request.use_llm,
            llm_provider=llm_provider_str,
            focus=request.focus,
        )

        analysis_time = (time.time() - start_time) * 1000

        response_payload = {
            "query": request.query,
            "parsed_query": result.get("parsing_result", {}),
            "optimization_suggestions": result.get("optimization_suggestions", []),
            "execution_plan": result.get("execution_plan"),
            "optimized_query": result.get("optimized_query"),
            "plain_explanation": result.get("plain_explanation"),
            "performance_metrics": {
                "complexity_score": result.get("parsing_result", {}).get("complexity_score", 0),
                "subqueries": result.get("parsing_result", {}).get("subqueries", 0),
            },
            "security_issues": result.get("security_issues", []),
            "readability_score": result.get("readability_score", 0),
            "analysis_time_ms": analysis_time,
            "facts": result.get("facts"),
            "used_ai": bool(result.get("used_ai", False)),
            "ai_provider": result.get("ai_provider"),
            "ai_model": result.get("ai_model"),
            "ai_insights": result.get("ai_insights"),
            "ai_error": result.get("ai_error"),
            "db_type": db_type_str,
            "original_query": request.query,
            "schema_info": request.schema_info,
        }
        # Persist asynchronously — failure never blocks the response
        analysis_id = await save_analysis(response_payload)

        # Attach the shareable ID (None if Supabase not configured)
        response_payload["analysis_id"] = analysis_id
        response_payload["share_url"] = f"https://querytuner.com/report/{analysis_id}" if analysis_id else None
        response_payload.pop("original_query", None)
        response_payload.pop("db_type", None)

        return QueryAnalysisResult(**response_payload)
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@app.get("/report/{analysis_id}", tags=["Reports"])
async def get_report(analysis_id: str):
    """
    GET /report/{analysis_id}

    Returns a stored analysis by UUID.
    Used by the shareable report page on the frontend.

    Issue #41: Shareable report URL
    """
    if not analysis_id or len(analysis_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    record = await get_analysis(analysis_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found. It may have expired or the link is incorrect.",
        )

    return JSONResponse(
        content={
            "id": record["id"],
            "db_type": record["db_type"],
            "original_query": record["original_query"],
            "optimization_suggestions": record["findings"],
            "severity": record["severity"],
            "optimized_query": record.get("optimized_query"),
            "readability_score": record.get("readability_score"),
            "analysis_time_ms": record.get("analysis_time_ms"),
            "used_ai": record.get("used_ai", False),
            "ai_model": record.get("ai_model"),
            "created_at": record["created_at"],
            "share_url": f"https://querytuner.com/report/{record['id']}",
        }
    )


@app.get("/docs")
async def get_documentation():
    """API documentation"""
    return {
        "title": "SQL Query Analyzer API",
        "version": "1.0.0",
        "endpoints": {
            "POST /analyze": "Analyze SQL query",
            "GET /health": "Health check",
            "GET /docs": "This documentation",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
