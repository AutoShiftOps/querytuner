"""
AI index suggestions: the model names the table and columns, our code writes
the DDL.

The model's own CREATE INDEX text is never passed on. Each suggestion is
reduced to (table, key columns, include columns), checked against the query
(and the pasted schema, when there is one), and the CREATE / rollback
statements are rebuilt with the same dialect templates the heuristic
engine uses. A suggestion that names a table or column the query does not
use, an expression, or a CTE / derived table is dropped with a reason.

Idea credit: AI SQL Tuner's open-source index tuner (MIT), which never runs
the model's script and rebuilds DDL from structured fields instead.
"""

from __future__ import annotations

import re
from typing import Any

from app.tools.index_recommender import _index_name, _unindexable_names
from app.tools.query_parser import parse_schema_ddl, strip_sql_comments
from app.utils.dialect_config import get_dialect, get_index_ddl

MAX_AI_INDEXES = 6

# Dialects whose CREATE INDEX accepts INCLUDE (...) (PostgreSQL 11+).
_INCLUDE_DIALECTS = {"postgresql", "sqlserver"}

_QUOTES = {"sqlserver": ("[", "]"), "mysql": ("`", "`")}
_DISPLAY = {"mysql": "MySQL", "oracle": "Oracle", "sqlite": "SQLite"}
_SEVERITIES = {"critical", "high", "medium", "low"}


def _severity(item: Any) -> str:
    sev = str(item.get("severity") or "").lower() if isinstance(item, dict) else ""
    return sev if sev in _SEVERITIES else "medium"


_PLAIN_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*")

_NAME_PART = r'(?:\[[^\]]+\]|"[^"]+"|`[^`]+`|[^\s(.\[\]"`]+)'

# CREATE [UNIQUE] [CLUSTERED|NONCLUSTERED] INDEX [CONCURRENTLY] [IF NOT EXISTS] name ON table (cols) [INCLUDE (cols)]
_CREATE_INDEX_RE = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?(?:(?:NON)?CLUSTERED\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    r"\S+\s+ON\s+(?P<table>" + _NAME_PART + r"(?:\." + _NAME_PART + r")*)\s*(?P<open>\()",
    re.IGNORECASE | re.DOTALL,
)
# MySQL: ALTER TABLE t ADD [UNIQUE] INDEX name (cols)
_ADD_INDEX_RE = re.compile(
    r"\bALTER\s+TABLE\s+(?P<table>"
    + _NAME_PART
    + r"(?:\."
    + _NAME_PART
    + r")*)\s+ADD\s+(?:UNIQUE\s+)?(?:INDEX|KEY)\s+[^\s(]*\s*(?P<open>\()",
    re.IGNORECASE | re.DOTALL,
)

_TEXT_KEYS = ("why", "reason", "rationale", "explanation", "description")
_TITLE_KEYS = ("suggestion", "title", "name", "summary")
_DDL_KEYS = ("ddl", "ddl_statement", "sql", "index_ddl", "ddl_hint", "statement", "create_index")


def _unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and (name[0], name[-1]) in {("[", "]"), ('"', '"'), ("`", "`")}:
        return name[1:-1]
    return name


def _split_top_level(text: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _paren_body(text: str, start: int) -> str | None:
    """Text between the '(' just before `start` and its matching ')'."""
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i]
    return None


def _name_parts(qualified: str) -> list[str]:
    """dbo.[Order Lines] -> ['dbo', 'Order Lines']; an unquoted name with no dot is one part."""
    if "." not in qualified:
        return [_unquote(qualified)] if qualified.strip() else []
    return [_unquote(p) for p in re.findall(r'\[[^\]]+\]|"[^"]+"|`[^`]+`|[^.\s]+', qualified)]


