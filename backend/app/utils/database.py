import hashlib
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
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
_OPTIONAL_COLUMNS = ("plain_explanation", "ai_insights", "ai_provider")


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
    if not settings.supabase_url or not settings.supabase_anon_key:
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
    if not settings.supabase_url or not settings.supabase_anon_key:
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
