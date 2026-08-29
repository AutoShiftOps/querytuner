import base64
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import jwt
import sentry_sdk
import stripe
from dotenv import load_dotenv
from jwt import PyJWKClient
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Must run before any local import that triggers Settings instantiation
# (app.utils.config reads env vars at import time via a module-level singleton).
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from .agents.sql_analyzer import SQLAnalyzerAgent  # noqa: E402
from .schemas.models import (  # noqa: E402
    BatchAnalysisRequest,
    BatchAnalysisResult,
    BatchQuerySummary,
    LLMProvider,
    QueryAnalysisResult,
    QueryRequest,
)
from .tools.batch_parsers import parse_batch_export, rank_top_n  # noqa: E402
from .tools.batch_reconciler import reconcile_index_suggestions  # noqa: E402
from .tools.index_recommender import IndexRecommender  # noqa: E402
from .tools.query_parser import QueryParser, parse_schema_ddl  # noqa: E402
from .utils.config import settings  # noqa: E402
from .utils.database import (  # noqa: E402
    check_database_health,
    expire_analysis,
    get_analysis,
    get_analysis_history,
    get_user_stripe_customer_id,
    get_user_usage,
    increment_user_usage,
    link_stripe_customer,
    save_analysis,
    update_user_pro_status,
)

FREE_TIER_MONTHLY_LIMIT = 10
# Phase 5 (backlog #54): GET /history pagination bounds.
HISTORY_PAGE_SIZE_DEFAULT = 20
HISTORY_PAGE_SIZE_MAX = 100

# stripe.Webhook.construct_event() (used below) is local signature
# verification and doesn't need this, but every other stripe.* call — like
# billing_portal.Session.create() in POST /billing-portal — is a real
# authenticated API call and does. Nothing in this codebase set this before
# now: the existing checkout flow goes through a pre-made Stripe Payment
# Link URL the frontend links to directly, so the backend never had to
# authenticate to Stripe's API until this.
stripe.api_key = settings.stripe_secret_key

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Phase 5 (#135): error tracking. A blank SENTRY_DSN makes this a complete
# no-op — sentry_sdk.init() is simply never called, and every sentry_sdk.*
# call used elsewhere in this file (set_tag, capture_exception via the
# logging integration) is a documented no-op without an active client. Same
# degrades-gracefully pattern as every other optional integration in this
# codebase (HF_API_KEY, OPENAI_API_KEY, the Stripe keys) — local dev and any
# deploy that hasn't set the env var yet keep working exactly as before.
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[FastApiIntegration()],
        # Light APM sampling, not full tracing — keeps a free-tier Sentry
        # project's event quota mostly for what actually matters: errors.
        traces_sample_rate=0.1,
        # Query text (even client-sanitized) and request bodies are not
        # something to hand to a third party by default — this app already
        # goes out of its way client-side (QueryInput.jsx's sanitizer) to
        # keep real schema names off the backend. Sentry's default PII
        # capture would undo that if left enabled.
        send_default_pii=False,
    )
    logger.info("Sentry error tracking initialized (environment=%s)", settings.environment)
else:
    logger.info("SENTRY_DSN not set — error tracking disabled")

# Initialize FastAPI
app = FastAPI(
    title="SQL Query Analyzer",
    description="AI-powered SQL query analysis and optimization tool",
    version="1.0.0",
)

