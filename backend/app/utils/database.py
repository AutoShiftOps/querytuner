import hashlib
import logging
from datetime import UTC, datetime, timedelta
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
_OPTIONAL_COLUMNS = (
    "plain_explanation",
    "ai_insights",
    "ai_provider",
    "security_issues",
    "user_id",
    "expires_at",  # Issue #116, migration 008
    "was_sanitized",  # Issue #124, migration 009
)

# Issue #116: default shareable-link lifetime, set at write time in
# save_analysis(). A named constant, not a magic literal scattered at the
# call site — pick a different number here if 90 days turns out wrong,
# nothing else needs to change.
ANALYSIS_EXPIRATION_DAYS = 90


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
        # Issue #124: self-reported by the client — see QueryRequest.was_sanitized's
        # own docstring for why this can only ever be self-reported.
        "was_sanitized": bool(payload.get("was_sanitized", False)),
        # Issue #116: every newly-created analysis gets a default
        # expiration window from creation. Existing rows (created before
        # migration 008 shipped) keep expires_at NULL — never expiring —
        # since this INSERT path is the only place that sets it.
        "expires_at": (datetime.now(UTC) + timedelta(days=ANALYSIS_EXPIRATION_DAYS)).isoformat(),
    }

    data = await _insert_with_fallback(row)
    if not data:
        return None

    inserted_id = data[0]["id"] if data else None
    logger.info("Analysis saved: id=%s hash=%s", inserted_id, row["query_hash"])
    return inserted_id


def _is_expired(expires_at: str | None) -> bool:
    """expires_at IS NULL means "never expires" (rows written before
    migration 008, or before this app started setting it) — only a
    present, past timestamp counts as expired."""
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return False
    return expiry <= datetime.now(UTC)


