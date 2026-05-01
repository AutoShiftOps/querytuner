from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.agents.explainer import QueryExplainer
from app.agents.optimizer import QueryOptimizer
from app.llm.router import run_llm
from app.schemas.models import DatabaseType
from app.schemas.models import QueryRequest as QR
from app.tools.execution_planner import collect_facts
from app.tools.query_parser import QueryParser

logger = logging.getLogger(__name__)


@dataclass
class AnalyzerConfig:
    max_query_chars: int = 20000

    @staticmethod
    def from_env() -> AnalyzerConfig:
        return AnalyzerConfig(
            max_query_chars=int(os.getenv("MAX_QUERY_CHARS", "20000")),
        )


class SQLAnalyzerAgent:
    """
    SQL Analyzer Agent (Heuristics + Optional LLM Enhancement)

    - Always runs heuristics (fast, free, reliable).
    - Optionally runs LLM insights via provider routing:
        - huggingface (default) using HF_API_KEY
        - openai (later) using OPENAI_API_KEY
    """

    def __init__(self, config: AnalyzerConfig | None = None):
        self.config = config or AnalyzerConfig.from_env()
        self.parser = QueryParser()
        self.optimizer = QueryOptimizer()
        self.explainer = QueryExplainer()

        DIALECT_RULES = {
            "postgresql": (
                "Use PostgreSQL syntax and indexing (CREATE INDEX ...). EXPLAIN is available; ANALYZE executes."
            ),
            "mysql": (
                "Use MySQL 8+ syntax. Use EXPLAIN/EXPLAIN ANALYZE where applicable; avoid PostgreSQL-only syntax."
            ),
            "sqlite": ("Use SQLite syntax. Avoid server-only features; indexes exist but no advanced planner hints."),
            "sqlserver": (
                "Use T-SQL syntax. Use SQL Server indexing and query patterns; avoid LIMIT (use TOP/OFFSET)."
            ),
            "oracle": (
                "Use Oracle SQL syntax. Use EXPLAIN PLAN FOR and DBMS_XPLAN. Use ROWNUM or FETCH FIRST for pagination."
            ),
        }
        self.dialect_rules = DIALECT_RULES

    async def analyze(
        self,
        query: str,
        db_type: str,
        schema_info: str | None = None,
        use_llm: bool = False,
        llm_provider: str = "huggingface",
        focus: str = "performance",
    ) -> dict[str, Any]:
        """
        Returns a dict that your FastAPI layer can map into QueryAnalysisResult:
          - parsing_result
          - optimization_suggestions
          - optimized_query
          - security_issues
          - readability_score
          - ai_insights (optional)
          - ai_model (optional)
        """
        query = (query or "").strip()
        if not query:
            raise ValueError("Query is empty")

        if len(query) > self.config.max_query_chars:
            raise ValueError(f"Query too large (>{self.config.max_query_chars} chars)")

        schema_info = (schema_info or "").strip()
        focus = (focus or "performance").strip().lower()
        llm_provider = (llm_provider or "huggingface").strip().lower()

        parsed = self._safe_parse(query)

        security_issues = self._security_checks(query)
        readability_score = self._readability_score(query, parsed)
        suggestions = self._heuristic_suggestions(query, parsed, db_type=db_type, focus=focus)
        # optimizer.py now does the actual rewriting
        optimized_query = self.optimizer.rewrite(query, suggestions, db_type=db_type)

        # explainer.py generates plain-English diagnosis (always runs, free, no LLM needed)
        plain_explanation = self.explainer.explain(
            query=query,
            parsed=parsed,
            suggestions=suggestions,
            db_type=db_type,
            security_issues=security_issues,
        )

        ai_insights, ai_model, ai_error = None, None, None
        ai_attempted = False
        used_ai = False

        if use_llm:
            ai_attempted = True
            prompt = self._build_llm_prompt(
                query=query,
                db_type=db_type,
                schema_info=schema_info,
                parsed=parsed,
                suggestions=suggestions,
                focus=focus,
            )

            ai_insights, ai_model, ai_error = await self._try_llm(llm_provider=llm_provider, prompt=prompt)

            used_ai = bool(ai_insights and str(ai_insights).strip())

        facts_result = None
        try:
            _req = QR(
                query=query,
                db_type=db_type if isinstance(db_type, DatabaseType) else DatabaseType(db_type),
                schema_info=schema_info or None,
                use_llm=False,
            )
            _facts = await collect_facts(_req)
            facts_result = _facts.dict()
        except Exception as _e:
            facts_result = {
                "db_type": db_type,
                "warnings": [f"Plan collection skipped: {str(_e)}"],
                "findings": [],
            }

        return {
            "parsing_result": parsed,
            "optimization_suggestions": suggestions,
            "optimized_query": optimized_query,
            "plain_explanation": plain_explanation,
            "security_issues": security_issues,
            "readability_score": readability_score,
            "facts": facts_result,
            "ai_attempted": ai_attempted,
            "ai_insights": ai_insights,
            "ai_model": ai_model,
            "ai_provider": llm_provider if use_llm else None,
            "used_ai": used_ai,
            "ai_error": ai_error,
        }

    # -------------------------
    # Parsing / safety
    # -------------------------

    def _safe_parse(self, query: str) -> dict[str, Any]:
        try:
            parsed = self.parser.parse(query)
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception:
            return {}

    # -------------------------
    # Heuristics
    # -------------------------

    def _heuristic_suggestions(
        self,
        query: str,
        parsed: dict[str, Any],
        db_type: str,
        focus: str,
    ) -> list[dict[str, Any]]:
        q = query.strip()
        ql = q.lower()

        tables = parsed.get("tables") or []
        subqueries = parsed.get("subqueries") or 0
        complexity = parsed.get("complexity_score") or 0

        suggestions: list[dict[str, Any]] = []

        # 1) SELECT *
        if re.search(r"\bselect\s+\*\b", ql):
            suggestions.append(
                self._suggest(
                    type_="column_selection",
                    severity="medium",
                    suggestion="Avoid SELECT *; specify only needed columns",
                    reason="Reduces I/O and memory usage; can improve planning and network transfer",
                    estimated="5-15% faster (varies)",
                )
            )

        # 2) Missing WHERE for SELECT (risky)
        has_select = re.search(r"\bselect\b", ql, re.IGNORECASE) is not None
        has_where = re.search(r"\bwhere\b", ql, re.IGNORECASE) is not None

        if has_select and not has_where:
            suggestions.append(
                self._suggest(
                    type_="full_scan_risk",
                    severity="medium",
                    suggestion="Query has no WHERE clause; ensure this is intentional",
                    reason="May scan entire table(s), especially costly on large datasets",
                    estimated="Varies",
                )
            )

        # 3) LIKE with leading wildcard
        # FIX: removed trailing \b which never matched after closing quote character
        if re.search(r"\blike\s+'%[^']*'", ql):
            suggestions.append(
                self._suggest(
                    type_="like_wildcard",
                    severity="high",
                    suggestion="Leading-wildcard LIKE (e.g. LIKE '%abc') cannot use a B-tree index",
                    reason="Consider full-text search or a trigram index (pg_trgm for PostgreSQL, FULLTEXT for MySQL)",
                    estimated="Often large — full index scan avoided",
                )
            )

        # 4) Functions on columns in WHERE
        # FIX: expanded function list to include YEAR, MONTH, DAY, DATEPART, EXTRACT,
        #      CONVERT, TO_DATE, TO_CHAR, NVL, ISNULL, IFNULL which were previously missed
        _fn_pattern = (
            r"\bwhere\b.*\b("
            r"lower|upper|trim|ltrim|rtrim|substr|substring|"
            r"cast|convert|"
            r"date|year|month|day|datepart|datename|extract|"
            r"to_date|to_char|to_number|"
            r"isnull|ifnull|nvl|coalesce|nullif|"
            r"abs|round|floor|ceil|ceiling|length|len|"
            r"md5|sha|sha1|sha2"
            r")\s*\("
        )
        if re.search(_fn_pattern, ql, re.DOTALL | re.IGNORECASE):
            suggestions.append(
                self._suggest(
                    type_="function_in_where",
                    severity="high",
                    suggestion="Avoid wrapping filtered columns in functions inside WHERE",
                    reason=(
                        "Functions on indexed columns prevent index seeks. "
                        "Rewrite as a range condition (e.g. YEAR(col)=2025 → col BETWEEN '2025-01-01' AND '2025-12-31')"
                    ),
                    estimated="Often large — enables index seek instead of full scan",
                )
            )

        # 5) ORDER BY without LIMIT
        if " order by " in f" {ql} " and " limit " not in f" {ql} " and "fetch first" not in ql:
            suggestions.append(
                self._suggest(
                    type_="order_by_no_limit",
                    severity="medium",
                    suggestion="Consider adding LIMIT/FETCH FIRST for user-facing queries with ORDER BY",
                    reason="Sorting large result sets is expensive; limiting reduces sort work",
                    estimated="Varies",
                )
            )

        # 6) Too many joins
        join_count = ql.count(" join ")
        if join_count >= 4:
            suggestions.append(
                self._suggest(
                    type_="join_complexity",
                    severity="high",
                    suggestion=f"Query has {join_count} JOINs; review join order, keys, and filter pushdown",
                    reason="Many joins can amplify row counts and increase planner complexity",
                    estimated="Varies",
                )
            )

        # 7) Subquery count
        if isinstance(subqueries, int) and subqueries >= 2:
            suggestions.append(
                self._suggest(
                    type_="subquery_refactor",
                    severity="medium",
                    suggestion="Consider refactoring nested subqueries into CTEs (WITH) or JOINs where appropriate",
                    reason="Improves readability; may improve planning depending on the DB and query shape",
                    estimated="Varies",
                )
            )

        # 8) Complexity score
        try:
            c = float(complexity)
            if c >= 70:
                suggestions.append(
                    self._suggest(
                        type_="high_complexity",
                        severity="medium",
                        suggestion=(
                            "High complexity query: consider splitting into steps, "
                            "using temp tables, or pre-aggregation"
                        ),
                        reason="Complex queries are harder to optimize and maintain",
                        estimated="Varies",
                    )
                )
        except Exception:
            pass

        # 9) Index hint (generic — only when WHERE exists)
        if " where " in f" {ql} " and tables:
            suggestions.append(
                self._suggest(
                    type_="index_review",
                    severity="high",
                    suggestion="Review indexes on columns used in WHERE, JOIN, GROUP BY, and ORDER BY",
                    reason="Correct indexes are often the biggest performance lever",
                    estimated="Often large",
                )
            )

        # 10) Focus-specific
        if focus == "security":
            suggestions.append(
                self._suggest(
                    type_="security_best_practice",
                    severity="medium",
                    suggestion="Ensure application uses parameterized queries (no string concatenation)",
                    reason="Reduces SQL injection risk and improves query plan caching",
                    estimated="Risk reduction",
                )
            )

        return self._dedupe_suggestions(suggestions)

    def _compose_optimized_query(self, query: str, suggestions: list[dict[str, Any]], db_type: str) -> str:
        q = query.strip()
        out_lines: list[str] = []

        out_lines.append("-- Suggested optimized SQL (review before using)")
        out_lines.append(f"-- DB: {db_type}")

        if any(s.get("type") in ("index_review", "index_missing") for s in suggestions):
            out_lines.append("-- Consider: add/verify indexes on WHERE/JOIN/GROUP BY/ORDER BY columns")

        # Rewrite SELECT *
        if re.search(r"\bselect\s+\*\b", q, re.IGNORECASE):
            q = re.sub(
                r"\bselect\s+\*\b",
                "SELECT /* TODO: list required columns */",
                q,
                flags=re.IGNORECASE,
            )

        # Rewrite YEAR(col) = N → range condition (MySQL/SQL Server/Oracle pattern)
        def _rewrite_year(m):
            col = m.group(1).strip()
            yr = m.group(2).strip()
            return f"{col} BETWEEN '{yr}-01-01' AND '{yr}-12-31'"

        q = re.sub(
            r"YEAR\s*\(\s*([\w.]+)\s*\)\s*=\s*(\d{{4}})",
            _rewrite_year,
            q,
            flags=re.IGNORECASE,
        )

        # Rewrite LOWER(col) = 'x' → col = 'x' with note
        def _rewrite_lower(m):
            col = m.group(1).strip()
            val = m.group(2).strip()
            return f"-- Use a case-insensitive index (CITEXT/collation) instead of LOWER()\n{col} = {val}"

        q = re.sub(
            r"LOWER\s*\(\s*([\w.]+)\s*\)\s*=\s*('[^']*')",
            _rewrite_lower,
            q,
            flags=re.IGNORECASE,
        )

        out_lines.append(q)
        return "\n".join(out_lines)

    # -------------------------
    # Security / readability
    # -------------------------

    def _security_checks(self, query: str) -> list[str]:
        ql = query.lower()
        issues: list[str] = []

        if ql.count(";") >= 2:
            issues.append("Multiple SQL statements detected; consider restricting to a single statement")

        for op in (" drop ", " truncate ", " alter ", " grant ", " revoke "):
            if op in f" {ql} ":
                issues.append(f"Potentially destructive/admin operation detected: {op.strip().upper()}")

        if "--" in query or "/*" in query:
            issues.append("SQL comments detected; ensure input is trusted/parameterized")

        if " union " in f" {ql} ":
            issues.append("UNION detected; validate inputs and prefer parameterized queries")

        if "||" in query or "concat(" in ql:
            issues.append("String concatenation detected; use parameterized queries to reduce injection risk")

        return issues

    def _readability_score(self, query: str, parsed: dict[str, Any]) -> float:
        score = 100.0

        complexity = parsed.get("complexity_score", 0) or 0
        try:
            score -= min(float(complexity) * 0.3, 30.0)
        except Exception:
            pass

        if re.search(r"\bselect\s+\*\b", query, re.IGNORECASE):
            score -= 10

        if query.count("\n") < 2:
            score -= 15

        if len(query) > 1500:
            score -= 10

        return float(max(0.0, min(100.0, score)))

    # -------------------------
    # LLM prompt + call
    # -------------------------

    def _build_llm_prompt(
        self,
        query: str,
        db_type: str,
        schema_info: str,
        parsed: dict[str, Any],
        suggestions: list[dict[str, Any]],
        focus: str,
    ) -> str:
        schema_trim = (schema_info or "")[:4000]
        parsed_summary = {
            "tables": parsed.get("tables"),
            "joins": parsed.get("joins"),
            "subqueries": parsed.get("subqueries"),
            "group_by": parsed.get("group_by"),
            "order_by": parsed.get("order_by"),
            "complexity_score": parsed.get("complexity_score"),
        }
        dialect_hint = self.dialect_rules.get(db_type, "")

        return f"""You are a senior SQL performance engineer.

Focus: {focus}
Database: {db_type}
Dialect rules: {dialect_hint}

Schema (optional, may be partial):
{schema_trim}

SQL:
{query}

Parsed summary:
{parsed_summary}

Heuristic suggestions already found:
{suggestions}

Tasks:
1) Provide the most impactful performance improvements (prioritized).
2) Recommend concrete indexes (include example CREATE INDEX statements).
3) Provide a rewritten query if it can reduce cost (CTEs/JOIN refactors/filters).
4) Call out any risky assumptions (unknown cardinalities, missing schema).
Keep it concise and actionable.
"""

    async def _try_llm(self, llm_provider: str, prompt: str) -> tuple[str | None, str | None, str | None]:
        try:
            text, model, err = await run_llm(provider=llm_provider, prompt=prompt)
            if not text or not str(text).strip():
                return None, model, "LLM returned empty response"
            return text, model, err
        except Exception as e:
            return None, None, str(e)

    # -------------------------
    # Utilities
    # -------------------------

    def _suggest(self, type_: str, severity: str, suggestion: str, reason: str, estimated: str) -> dict[str, Any]:
        return {
            "type": type_,
            "severity": severity,
            "suggestion": suggestion,
            "reason": reason,
            "estimated_improvement": estimated,
        }

    def _dedupe_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        out: list[dict[str, Any]] = []
        for s in suggestions:
            key = (s.get("type"), s.get("suggestion"))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out