# Hotfix (regression in the original CORS-allowlist fix): querytuner.com
# 307-redirects to www.querytuner.com at the DNS/Vercel level — confirmed
# live via curl — so the browser's real Origin header on every API call
# from the deployed site is "https://www.querytuner.com", not the bare
# "https://querytuner.com" settings.frontend_url defaults to. The
# allowlist below only had the bare domain, so every real visitor was
# silently CORS-blocked on /capabilities, /usage, and /analyze itself —
# the request succeeded server-side (confirmed via curl: 200 OK, no ACAO
# header) but the browser refused to let the frontend's JS read the
# response. Both the bare domain and the www subdomain are allowed
# explicitly now, in addition to whatever FRONTEND_URL is actually set
# to, so this survives either DNS pointing the redirect could take.
_frontend_origin = settings.frontend_url.rstrip("/")
_cors_allow_origins = list(
    dict.fromkeys(
        [
            _frontend_origin,
            "https://querytuner.com",
            "https://www.querytuner.com",
            "http://localhost:3000",
        ]
    )
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    # Real allowlist, not "*" — settings.frontend_url already exists
    # (used by the Stripe Billing Portal return_url) and already defaults
    # to production while being overridable via FRONTEND_URL for local
    # dev, so reusing it here needs no new env var. localhost:3000 is
    # additionally always allowed (matches frontend/vite.config.js's dev
    # server port) so local development against a deployed backend still
    # works without setting FRONTEND_URL.
    allow_origins=_cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize analyzer
analyzer = SQLAnalyzerAgent()

# Phase 5 (#115/#120): batch workload analysis — reuses the existing
# QueryParser/IndexRecommender instances rather than running the full
# SQLAnalyzerAgent (LLM, security checks, plain-English explanation, ...)
# per query in a batch. The design doc scopes #115/#120 specifically to
# index reconciliation, not full single-query analysis output, and
# running the full heuristic engine against a potentially large export is
# exactly the scaling concern the doc's own item 4 flags — this keeps
# batch analysis to the one thing it's actually for.
_batch_query_parser = QueryParser()
_batch_index_recommender = IndexRecommender()

# A batch's export format implies its dialect — each of the three named
# sources is tied to exactly one database, so there's nothing for the
# caller to get inconsistent by specifying both separately.
_BATCH_SOURCE_DB_TYPE = {
    "query_store": "sqlserver",
    "pg_stat_statements": "postgresql",
    "performance_schema": "mysql",
}

# Simple in-memory rate limiter (use Redis for production)
rate_limit_store = defaultdict(list)

# Anonymous-usage daily cap — separate from rate_limit_store above, which is
# a per-minute anti-burst-abuse throttle applied to every caller regardless
# of auth. Before this, unauthenticated callers had genuinely no usage limit
# at all: the per-minute guard doesn't cap total usage, and only signed-in
# free users were capped (FREE_TIER_MONTHLY_LIMIT/month, enforced further
# down). Same in-memory sliding-window approach as rate_limit_store — this
# app has no rate-limiting library dependency (no slowapi, fastapi-limiter,
# redis-backed limiter, ...), so extending the existing idiom keeps one
# pattern in the codebase instead of introducing a second one for what's
# structurally the same problem.
anonymous_daily_store: dict[str, list[float]] = defaultdict(list)
ANONYMOUS_DAILY_LIMIT = 5
_ONE_DAY_SECONDS = 24 * 60 * 60


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
            # NOT `raise HTTPException(...)` — exceptions raised inside an
            # @app.middleware("http") function are not routed through
            # FastAPI's normal exception handlers (that machinery only
            # wraps route handlers), so a raised HTTPException here always
            # propagated uncaught and surfaced to the client as a generic
            # 500, never the intended 429. Returning a JSONResponse
            # directly is the correct way to short-circuit from middleware.
            # Shape matches the anonymous-limit 429 elsewhere in this file
            # ({error, message, ...}) for one consistent 429 shape.
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded. Try again in 1 minute.",
                },
            )

        rate_limit_store[client_ip].append(now)

    response = await call_next(request)
    return response


