import hashlib
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _supabase_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _supabase_headers() -> dict[str, str]:
    # service_role, not anon — RLS is enabled on both analyses and
    # user_usage, and service_role is the only key that bypasses it without
    # requiring custom policies. This used to be the anon key, which only
    # appeared to work because analyses had RLS disabled; user_usage always
    # had RLS enabled and every POST/PATCH here 401'd (GET happened to
    # succeed — RLS's default deny-all still allows reads under some
    # configurations, but never writes). Never send this key to the
    # frontend — it's backend-only, on purpose.
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",  # returns the inserted row
    }


def hash_query(query: str) -> str:
    """Stable SHA-256 hash of the normalized query text."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# Columns added after the initial schema (001) — a given Supabase project may
# not have run the corresponding migration yet. Retried one at a time below
# rather than losing the whole analysis record (PGRST204: unknown column).
_OPTIONAL_COLUMNS = ("plain_explanation", "ai_insights", "ai_provider", "security_issues", "user_id")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _insert_with_fallback(row: dict[str, Any]) -> list[dict[str, Any]] | None:
    """
    POST row to Supabase, stripping one missing optional column at a time
    and retrying if PostgREST rejects the insert because that column hasn't
    been migrated in yet on this project.
    """
    for _ in range(len(_OPTIONAL_COLUMNS) + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{settings.supabase_url}/rest/v1/analyses",
                    headers=_supabase_headers(),
                    json=row,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            missing = next((c for c in _OPTIONAL_COLUMNS if c in row and c in exc.response.text), None)
            if not missing:
                logger.warning("Failed to save analysis to Supabase: %s", exc)
                return None
            logger.warning("%s column not found in Supabase — retrying without it", missing)
            row.pop(missing, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save analysis to Supabase: %s", exc)
            return None
    return None


async def save_analysis(payload: dict[str, Any]) -> str | None:
    """
    Persist a completed analysis to Supabase.
    Returns the UUID of the inserted row, or None on failure.
    Failures are logged but never raised — analysis results still returned to user.
    """
    if not _supabase_configured():
        logger.debug("Supabase not configured — skipping persistence")
        return None

    row = {
        "query_hash": hash_query(payload.get("original_query", "")),
        "db_type": payload.get("db_type", "unknown"),
        "original_query": payload.get("original_query", ""),
        "findings": payload.get("optimization_suggestions", []),
        "severity": _top_severity(payload.get("optimization_suggestions", [])),
        "optimized_query": payload.get("optimized_query"),
        "readability_score": payload.get("readability_score"),
        "analysis_time_ms": payload.get("analysis_time_ms"),
        "used_ai": payload.get("used_ai", False),
        "ai_model": payload.get("ai_model"),
        "schema_info": payload.get("schema_info") or None,
        "plain_explanation": payload.get("plain_explanation"),
        "ai_insights": payload.get("ai_insights") or None,
        "ai_provider": payload.get("ai_provider") or None,
        "security_issues": payload.get("security_issues") or [],
        "user_id": payload.get("user_id") or None,
    }

    data = await _insert_with_fallback(row)
    if not data:
        return None

    inserted_id = data[0]["id"] if data else None
    logger.info("Analysis saved: id=%s hash=%s", inserted_id, row["query_hash"])
    return inserted_id


async def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    """
    Retrieve a stored analysis by UUID.
    Returns None if not found or Supabase is not configured.
    """
    if not _supabase_configured():
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/analyses",
                headers=_supabase_headers(),
                params={"id": f"eq.{analysis_id}", "select": "*", "limit": "1"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch analysis %s: %s", analysis_id, exc)
        return None


# ---------------------------------------------------------------------------
# Phase 4: user usage / Stripe billing status
# ---------------------------------------------------------------------------


async def get_user_usage(user_id: str, month: str) -> dict[str, Any]:
    """
    Look up a user's analysis count and Pro status for a given 'YYYY-MM'
    month. Returns the free-tier defaults (never raises) when Supabase isn't
    configured, the request fails, or no row exists yet for this user/month.
    """
    default = {"count": 0, "is_pro": False, "limit": 10}
    if not _supabase_configured():
        return default

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/user_usage",
                headers=_supabase_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "month": f"eq.{month}",
                    "select": "*",
                    "limit": "1",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return default
            row = data[0]
            return {
                "count": row.get("analysis_count", 0),
                "is_pro": bool(row.get("is_pro", False)),
                "limit": 10,
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch usage for user %s: %s", user_id, exc)
        return default


async def increment_user_usage(user_id: str, month: str) -> None:
    """
    Best-effort +1 to this user's analysis_count for the given month,
    creating the row if it doesn't exist yet. This is what makes get_user_usage
    (and therefore GET /usage and the free-tier limit check in /analyze)
    reflect real activity instead of always reading back 0.

    Read-then-write, not atomic — a genuine race is possible under truly
    concurrent requests from the same user. A Postgres RPC function would
    make this atomic; not worth an extra migration for a v1 free-tier
    counter where the worst case is a user getting 1-2 extra free analyses.
    """
    if not _supabase_configured():
        return
    try:
        current = await get_user_usage(user_id, month)
        headers = _supabase_headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.supabase_url}/rest/v1/user_usage",
                headers=headers,
                # PostgREST only treats resolution=merge-duplicates as an
                # upsert when on_conflict names the unique constraint to
                # merge against — without it, every call past the first for
                # a given (user_id, month) falls through to a plain INSERT
                # and 409s against user_usage_user_month_unique (migration
                # 006), silently caught below. That left analysis_count
                # stuck at 1 forever after the first analysis, so the
                # free-tier paywall never triggered. Confirmed live against
                # Supabase before this fix and re-verified after.
                params={"on_conflict": "user_id,month"},
                json={"user_id": user_id, "month": month, "analysis_count": current["count"] + 1},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to increment usage for user %s: %s", user_id, exc)


async def link_stripe_customer(user_id: str, stripe_customer_id: str, month: str) -> None:
    """
    Associate a Clerk user_id with the Stripe customer_id created at
    checkout, upserting the (user_id, month) row so a later
    customer.subscription.* webhook event — which only carries the Stripe
    customer_id, not the Clerk user_id — has a row it can find and update.
    """
    if not _supabase_configured():
        return
    try:
        headers = _supabase_headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.supabase_url}/rest/v1/user_usage",
                headers=headers,
                # Same upsert-needs-on_conflict requirement as
                # increment_user_usage above — without it this also 409s
                # (silently, caught below) on the second checkout for the
                # same (user_id, month), e.g. a user who upgrades, cancels,
                # then re-subscribes within the same month.
                params={"on_conflict": "user_id,month"},
                json={"user_id": user_id, "month": month, "stripe_customer_id": stripe_customer_id},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to link Stripe customer %s to user %s: %s", stripe_customer_id, user_id, exc)


async def update_user_pro_status(stripe_customer_id: str, is_pro: bool) -> None:
    """
    Flip is_pro on whichever user_usage row(s) match this Stripe customer_id
    — set by link_stripe_customer() at checkout time. A customer with no
    linked row yet (e.g. this event arrived before checkout.session.completed
    was processed) is silently a no-op; Stripe retries failed/ignored
    webhooks, but this one doesn't even fail — there's just nothing to match
    yet, so the next subscription.updated event (or a manual reconciliation)
    is what would need to catch it.
    """
    if not _supabase_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{settings.supabase_url}/rest/v1/user_usage",
                headers=_supabase_headers(),
                params={"stripe_customer_id": f"eq.{stripe_customer_id}"},
                json={"is_pro": is_pro},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to update Pro status for Stripe customer %s: %s", stripe_customer_id, exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _top_severity(findings: list[dict]) -> str:
    """Return the highest severity across all findings."""
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    top = 0
    label = "low"
    for f in findings:
        sev = str(f.get("severity", "low")).lower()
        if order.get(sev, 0) > top:
            top = order[sev]
            label = sev
    return label
