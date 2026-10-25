"""
Compare AI providers on the same queries, with numbers instead of opinions.

Runs each .sql file through the full analyzer once per provider and prints,
per query and provider: latency, whether the reply parsed as JSON, whether
the full rewrite was rejected (dropped a table/column, broken syntax), how
many targeted fixes were kept/dropped, and whether the reply looks cut off.

Usage (from backend/, with the provider keys in the environment or .env):

    python -m scripts.compare_providers path/to/queries/*.sql \
        --db sqlserver --providers openai anthropic

Each call is a real, billed API request. Cost is not estimated here; read the
token usage in each provider's console against its current price list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.agents.sql_analyzer import SQLAnalyzerAgent
from app.llm.json_utils import safe_parse_json


def _summarize(result: dict, seconds: float) -> dict:
    raw = result.get("ai_insights") or ""
    data = safe_parse_json(raw) if raw else None
    data = data if isinstance(data, dict) else {}
    try:
        json.loads(raw)
        complete = True
    except (TypeError, ValueError):
        complete = False
    return {
        "seconds": round(seconds, 1),
        "error": result.get("ai_error"),
        "json_ok": bool(data),
        "complete_json": complete,
        "rewrite": bool((data.get("rewritten_query") or "").strip()),
        "rewrite_rejected": data.get("rewrite_rejected") or "",
        "fixes_kept": len(data.get("targeted_fixes") or []),
        "fixes_dropped": data.get("targeted_fixes_dropped", 0),
        "improvements": len(data.get("most_impactful_improvements") or []),
        "indexes": len(data.get("recommended_indexes") or []),
    }


async def _run(files: list[Path], db: str, providers: list[str]) -> list[dict]:
    agent = SQLAnalyzerAgent()
    rows = []
    for f in files:
        query = f.read_text(encoding="utf-8")
        for p in providers:
            start = time.perf_counter()
            result = await agent.analyze(query=query, db_type=db, use_llm=True, llm_provider=p)
            rows.append({"query": f.name, "provider": p, **_summarize(result, time.perf_counter() - start)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--db", default="postgresql")
    ap.add_argument("--providers", nargs="+", default=["openai", "anthropic"])
    ap.add_argument("--json", action="store_true", help="print raw rows as JSON")
    args = ap.parse_args()

    rows = asyncio.run(_run(args.files, args.db, args.providers))
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    cols = ["query", "provider", "seconds", "complete_json", "rewrite", "rewrite_rejected", "fixes_kept",
            "fixes_dropped", "improvements", "indexes", "error"]  # fmt: skip
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r.get(c, "")) for c in cols))


if __name__ == "__main__":
    main()