# Phase 5 (#135): correlation IDs for request tracing. Added after
# rate_limit_middleware above — FastAPI/Starlette wraps middleware so the
# LAST one added ends up OUTERMOST, meaning this one sees every request
# first (assigns the ID before rate-limiting even runs) and touches every
# response last (so even a 429 short-circuited by rate_limit_middleware
# still carries the header). Reuses an incoming X-Request-ID if the caller
# already set one (lets a frontend or upstream proxy's own ID flow through
# end to end) rather than always minting a fresh one.
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    if settings.sentry_dsn:
        sentry_sdk.set_tag("request_id", request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint — point an uptime monitor (#135) here.

    Deliberately still returns 200 and "status": "healthy" even when the
    database check below fails: the heuristic engine (the actual product)
    keeps working with Supabase fully down, per every database.py call's
    own try/except fallback. Paging on-call for a persistence blip as if
    the whole service were down would be a false alarm — checks.database
    surfaces the real state for a human without flipping the overall
    liveness signal an uptime monitor pages on.
    """
    db_ok = await check_database_health()
    return {
        "status": "healthy",
        "service": "SQL Query Analyzer",
        "checks": {"database": "ok" if db_ok else "unreachable"},
    }


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
async def analyze_query(request: QueryRequest, http_request: Request, user_id: str | None = Depends(get_current_user)):
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

        # Phase 4: resolve tier once — drives both the per-query character
        # limit below and the monthly analysis-count limit further down.
        # user_id comes from a verified JWT (get_current_user), so this is
        # the check that actually matters — the frontend's canAnalyze() is
        # only an honour-system UX nicety anyone could bypass by calling
        # this endpoint directly.
        usage_month = datetime.now(UTC).strftime("%Y-%m")
        usage = None
        is_pro = False
        if user_id:
            usage = await get_user_usage(user_id, usage_month)
            is_pro = bool(usage.get("is_pro", False))

        # Anonymous callers: AI insights require signing in (the OpenAI-backed
        # path costs real money per call — heuristic-only analysis is free to
        # run and stays open), and a daily cap replaces what was previously no
        # limit at all. Structured JSON body (not a bare 401) so the frontend
        # can render an actionable prompt instead of a generic auth error.
        if not user_id:
            if request.use_llm:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "sign_in_required",
                        "message": ("Sign in to use AI insights. Heuristic analysis is available without an account."),
                        "sign_in_required": True,
                    },
                )

            client_ip = http_request.client.host if http_request.client else "unknown"
            now = time.time()
            anonymous_daily_store[client_ip] = [
                t for t in anonymous_daily_store[client_ip] if now - t < _ONE_DAY_SECONDS
            ]
            if len(anonymous_daily_store[client_ip]) >= ANONYMOUS_DAILY_LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "anonymous_limit_reached",
                        "message": (
                            f"Free anonymous limit reached ({ANONYMOUS_DAILY_LIMIT}/day). "
                            "Sign in for 10 free analyses/month, or upgrade to Pro for unlimited."
                        ),
                        "sign_in_available": True,
                    },
                )
            anonymous_daily_store[client_ip].append(now)

        # Tier-based query size limit. Checked here (not just inside
        # analyzer.analyze()) so an oversized query returns a clean 400 with
        # actionable detail instead of bubbling up as a ValueError that the
        # broad except below turns into an opaque 500 — this was the actual
        # cause of the production 500s (Render logs: "Analysis error: Query
        # too large (>20000 chars)"). Free/anonymous users get a smaller
        # ceiling than Pro — not just anti-abuse, this doubles as the
        # upgrade prompt itself (upgrade_available, read by the frontend to
        # show UpgradeModal instead of a generic error toast).
        max_chars = settings.max_query_chars if is_pro else settings.free_tier_max_query_chars
        if len(request.query) > max_chars:
            logger.warning(
                "Query too large: %d chars (max %d, is_pro=%s)",
                len(request.query),
                max_chars,
                is_pro,
            )
            message = (
                f"Query exceeds maximum length of {max_chars:,} characters. "
                "For very large queries, try analyzing the slowest subquery or CTE separately."
                if is_pro
                else (
                    f"Query too large for free tier (>{max_chars:,} chars). "
                    f"Upgrade to QueryTuner Pro for queries up to {settings.max_query_chars:,} characters."
                )
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": "query_too_large",
                    "message": message,
                    "query_length": len(request.query),
                    "max_length": max_chars,
                    "is_pro": is_pro,
                    "upgrade_available": not is_pro,
                },
            )

        # Phase 4: server-side monthly free-tier enforcement — separate from
        # the per-query size limit above (that caps how big one query can
        # be; this caps how many analyses per month).
        if user_id and not is_pro and usage["count"] >= FREE_TIER_MONTHLY_LIMIT:
            raise HTTPException(
                status_code=402,
                detail="Free tier limit reached — upgrade to Pro for unlimited analyses",
            )

        # Phase 4 audit (#53) fix: OpenAI (GPT-4o-mini) is a Pro-tier
        # feature by design — free tier stays on Hugging Face. Before this
        # check existed, request.llm_provider was read straight off the
        # client request body and passed to analyzer.analyze() with
        # nothing checking it against is_pro anywhere in the call path:
        # any signed-in free user could select "openai" in the dropdown
        # and the backend would honor it, running real GPT-4o-mini calls
        # on Pro's cost budget. QueryInput.jsx's dropdown now also hides
        # this option from non-Pro users client-side, but that's UX only —
        # this server-side check is the one that's authoritative, same
        # relationship the sign-in-required gate above already has with
        # its own frontend-side checkbox-disabling.
        if request.use_llm and request.llm_provider == LLMProvider.OPENAI and not is_pro:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "pro_required",
                    "message": (
                        "OpenAI (GPT-4o-mini) AI insights are a Pro feature. "
                        "Upgrade to QueryTuner Pro, or switch to Hugging Face for free AI insights."
                    ),
                    "upgrade_available": True,
                },
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
            "ai_truncated": bool(result.get("ai_truncated", False)),
            "db_type": db_type_str,
            "original_query": request.query,
            "schema_info": request.schema_info,
            "user_id": user_id,  # Phase 4: None for anonymous/unauthenticated requests
            "was_sanitized": request.was_sanitized,  # Issue #124: self-reported, see QueryRequest's own docstring
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
        response_payload.pop("was_sanitized", None)

        return QueryAnalysisResult(**response_payload)
    except HTTPException:
        # Let intentional client errors (400 query-too-short/too-large, 429
        # rate limit, 402 free-tier limit, ...) through as-is — confirmed by
        # testing that the bare `except Exception` below was flattening
        # these to 500 too, the same bug class as the reported
        # query_too_large incident.
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


@app.get("/history")
async def get_history(
    user_id: str | None = Depends(get_current_user),
    limit: int = HISTORY_PAGE_SIZE_DEFAULT,
    offset: int = 0,
    sanitized: bool = False,
):
    """
    GET /history — Phase 5 (backlog #54): a Pro-only, paginated list of the
    signed-in user's past analyses. UpgradeModal.jsx has advertised "Query
    history" as a Pro perk since Phase 4; this is what actually backs it.

    Gates the *data*, not just the UI — mirrors /analyze's own is_pro check
    (via get_user_usage) rather than trusting the frontend to only call
    this for Pro users:
      - not signed in -> 401 sign_in_required
      - signed in but not Pro -> 403 pro_required
      - signed in and Pro -> the actual paginated history

    Both rejection cases use the same structured {error, message, ...}
    body shape as /analyze's other structured errors (query_too_large,
    sign_in_required, anonymous_limit_reached) rather than FastAPI's
    default {"detail": ...} shape, so the frontend can render an actionable
    prompt (sign in / upgrade) instead of a generic error.

    sanitized=true (Issue #124): filters to only analyses the client
    reported as sanitized (QueryRequest.was_sanitized) — filtered
    server-side (get_analysis_history's own job) so pagination stays
    correct against the filtered set.
    """
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "sign_in_required",
                "message": "Sign in to view your query history.",
                "sign_in_required": True,
            },
        )

    usage_month = datetime.now(UTC).strftime("%Y-%m")
    usage = await get_user_usage(user_id, usage_month)
    if not usage.get("is_pro", False):
        return JSONResponse(
            status_code=403,
            content={
                "error": "pro_required",
                "message": "Query history is a Pro feature. Upgrade to QueryTuner Pro to see your saved analyses.",
                "upgrade_available": True,
            },
        )

    limit = max(1, min(limit, HISTORY_PAGE_SIZE_MAX))
    offset = max(0, offset)

    items = await get_analysis_history(user_id, limit=limit, offset=offset, sanitized_only=sanitized)
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        # Simple v1 pagination signal per the design doc — a full page back
        # means there might be more, not a guarantee (would need a separate
        # COUNT query to know for certain). Good enough for a "Load more"
        # button; not attempting cursor-based pagination yet.
        "has_more": len(items) == limit,
    }


@app.post("/analyze/batch", response_model=BatchAnalysisResult)
async def analyze_batch(request: BatchAnalysisRequest, user_id: str | None = Depends(get_current_user)):
    """
    POST /analyze/batch — Phase 5 (#115/#120): accepts a pasted production
    workload export (SQL Server Query Store / PostgreSQL
    pg_stat_statements / MySQL performance_schema — see
    docs/querytuner-batch-analysis-issue.md) and returns per-query index
    suggestions plus a reconciled, cross-query index recommendation set
    (#115) — collapsing suggestions that are redundant once a wider
    composite exists on the same table, and flagging (not silently
    resolving) suggestions that disagree on column order — instead of N
    independent single-query results concatenated together.

    A separate endpoint from POST /analyze rather than a `queries: list`
    variant of it, per the design doc's own recommendation — this has a
    genuinely different request/response shape and gating (Pro-only, one
    export instead of one query) that would otherwise complicate
    /analyze's existing single-query contract.

    Pro-only — mirrors GET /history's gating pattern exactly:
      - not signed in -> 401 sign_in_required
      - signed in but not Pro -> 403 pro_required
      - signed in and Pro -> the actual batch analysis
    Product decision made explicitly (not guessed at, per the design
    doc's own flag that this was still open): batch/reconciliation is a
    heavier analysis workload than a single /analyze call, closer to the
    existing Pro-gated features (query history, PDF export) than to core
    single-query analysis.
    """
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "sign_in_required",
                "message": "Sign in to use batch workload analysis.",
                "sign_in_required": True,
            },
        )

    usage_month = datetime.now(UTC).strftime("%Y-%m")
    usage = await get_user_usage(user_id, usage_month)
    if not usage.get("is_pro", False):
        return JSONResponse(
            status_code=403,
            content={
                "error": "pro_required",
                "message": (
                    "Batch workload analysis is a Pro feature. "
                    "Upgrade to QueryTuner Pro to analyze production query exports."
                ),
                "upgrade_available": True,
            },
        )

    start_time = time.time()

    if not request.export_text or not request.export_text.strip():
        raise HTTPException(status_code=400, detail="export_text is empty")

    source = request.source.value
    entries = parse_batch_export(source, request.export_text)
    if not entries:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not parse any queries from the pasted {source} export — "
                "check it matches a standard export for this source "
                "(see the endpoint's own docstring for an example query)."
            ),
        )

    ranked = rank_top_n(entries, request.top_n)
    db_type = _BATCH_SOURCE_DB_TYPE[source]
    schema = parse_schema_ddl(request.schema_info) if request.schema_info else {}

    query_summaries: list[BatchQuerySummary] = []
    per_query_suggestions: list[tuple[int, list[dict]]] = []
    for idx, entry in enumerate(ranked):
        parsed = _batch_query_parser.parse(entry.query_text)
        suggestions = _batch_index_recommender.recommend(
            query=entry.query_text,
            parsed=parsed,
            db_type=db_type,
            schema_info=request.schema_info,
        )
        per_query_suggestions.append((idx, suggestions))
        query_summaries.append(
            BatchQuerySummary(
                index=idx,
                query=entry.query_text,
                calls=entry.calls,
                total_time_ms=entry.total_time_ms,
                index_suggestions=suggestions,
            )
        )

    reconciliation = reconcile_index_suggestions(per_query_suggestions, schema)
    analysis_time = (time.time() - start_time) * 1000

    return BatchAnalysisResult(
        source=request.source,
        db_type=db_type,
        total_parsed=len(entries),
        analyzed_count=len(ranked),
        queries=query_summaries,
        reconciled_index_suggestions=[
            {**r.suggestion, "table": r.table, "satisfies_queries": r.satisfies_queries}
            for r in reconciliation.reconciled_suggestions
        ],
        dropped_suggestions=[
            {
                "table": d.table,
                "columns": d.columns,
                "suggestion": d.suggestion_text,
                "source_query_indices": d.source_query_indices,
                "reason": d.reason,
                "superseded_by_columns": d.superseded_by_columns,
            }
            for d in reconciliation.dropped_suggestions
        ],
        column_order_conflicts=[
            {"table": c.table, "columns": c.columns, "variants": c.variants}
            for c in reconciliation.column_order_conflicts
        ],
        warnings=reconciliation.warnings,
        analysis_time_ms=analysis_time,
    )


@app.post("/billing-portal")
async def create_billing_portal_session(user_id: str | None = Depends(get_current_user)):
    """
    Creates a Stripe Billing Portal session so a Pro user can manage their
    own subscription (payment method, cancel, invoices) — deliberately no
    custom billing UI in this app; Stripe's hosted portal handles all of
    that. Auth-required: unlike /analyze, there's no useful anonymous path
    here (no subscription to manage without being signed in).
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")

    customer_id = await get_user_stripe_customer_id(user_id)
    if not customer_id:
        # Shouldn't normally happen if the frontend only shows "Manage
        # subscription" to is_pro users, but is_pro and stripe_customer_id
        # are tracked independently (see get_user_stripe_customer_id's
        # docstring) — a clear 400 here instead of letting a bare
        # stripe.billing_portal.Session.create(customer=None) call surface
        # a confusing Stripe API error to the frontend.
        raise HTTPException(status_code=400, detail="No active subscription found for this account")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=settings.frontend_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create billing portal session for user %s: %s", user_id, exc)
        raise HTTPException(status_code=502, detail="Could not open billing portal — try again shortly") from None

    return {"url": session.url}


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook — keeps user_accounts.is_pro (migration 007) in sync
    with subscription status, and links a Clerk user_id to its Stripe
    customer_id the moment checkout completes (checkout.session.completed
    carries both, via the client_reference_id the Upgrade modal's payment
    link is set up to pass). Without that link, later customer.subscription.*
    events would only have a customer_id to go on and could never find
    which user to update.
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
    # event["data"]["object"] is a stripe.StripeObject, not a plain dict —
    # it supports __getitem__ (event["type"] above works) but NOT .get():
    # `.get` isn't a real attribute or key, so StripeObject.__getattr__
    # falls through to self["get"], which raises KeyError, re-raised as
    # AttributeError: get. Every .get(...) call below crashed with exactly
    # that, uncaught, for every real webhook delivery — 500 on both
    # checkout.session.completed and customer.subscription.created/updated.
    # Reproduced locally by sending a correctly-signed synthetic event
    # through this exact handler before writing this fix. .to_dict() is
    # StripeObject's own documented conversion, so .get() works as expected
    # from here on.
    data = event["data"]["object"].to_dict()

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            await link_stripe_customer(user_id, customer_id)
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
            "was_sanitized": bool(record.get("was_sanitized", False)),  # Issue #124
        }
    )


@app.delete("/report/{analysis_id}", tags=["Reports"])
async def delete_report(analysis_id: str, user_id: str | None = Depends(get_current_user)):
    """
    DELETE /report/{analysis_id} — Phase 5 (backlog #116): lets a
    signed-in user revoke their own shared report link early, rather than
    waiting out the default expiration window (see
    database.py's ANALYSIS_EXPIRATION_DAYS). Soft-delete — see
    expire_analysis()'s docstring for why this isn't a hard DELETE.

    Anonymous-authored analyses (user_id IS NULL) have no owner to
    authorize a delete against, so there's nothing for anyone to delete
    via this endpoint for those in v1 — expiration is the only mechanism
    that applies to them, same as the design doc's explicit scope.
    """
    if not analysis_id or len(analysis_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")

    deleted = await expire_analysis(analysis_id, user_id)
    if not deleted:
        # Same shape as GET /report/{id}'s 404 — deliberately doesn't
        # distinguish "doesn't exist" from "exists but isn't yours" from
        # "already expired", for the same reason get_analysis() doesn't:
        # not leaking which of those is actually true.
        raise HTTPException(
            status_code=404,
            detail="Analysis not found. It may have expired, already been deleted, or isn't owned by this account.",
        )
    return {"status": "deleted"}


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