def _norm(name: str) -> str:
    return _unquote(name).lower()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return _split_top_level(value)
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _structured(item: Any) -> tuple[str, list[str], list[str], str, str] | None:
    """(table, keys, include, title, why) from one AI item, or None."""
    if isinstance(item, dict):
        table = item.get("table") or item.get("table_name")
        keys = _as_list(item.get("columns") or item.get("key_columns") or item.get("keys"))
        include = _as_list(item.get("include") or item.get("include_columns") or item.get("included_columns"))
        title = _first_text(item, _TITLE_KEYS)
        why = _first_text(item, _TEXT_KEYS)
        if isinstance(table, str) and table.strip() and keys:
            return table.strip(), keys, include, title, why
        ddl = _first_text(item, _DDL_KEYS)
        if not ddl:
            # Some models put the statement in the title.
            ddl = title
    elif isinstance(item, str):
        ddl, title, why = item, "", ""
    else:
        return None

    m = _CREATE_INDEX_RE.search(ddl) or _ADD_INDEX_RE.search(ddl)
    if not m:
        return None
    cols_text = _paren_body(ddl, m.end("open"))
    if cols_text is None:
        return None
    cols = [re.sub(r"\s+(ASC|DESC)\s*$", "", c, flags=re.IGNORECASE) for c in _split_top_level(cols_text)]
    rest = ddl[m.end("open") + len(cols_text) + 1 :]
    inc_m = re.match(r"\s*INCLUDE\s*\(", rest, re.IGNORECASE)
    include = _split_top_level(_paren_body(rest, inc_m.end()) or "") if inc_m else []
    if isinstance(item, str):
        title = ""
    return m.group("table"), cols, include, title, why


class _QueryFacts:
    """What the query (and pasted schema) says exists."""

    def __init__(self, query: str, parsed: dict[str, Any] | None, schema_info: str | None):
        parsed = parsed or {}
        self.code = strip_sql_comments(query or "")
        self.schema = parse_schema_ddl(schema_info) if schema_info else {}
        relations, computed = _unindexable_names(self.code, parsed.get("select_items"))
        self.relations = relations
        self.computed = computed

        # normalized last name part -> the query's own spelling of the table
        self.tables: dict[str, str] = {}
        for t in parsed.get("tables") or []:
            parts = _name_parts(str(t))
            if parts:
                self.tables.setdefault(parts[-1].lower(), str(t))
        self.aliases: dict[str, str] = {}
        for alias, t in (parsed.get("table_aliases") or {}).items():
            parts = _name_parts(str(t))
            if alias and parts:
                self.aliases[_norm(alias)] = str(t)
                self.tables.setdefault(parts[-1].lower(), str(t))
        # schema tables, by last name part
        self.schema_tables: dict[str, str] = {}
        for t in self.schema:
            parts = _name_parts(t)
            if parts:
                self.schema_tables[parts[-1].lower()] = t

    def resolve_table(self, name: str) -> tuple[str | None, str]:
        """(the query's spelling of the table, problem) — problem is '' when found."""
        parts = _name_parts(name)
        if not parts:
            return None, "no table was named"
        last = parts[-1].lower()
        found = None
        if len(parts) == 1 and last in self.aliases:
            found = self.aliases[last]
        elif last in self.tables:
            found = self.tables[last]
        # A CTE / derived table shadows any base table of the same name, and
        # the parser lists CTE names among the query's tables.
        real_last = _name_parts(found)[-1].lower() if found else last
        if real_last in self.relations and len(_name_parts(found or name)) == 1:
            return None, f"`{_name_parts(found or name)[-1]}` is a CTE or derived table, which cannot be indexed"
        if found:
            return found, ""
        return None, f"table `{name}` is not used in this query"

    def schema_columns(self, table: str) -> dict[str, str] | None:
        parts = _name_parts(table)
        key = self.schema_tables.get(parts[-1].lower()) if parts else None
        if key is None:
            return None
        return {c.lower(): c for c in self.schema[key]}

    def column_problem(self, table: str, col: str) -> str:
        bare = _unquote(col)
        if not bare or "(" in bare or not re.fullmatch(r"[\w $#]+", bare):
            return f"`{col}` is an expression, not a column (expression indexes are not checked yet)"
        schema_cols = self.schema_columns(table)
        if schema_cols is not None:
            if bare.lower() not in schema_cols:
                return f"column `{bare}` is not in your schema for `{table}`"
            return ""
        if bare.lower() in self.computed:
            return f"`{bare}` is a computed SELECT alias, not a table column"
        name_re = re.compile(r"(?<![\w$#])" + re.escape(bare) + r"(?![\w$#])", re.IGNORECASE)
        hits = list(name_re.finditer(self.code))
        if not hits:
            return f"column `{bare}` does not appear in this query"
        # Qualified uses (o.col / [o].[col]) tell us which table the column is on.
        qualifiers, unqualified = set(), False
        for h in hits:
            before = self.code[: h.start()].rstrip('["`')
            if before.endswith("."):
                q = re.search(r'(\[[^\]]+\]|"[^"]+"|`[^`]+`|[\w$#]+)\s*\.$', before)
                if q:
                    qualifiers.add(_norm(q.group(1)))
            else:
                unqualified = True
        if qualifiers and not unqualified:
            target = _name_parts(table)[-1].lower()
            owners = {_name_parts(self.aliases.get(q, q))[-1].lower() for q in qualifiers}
            if target not in owners:
                return f"column `{bare}` belongs to another table in this query, not `{table}`"
        return ""

    def verified_by_schema(self, table: str) -> bool:
        return self.schema_columns(table) is not None


