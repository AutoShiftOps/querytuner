import base64
import logging
import os
import time
from collections import defaultdict
from datetime import UTC, datetime

import jwt
import stripe
from dotenv import load_dotenv
from jwt import PyJWKClient

# Must run before any local import that triggers Settings instantiation
# (app.utils.config reads env vars at import time via a module-level singleton).
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from .agents.sql_analyzer import SQLAnalyzerAgent  # noqa: E402
from .schemas.models import QueryAnalysisResult, QueryRequest  # noqa: E402
from .utils.config import settings  # noqa: E402
from .utils.database import (  # noqa: E402
    get_analysis,
    get_user_usage,
    increment_user_usage,
    link_stripe_customer,
    save_analysis,
    update_user_pro_status,
)

FREE_TIER_MONTHLY_LIMIT = 10

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


# -----------------------------------------------------------------------------
# Phase 4: Clerk auth
#
# IMPORTANT: this verifies the JWT signature against Clerk's own JWKS before
# trusting anything in the token — earlier drafts of this feature used
# jwt.decode(token, options={"verify_signature": False}), which accepts ANY
# token with ANY `sub` claim and would let a caller impersonate an arbitrary
# user_id (fake Pro status, forge another user's usage counter, etc). Do not
# reintroduce that pattern.
#
# The Clerk JWKS URL is derived from the publishable key (not a secret —
# it's the same value shipped to the browser as VITE_CLERK_PUBLISHABLE_KEY),
# which Clerk itself base64-encodes the Frontend API domain into. This is
# the same derivation Clerk's own SDKs perform.
# -----------------------------------------------------------------------------

_jwks_client: PyJWKClient | None = None


def _clerk_jwks_url() -> str | None:
    pk = settings.clerk_publishable_key
    if not pk or "_" not in pk:
        return None
    try:
        b64_part = pk.split("_", 2)[2]
        padded = b64_part + "=" * (-len(b64_part) % 4)
        domain = base64.b64decode(padded).decode().rstrip("$")
        if not domain:
            return None
        return f"https://{domain}/.well-known/jwks.json"
    except Exception:  # noqa: BLE001
        return None


async def get_current_user(request: Request) -> str | None:
    """
    Extract and verify a Clerk session JWT from the Authorization header.

    Returns the Clerk user_id (JWT `sub` claim) once the token's signature,
    issuer-derived key, and expiry have all checked out — or None for any
    unauthenticated / invalid / expired request. Never trusts token contents
    without verifying the signature first.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    jwks_url = _clerk_jwks_url()
    if not jwks_url:
        logger.warning("CLERK_PUBLISHABLE_KEY not configured — cannot verify auth tokens")
        return None

    try:
        global _jwks_client
        if _jwks_client is None:
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(token, signing_key.key, algorithms=["RS256"])
        return decoded.get("sub")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Clerk token verification failed: %s", exc)
        return None


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
async def analyze_query(request: QueryRequest, user_id: str | None = Depends(get_current_user)):
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

        # Phase 4: server-side free-tier enforcement. The frontend already
        # gates this client-side (canAnalyze() in App.jsx), but that's an
        # honour system anyone could bypass by calling this endpoint
        # directly — user_id here comes from a verified JWT, so this is the
        # check that actually matters. Anonymous requests (user_id is None)
        # are unaffected, same as the frontend's honour-system comment says.
        usage_month = datetime.now(UTC).strftime("%Y-%m")
        if user_id:
            usage = await get_user_usage(user_id, usage_month)
            if not usage["is_pro"] and usage["count"] >= FREE_TIER_MONTHLY_LIMIT:
                raise HTTPException(
                    status_code=402,
                    detail="Free tier limit reached — upgrade to Pro for unlimited analyses",
                )

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
            "user_id": user_id,  # Phase 4: None for anonymous/unauthenticated requests
        }
        # Persist asynchronously — failure never blocks the response
        analysis_id = await save_analysis(response_payload)

        # Phase 4: count this analysis against the user's free-tier limit.
        # Pro users still get counted (harmless — the limit check above
        # already exempts is_pro) so the number stays meaningful if they
        # ever downgrade.
        if user_id:
            await increment_user_usage(user_id, usage_month)

        # Attach the shareable ID (None if Supabase not configured)
        response_payload["analysis_id"] = analysis_id
        response_payload["share_url"] = f"https://querytuner.com/report/{analysis_id}" if analysis_id else None
        response_payload.pop("original_query", None)
        response_payload.pop("db_type", None)
        # Not part of the response schema — only needed above for persistence.
        response_payload.pop("user_id", None)

        return QueryAnalysisResult(**response_payload)
    except HTTPException:
        # Let intentional client errors (400 query-too-short, 429 rate limit,
        # 402 free-tier limit, ...) through as-is — the bare `except
        # Exception` below is only for genuinely unexpected failures, and
        # would otherwise flatten every deliberate status code to 500.
        raise
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@app.get("/usage")
async def get_usage(user_id: str | None = Depends(get_current_user)):
    """
    GET /usage — the authoritative monthly analysis count + Pro status for
    the signed-in user, backing the free-tier limit in the frontend (which
    otherwise only has a client-side counter that resets on page refresh).

    Anonymous/unauthenticated requests get the default free-tier shape back
    rather than a 401 — there's nothing to enforce against yet for them.
    """
    if not user_id:
        return {"count": 0, "is_pro": False, "limit": 10}

    month = datetime.now(UTC).strftime("%Y-%m")
    return await get_user_usage(user_id, month)


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook — keeps user_usage.is_pro in sync with subscription
    status, and links a Clerk user_id to its Stripe customer_id the moment
    checkout completes (checkout.session.completed carries both, via the
    client_reference_id the Upgrade modal's payment link is set up to pass).
    Without that link, later customer.subscription.* events would only have
    a customer_id to go on and could never find which user to update.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not settings.stripe_webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=400, detail="Webhook not configured") from None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from None

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            month = datetime.now(UTC).strftime("%Y-%m")
            await link_stripe_customer(user_id, customer_id, month)
        else:
            logger.warning(
                "checkout.session.completed missing client_reference_id or customer — "
                "cannot link user to Stripe customer"
            )

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id = data.get("customer")
        is_pro = data.get("status") == "active"
        if customer_id:
            await update_user_pro_status(customer_id, is_pro)

    return {"status": "ok"}


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
            "security_issues": record.get("security_issues") or [],
            "severity": record["severity"],
            "optimized_query": record.get("optimized_query"),
            "plain_explanation": record.get("plain_explanation"),
            "readability_score": record.get("readability_score"),
            "analysis_time_ms": record.get("analysis_time_ms"),
            "used_ai": record.get("used_ai", False),
            "ai_model": record.get("ai_model"),
            "ai_insights": record.get("ai_insights"),
            "ai_provider": record.get("ai_provider"),
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
