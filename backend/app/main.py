from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import os
import time
import logging
from .schemas.models import QueryRequest, QueryAnalysisResult
from .agents.sql_analyzer import SQLAnalyzerAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()  # loads backend/.env when running locally (if present) [web:146]

# Initialize FastAPI
app = FastAPI(
    title="SQL Query Analyzer",
    description="AI-powered SQL query analysis and optimization tool",
    version="1.0.0"
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
        client_ip = request.client.host
        now = time.time()
        
        # Clean old requests (keep last 60 seconds)
        rate_limit_store[client_ip] = [
            t for t in rate_limit_store[client_ip] if now - t < 60
        ]
        
        # Check limit (10 requests per minute per IP)
        if len(rate_limit_store[client_ip]) >= 10:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in 1 minute.")
        
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
        result = await analyzer.analyze(
            query=request.query,
            db_type=request.db_type.value if hasattr(request.db_type, "value") else str(request.db_type),
            schema_info=request.schema_info,
            use_llm=request.use_llm,
            llm_provider=request.llm_provider.value if hasattr(request.llm_provider, "value") else str(request.llm_provider),
            focus=request.focus,
        )
        
        analysis_time = (time.time() - start_time) * 1000
        
        return QueryAnalysisResult(
            query=request.query,
            parsed_query=result.get("parsing_result", {}),
            optimization_suggestions=result.get("optimization_suggestions", []),
            execution_plan=result.get("execution_plan"),
            optimized_query=result.get("optimized_query"),
            performance_metrics={
                "complexity_score": result.get("parsing_result", {}).get("complexity_score", 0),
                "subqueries": result.get("parsing_result", {}).get("subqueries", 0)
            },
            security_issues=result.get("security_issues", []),
            readability_score=result.get("readability_score", 0),
            analysis_time_ms=analysis_time,
            facts=result.get("facts"),
            # NEW: make AI visibly reflected in output
            used_ai=bool(result.get("used_ai", False)),
            ai_provider=result.get("ai_provider"),
            ai_model=result.get("ai_model"),
            ai_insights=result.get("ai_insights"),
            ai_error=result.get("ai_error"),
        )
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/docs")
async def get_documentation():
    """API documentation"""
    return {
        "title": "SQL Query Analyzer API",
        "version": "1.0.0",
        "endpoints": {
            "POST /analyze": "Analyze SQL query",
            "GET /health": "Health check",
            "GET /docs": "This documentation"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)