async def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    """
    Retrieve a stored analysis by UUID.
    Returns None if not found, expired, or Supabase is not configured.

    Issue #116: expiration is enforced here rather than in the /report/{id}
    route handler — the route's existing 404 ("Analysis not found. It may
    have expired or the link is incorrect.") already anticipated this case
    and needs no change; an expired analysis just looks exactly like a
    nonexistent one to every caller, deliberately (no separate "this link
    expired" vs "this link never existed" distinction — that would leak
    whether a given UUID was ever valid).
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
            if not data:
                return None
            record = data[0]
            if _is_expired(record.get("expires_at")):
                return None
            return record
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch analysis %s: %s", analysis_id, exc)
        return None


async def expire_analysis(analysis_id: str, user_id: str) -> bool:
    """
    Issue #116: DELETE /report/{id} — lets a signed-in user revoke their
    own shared link early instead of waiting out the default expiration
    window. Soft-delete (sets expires_at to now(), same mechanism the
    default expiration already uses), not a hard DELETE — accomplishes
    the same user-facing outcome (the link stops working immediately) with
    less risk, per the design doc's explicit v1 choice.

    Both id AND user_id are in the PATCH filter — the WHERE clause is the
    actual authorization check, not just a pre-check in application code,
    so this can never touch a row that isn't both the right analysis and
    owned by the caller, regardless of what the caller claims. An
    anonymous-authored analysis (user_id IS NULL in the row) can never
    match `user_id=eq.<caller>` for any real caller, so it's naturally
    unreachable through this function — consistent with the v1 scope of
    "anonymous analyses: expiration-only, no explicit delete".

    Returns True if a row was actually updated (found and owned by this
    user), False otherwise — the route handler turns False into a 404
    without needing to know why (not found vs. not owned looks the same
    to the caller, same reasoning as get_analysis()'s 404).
    """
    if not _supabase_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{settings.supabase_url}/rest/v1/analyses",
                headers=_supabase_headers(),
                params={"id": f"eq.{analysis_id}", "user_id": f"eq.{user_id}"},
                json={"expires_at": datetime.now(UTC).isoformat()},
            )
            resp.raise_for_status()
            updated = resp.json()
            return bool(updated)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to expire analysis %s for user %s: %s", analysis_id, user_id, exc)
        return False


# Longest a history-list query snippet is allowed to be before truncating
# with an ellipsis — this is a *list* row, not the detail view (GET
# /report/{id} already returns the full original_query on click-through),
# so keeping this short is deliberate, not a size limit workaround.
_HISTORY_SNIPPET_CHARS = 200


async def get_analysis_history(
    user_id: str, *, limit: int = 20, offset: int = 0, sanitized_only: bool = False
) -> list[dict[str, Any]]:
    """
    Phase 5 (backlog #54): a lightweight, paginated summary of a user's
    past analyses for the History page (GET /history) — id, db_type, a
    truncated query snippet, severity, issue count, created_at,
    was_sanitized (#124). NOT the full record (execution plan, AI
    insights, schema_info, ...) — that's what GET /report/{id} already
    returns on click-through, so this deliberately avoids `select=*` to
    keep the list response light.

    sanitized_only (#124): filters server-side (a Supabase query param,
    not a client-side array filter) so pagination stays correct against
    the filtered set — filtering an already-paginated page client-side
    would make "Load more" and the item count both lie.

    Returns an empty list (never raises) when Supabase isn't configured,
    the request fails, or the user has no analyses yet — callers can't
    distinguish "no history" from "fetch failed" from this alone, but
    /history's empty-state copy reads fine either way ("Your analyses will
    show up here").
    """
    if not _supabase_configured():
        return []

    base_select = "id,db_type,original_query,severity,findings,created_at"
    # was_sanitized (migration 009) is the first *optional* column this
    # query has ever selected — every other field here has existed since
    # migration 001. A Supabase project that hasn't run 009 yet would 400
    # on the unknown column and (via the broad except below) lose the
    # ENTIRE history list, not just the sanitized part — so this needs the
    # same one-column-at-a-time fallback _insert_with_fallback already
    # uses for writes, just for this one read.
    params = {
        "user_id": f"eq.{user_id}",
        "select": f"{base_select},was_sanitized",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if sanitized_only:
        params["was_sanitized"] = "eq.true"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/analyses",
                headers=_supabase_headers(),
                params=params,
            )
            resp.raise_for_status()
            rows = resp.json()
    except httpx.HTTPStatusError as exc:
        if "was_sanitized" not in exc.response.text:
            logger.warning("Failed to fetch analysis history for user %s: %s", user_id, exc)
            return []
        # Migration 009 hasn't run on this project yet — fall back to the
        # pre-#124 column set. sanitized_only can't be honored without the
        # column to filter on, so it's dropped (unfiltered results) rather
        # than silently returning an empty list for a filter that isn't
        # really "zero sanitized analyses," just "not migrated yet."
        logger.warning("was_sanitized column not found — retrying history fetch without it")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.supabase_url}/rest/v1/analyses",
                    headers=_supabase_headers(),
                    params={
                        "user_id": f"eq.{user_id}",
                        "select": base_select,
                        "order": "created_at.desc",
                        "limit": str(limit),
                        "offset": str(offset),
                    },
                )
                resp.raise_for_status()
                rows = resp.json()
        except Exception as exc2:  # noqa: BLE001
            logger.warning("Failed to fetch analysis history for user %s: %s", user_id, exc2)
            return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch analysis history for user %s: %s", user_id, exc)
        return []

    summaries = []
    for row in rows:
        query = row.get("original_query") or ""
        snippet = query if len(query) <= _HISTORY_SNIPPET_CHARS else query[:_HISTORY_SNIPPET_CHARS].rstrip() + "…"
        findings = row.get("findings")
        summaries.append(
            {
                "id": row.get("id"),
                "db_type": row.get("db_type"),
                "query_snippet": snippet,
                "severity": row.get("severity"),
                "issue_count": len(findings) if isinstance(findings, list) else 0,
                "created_at": row.get("created_at"),
                "was_sanitized": bool(row.get("was_sanitized", False)),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# Phase 4: user usage / Stripe billing status
# ---------------------------------------------------------------------------


async def _get_user_account(user_id: str) -> dict[str, Any] | None:
    """
    Fetch this user's user_accounts row (is_pro, stripe_customer_id) — a
    dedicated per-user row (migration 007), not scoped to a calendar month
    the way user_usage is. Returns None if the row doesn't exist yet
    (never subscribed), Supabase isn't configured, or the request fails.
    """
    if not _supabase_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/user_accounts",
                headers=_supabase_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*", "limit": "1"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch account for user %s: %s", user_id, exc)
        return None


async def get_user_usage(user_id: str, month: str) -> dict[str, Any]:
    """
    Look up a user's analysis count for a given 'YYYY-MM' month plus their
    (not month-scoped) Pro status. Two independent lookups — user_usage for
    analysis_count, user_accounts for is_pro (migration 007; see that
    migration's header for why is_pro moved out of user_usage) — kept
    independent rather than one combined try/except so a failure fetching
    one doesn't zero out the other: a real Pro user hitting the paywall
    because the monthly-count fetch alone flaked would be a worse failure
    mode than analysis_count reading 0 for one request.
    """
    if not _supabase_configured():
        return {"count": 0, "is_pro": False, "limit": 10}

    count = 0
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/user_usage",
                headers=_supabase_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "month": f"eq.{month}",
                    "select": "analysis_count",
                    "limit": "1",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                count = data[0].get("analysis_count", 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch usage count for user %s: %s", user_id, exc)

    account = await _get_user_account(user_id)
    is_pro = bool(account.get("is_pro", False)) if account else False

    return {"count": count, "is_pro": is_pro, "limit": 10}


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

    Only ever writes analysis_count — is_pro/stripe_customer_id live on
    user_accounts now (migration 007), not on this monthly row, and this
    function never touched those fields even before that split.
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


async def get_user_stripe_customer_id(user_id: str) -> str | None:
    """
    Look up this user's Stripe customer_id, for opening a Billing Portal
    session (POST /billing-portal). Direct lookup on user_accounts by
    user_id (its primary key) — migration 007 moved stripe_customer_id off
    the monthly user_usage rows onto this dedicated per-user table, so this
    no longer has to search across all of a user's monthly rows for the
    most recent non-null value the way it used to.
    """
    account = await _get_user_account(user_id)
    return account.get("stripe_customer_id") if account else None


async def link_stripe_customer(user_id: str, stripe_customer_id: str) -> None:
    """
    Associate a Clerk user_id with the Stripe customer_id created at
    checkout, upserting into user_accounts (migration 007) so a later
    customer.subscription.* webhook event — which only carries the Stripe
    customer_id, not the Clerk user_id — has a row it can find and update.

    No `month` parameter anymore: user_accounts is one row per user, not
    one row per user per month, so there's nothing to scope by. Still needs
    on_conflict for the upsert to actually take effect (resolution=
    merge-duplicates alone is a no-op without it — see increment_user_usage's
    history for the bug that taught this), but it's a true single-column
    primary-key upsert (on_conflict=user_id) now instead of the composite
    on_conflict=user_id,month user_usage needed.
    """
    if not _supabase_configured():
        return
    try:
        headers = _supabase_headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.supabase_url}/rest/v1/user_accounts",
                headers=headers,
                params={"on_conflict": "user_id"},
                json={"user_id": user_id, "stripe_customer_id": stripe_customer_id},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to link Stripe customer %s to user %s: %s", stripe_customer_id, user_id, exc)


async def update_user_pro_status(stripe_customer_id: str, is_pro: bool) -> None:
    """
    Flip is_pro on whichever user_accounts row matches this Stripe
    customer_id — set by link_stripe_customer() at checkout time. A
    customer with no linked row yet (e.g. this event arrived before
    checkout.session.completed was processed) is silently a no-op; Stripe
    retries failed/ignored webhooks, but this one doesn't even fail —
    there's just nothing to match yet, so the next subscription.updated
    event (or a manual reconciliation) is what would need to catch it.

    This is the fix for is_pro no longer living on a monthly user_usage
    row: user_accounts has exactly one row per user, so there's no new
    month's row for this update to miss — the same row this PATCHes today
    is still the row get_user_usage() reads is_pro from next month, and
    every month after.
    """
    if not _supabase_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{settings.supabase_url}/rest/v1/user_accounts",
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
