"""
Checks on what the LLM sends back, before any of it reaches the user.

Two shapes of AI output:
- rewritten_query: a full rewrite. Rejected if it drops a table or an output
  column of the original, or is visibly broken (unbalanced parentheses,
  empty list items). A rejected rewrite is removed and the reason recorded.
- targeted_fixes: before -> after snippets, used for long queries and
  multi-statement batches. A fix is kept only if its "before" text really
  occurs in the original query.

Neither check proves a rewrite is equivalent; they catch the common ways a
model silently changes results.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.json_utils import parse_json_lenient
from app.tools.query_parser import strip_sql_comments

# Above this size, or for a multi-statement batch, ask for targeted fixes
# instead of a full rewrite: a full copy of a large batch is slow, often cut
# off, and the model tends to drop pieces of it.
TARGETED_FIX_MIN_CHARS = 3000
MAX_TARGETED_FIXES = 8

# Statements other than a plain SELECT (CTEs and UNIONs stay single queries).
_NON_SELECT_START_RE = re.compile(
    r"(?im)^\s*(?:declare|insert|update|delete|merge|create|drop|alter|exec|execute|truncate)\b"
)


def wants_targeted_fixes(query: str) -> bool:
    """True for long queries and multi-statement batches."""
    code = strip_sql_comments(query or "")
    if len(code) > TARGETED_FIX_MIN_CHARS:
        return True
    statements = [s for s in _mask(code).split(";") if s.strip()]
    if len(statements) > 1:
        return True
    # Batches without semicolons, and DML/DDL: any top-level line that starts
    # a non-SELECT statement.
    return any(_depth_at(code, m.start()) == 0 for m in _NON_SELECT_START_RE.finditer(code))


def _mask(sql: str) -> str:
    """Blank out the insides of strings and quoted identifiers (same length)."""

    def _blank(m: re.Match) -> str:
        t = m.group(0)
        return t[0] + " " * (len(t) - 2) + t[-1]

    # [^\[\]] keeps this linear on input like "[[[[...".
    return re.sub(r"'(?:[^']|'')*'|\[[^\[\]]*\]|\"[^\"]*\"|`[^`]*`", _blank, sql)


def _depth_at(sql: str, pos: int) -> int:
    masked = _mask(sql[:pos])
    return masked.count("(") - masked.count(")")


def _norm_name(name: str) -> str:
    n = re.sub(r"[\[\]\"`]", "", name).strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n.split(".")[-1]


_TABLE_REF_RE = re.compile(
    r"\b(?:from|join|into|update)\s+"
    r"([@#]{0,2}(?:\[[^\]]+\]|\"[^\"]+\"|`[^`]+`|[A-Za-z_][\w$]*)"
    r"(?:\s*\.\s*(?:\[[^\]]+\]|\"[^\"]+\"|`[^`]+`|[A-Za-z_][\w$]*))*)",
    re.IGNORECASE,
)


def _tables(sql: str) -> dict[str, str]:
    """Normalized table name -> name as written (first occurrence)."""
    masked = _mask(sql)
    out: dict[str, str] = {}
    for m in _TABLE_REF_RE.finditer(masked):
        raw = sql[m.start(1) : m.end(1)].strip()
        key = _norm_name(raw)
        if key:
            out.setdefault(key, raw)
    return out


# Output column names: T-SQL "[Name] = expr" items and "expr AS name" aliases
# followed by a comma or FROM.
_ASSIGN_RE = re.compile(r"(?:\bselect|,)\s*(\[[^\]]+\]|[A-Za-z_]\w*)\s*=(?!=)", re.IGNORECASE)
_AS_ALIAS_RE = re.compile(r"\bas\s+(\[[^\]]+\]|\"[^\"]+\"|[A-Za-z_]\w*)\s*(?=,|\bfrom\b)", re.IGNORECASE)


def _output_columns(sql: str) -> dict[str, str]:
    """Normalized output column name -> name as written."""
    out: dict[str, str] = {}
    for rx in (_ASSIGN_RE, _AS_ALIAS_RE):
        for m in rx.finditer(sql):
            key = _norm_name(m.group(1))
            if key:
                out.setdefault(key, m.group(1))
    return out


def _syntax_problem(sql: str) -> str | None:
    masked = _mask(sql)
    if masked.count("(") != masked.count(")"):
        return "it has unbalanced parentheses"
    if re.search(r",\s*,|\(\s*,|,\s*\)|,\s*\bfrom\b", masked, re.IGNORECASE):
        return "it has an empty item in a list (a stray comma)"
    return None


def check_rewrite(original: str, rewrite: str) -> str | None:
    """Why a full rewrite must not be shown, or None if it passes."""
    orig = strip_sql_comments(original or "")
    new = strip_sql_comments(rewrite or "")
    if not new.strip():
        return None
    problem = _syntax_problem(new)
    if problem:
        return problem
    orig_tables, new_tables = _tables(orig), _tables(new)
    missing_tables = [orig_tables[k] for k in orig_tables if k not in new_tables]
    if missing_tables:
        return "it drops table " + ", ".join(missing_tables[:3])
    orig_cols, new_cols = _output_columns(orig), _output_columns(new)
    missing_cols = [orig_cols[k] for k in orig_cols if k not in new_cols]
    if missing_cols:
        return "it drops output column " + ", ".join(missing_cols[:3])
    return None


def _paren_balance(sql: str) -> int:
    m = _mask(sql)
    return m.count("(") - m.count(")")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def check_targeted_fixes(original: str, fixes: Any) -> tuple[list[dict[str, str]], int]:
    """Keep fixes whose 'before' text occurs in the original. Returns (kept, dropped)."""
    if not isinstance(fixes, list):
        return [], 0
    haystack = _squash(original)
    kept: list[dict[str, str]] = []
    dropped = 0
    for f in fixes:
        if not isinstance(f, dict):
            dropped += 1
            continue
        before = str(f.get("before") or "").strip()
        after = str(f.get("after") or "").strip()
        if not before or not after or _squash(before) == _squash(after) or _squash(before) not in haystack:
            dropped += 1
            continue
        if _paren_balance(before) != _paren_balance(after):
            dropped += 1
            continue
        kept.append(
            {
                "title": str(f.get("title") or "").strip()[:160],
                "before": before,
                "after": after,
                "why": str(f.get("why") or "").strip()[:600],
            }
        )
        if len(kept) >= MAX_TARGETED_FIXES:
            break
    return kept, dropped


def review_ai_output(original: str, ai_text: str | None) -> str | None:
    """
    Apply both checks to the model's JSON reply and return it re-serialized.
    A reply cut off by the token limit is repaired first; whatever was being
    written when it stopped is dropped (an incomplete rewrite or the last,
    possibly half-written targeted fix), and output_truncated is set.
    Text that is not JSON at all is returned unchanged.
    """
    if not ai_text:
        return ai_text
    data, truncated, last_complete = parse_json_lenient(ai_text)
    if not isinstance(data, dict):
        return ai_text

    if truncated:
        last = list(data)[-1] if data and not last_complete else None
        data["output_truncated"] = True
        if last == "rewritten_query" and isinstance(data.get("rewritten_query"), str) and data["rewritten_query"]:
            data["rewritten_query"] = ""
            data["rewrite_cut_off"] = True
        elif last == "targeted_fixes" and isinstance(data.get("targeted_fixes"), list) and data["targeted_fixes"]:
            data["targeted_fixes"] = data["targeted_fixes"][:-1]
            data["targeted_fixes_dropped"] = 1

    rewrite = data.get("rewritten_query")
    if isinstance(rewrite, str) and rewrite.strip():
        reason = check_rewrite(original, rewrite)
        if reason:
            data["rewritten_query"] = ""
            data["rewrite_rejected"] = reason

    if "targeted_fixes" in data:
        already = int(data.get("targeted_fixes_dropped") or 0)
        kept, dropped = check_targeted_fixes(original, data.get("targeted_fixes"))
        data["targeted_fixes"] = kept
        if dropped + already:
            data["targeted_fixes_dropped"] = dropped + already

    return json.dumps(data, ensure_ascii=False)