def _quote_col(col: str, db_type: str) -> str:
    bare = _unquote(col)
    if _PLAIN_IDENT.fullmatch(bare):
        return bare
    left, right = _QUOTES.get(db_type, ('"', '"'))
    return f"{left}{bare}{right}"


def check_ai_indexes(
    query: str,
    items: Any,
    *,
    db_type: str,
    parsed: dict[str, Any] | None = None,
    schema_info: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Returns (kept, drop_reasons). Each kept item carries DDL and rollback built
    here, never the model's text.
    """
    if not isinstance(items, list):
        return [], []
    facts = _QueryFacts(query, parsed, schema_info)
    db_type = (db_type or "postgresql").lower()
    cfg = get_dialect(db_type)
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for item in items:
        shape = _structured(item)
        if shape is None:
            dropped.append("it did not name a table and columns")
            continue
        table_raw, keys, include, title, why = shape
        table, problem = facts.resolve_table(table_raw)
        if not table:
            dropped.append(problem)
            continue
        problem = next((p for p in (facts.column_problem(table, c) for c in keys + include) if p), "")
        if problem:
            dropped.append(problem)
            continue

        key_cols = list(dict.fromkeys(_quote_col(c, db_type) for c in keys))
        inc_cols = [
            c
            for c in dict.fromkeys(_quote_col(c, db_type) for c in include)
            if c.lower() not in {k.lower() for k in key_cols}
        ]
        sig = (table.lower(), tuple(c.lower() for c in key_cols))
        if sig in seen:
            continue
        seen.add(sig)

        column_text = ", ".join(key_cols)
        include_note = ""
        if inc_cols and db_type in _INCLUDE_DIALECTS:
            # Templates are "...{table}({column})...": close the key list and open INCLUDE.
            column_text = f"{column_text}) INCLUDE ({', '.join(inc_cols)}"
        elif inc_cols:
            include_note = (
                f" {_DISPLAY.get(db_type, db_type)} has no INCLUDE clause, so the covering columns were left out."
            )

        name = _index_name(table, [_unquote(c) for c in key_cols])
        ddl = get_index_ddl(db_type, table, column_text, name)
        verified = "schema" if facts.verified_by_schema(table) else "query"
        cols_label = ", ".join(_unquote(c) for c in key_cols)
        kept.append(
            {
                "suggestion": title or f"Index on {table} ({cols_label})",
                "reason": (why + include_note).strip() or None,
                "table": table,
                "columns": [_unquote(c) for c in key_cols],
                "include": [_unquote(c) for c in inc_cols],
                "ddl": ddl,
                "rollback_ddl": cfg.rollback_index.format(index=name, table=table),
                "verified_against": verified,
                "severity": _severity(item),
            }
        )
        if len(kept) >= MAX_AI_INDEXES:
            break

    return kept, dropped
