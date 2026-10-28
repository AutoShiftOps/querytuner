"""
ai_cache.py — in-memory cache of AI output for QueryTuner's built-in sample queries.

Every visitor who clicks the same sample sends the same prompt, so paying for a
fresh LLM call each time (and spending the visitor's few free daily AI runs on
a canned example) adds nothing. Only the exact sample queries listed in
app/data/sample_queries.json are cached; any other query always goes to the LLM.
The frontend's sample list is checked against that file by a frontend test, so
the two cannot silently drift apart.

The cache is per-process memory: it empties on restart/deploy, and the first
request for each sample/provider/model combination after that pays for one call.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_queries.json"
CACHE_TTL_SECONDS = 7 * 24 * 3600
CACHE_MAX_ENTRIES = 128  # 9 samples x a handful of provider/model combinations

_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip())


def _sample_signature(db_type: str, sql: str) -> str:
    return f"{str(db_type).lower()}|{_normalize_sql(sql)}"


def _load_sample_signatures() -> frozenset[str]:
    try:
        data = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
        return frozenset(_sample_signature(item["db_type"], item["sql"]) for item in data)
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()  # no samples known -> nothing is cached, never an error


SAMPLE_SIGNATURES = _load_sample_signatures()


def cache_key(
    query: str,
    db_type: str,
    provider: str,
    model: str | None,
    focus: str,
    schema_info: str | None,
    explain_plan: str | None,
) -> str | None:
    """Key for an eligible request, else None. Eligible = an exact built-in sample
    asked for the default focus with no schema or EXPLAIN plan attached (those change the prompt)."""
    db = getattr(db_type, "value", db_type)
    if (schema_info or "").strip() or (explain_plan or "").strip():
        return None
    if (focus or "performance").strip().lower() != "performance":
        return None
    if _sample_signature(db, query) not in SAMPLE_SIGNATURES:
        return None
    raw = "|".join([_sample_signature(db, query), str(provider).lower(), model or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Set by app.llm.rewrite_check.review_ai_output when the reply was cut off by
# the token limit or the full rewrite failed its checks. Such a reply is fine
# to show once, with a note, but must not be served to every later visitor.
_NOT_CACHEABLE_FLAGS = ("output_truncated", "rewrite_cut_off", "rewrite_rejected")


def is_cacheable(ai_insights: str | None) -> bool:
    """False for empty, non-JSON, cut-off or rejected AI replies."""
    if not ai_insights:
        return False
    try:
        data = json.loads(ai_insights)
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and not any(data.get(flag) for flag in _NOT_CACHEABLE_FLAGS)


def get(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return dict(value)


def put(key: str | None, value: dict[str, Any]) -> None:
    if not key or not value.get("ai_insights"):
        return
    _cache[key] = (time.time(), {"ai_insights": value["ai_insights"], "ai_model": value.get("ai_model")})
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def clear() -> None:
    _cache.clear()
