"""
database.py — Supabase persistence layer for QueryTuner
Issue #68: Supabase free tier setup + wire POST /analyze to INSERT

Place this file at: backend/app/utils/database.py

Required env vars (add to Render + .env.example):
  SUPABASE_URL=https://your-project.supabase.co
  SUPABASE_ANON_KEY=your-anon-key

Supabase SQL to run once in the Supabase dashboard SQL editor:
-----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE analyses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash  TEXT NOT NULL,
    db_type     TEXT NOT NULL,
    original_query TEXT NOT NULL,
    findings    JSONB NOT NULL DEFAULT '[]',
    severity    TEXT NOT NULL DEFAULT 'low',
    optimized_query TEXT,
    readability_score FLOAT,
    analysis_time_ms FLOAT,
    used_ai     BOOLEAN DEFAULT FALSE,
    ai_model    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by hash (dedup future queries)
CREATE INDEX idx_analyses_query_hash ON analyses(query_hash);
-- Index for time-based queries (usage analytics later)
CREATE INDEX idx_analyses_created_at ON analyses(created_at DESC);
-----------------------------------------------------------------
"""

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.supabase_url}/rest/v1/analyses",
                headers=_supabase_headers(),
                json=row,
            )
            resp.raise_for_status()
            data = resp.json()
            inserted_id = data[0]["id"] if data else None
            logger.info("Analysis saved: id=%s hash=%s", inserted_id, row["query_hash"])
            return inserted_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to save analysis to Supabase: %s", exc)
        return None


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
