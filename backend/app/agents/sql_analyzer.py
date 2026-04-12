from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.tools.query_parser import QueryParser
from app.llm.router import run_llm
from app.tools.execution_planner import collect_facts
from app.schemas.models import QueryRequest as QR, DatabaseType
import logging
logger = logging.getLogger(__name__)


@dataclass
class AnalyzerConfig:
    max_query_chars: int = 20000

    @staticmethod
    def from_env() -> "AnalyzerConfig":
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

    def __init__(self, config: Optional[AnalyzerConfig] = None):
        self.config = config or AnalyzerConfig.from_env()
        self.parser = QueryParser()
        DIALECT_RULES = {
            "postgresql": "Use PostgreSQL syntax and indexing (CREATE INDEX ...). EXPLAIN is available; ANALYZE executes.",
            "mysql": "Use MySQL 8+ syntax. Use EXPLAIN/EXPLAIN ANALYZE where applicable; avoid PostgreSQL-only syntax.",
            "sqlite": "Use SQLite syntax. Avoid server-only features; indexes exist but no advanced planner hints.",
            "sqlserver": "Use T-SQL syntax. Use SQL Server indexing and query patterns; avoid LIMIT (use TOP/OFFSET).",
            "oracle": "Use Oracle SQL syntax. Use EXPLAIN PLAN FOR and DBMS_XPLAN. Use ROWNUM or FETCH FIRST for pagination.",
        }
        self.dialect_rules = DIALECT_RULES

    async def analyze(
        self,
        query: str,
        db_type: str,
        schema_info: Optional[str] = None,
        use_llm: bool = False,
        llm_provider: str = "huggingface",
        focus: str = "performance",
    ) -> Dict[str, Any]:
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
        optimized_query = self._compose_optimized_query(query, suggestions, db_type=db_type)

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

            ai_insights, ai_model, ai_error = await self._try_llm(
                llm_provider=llm_provider,
                prompt=prompt
            )

            # "used" means we actually got usable content back
            used_ai = bool(ai_insights and str(ai_insights).strip())
        
        # Build a QueryRequest-compatible object for the collector
        facts_result = None
        try:
            _req = QR(
                query=query,
                db_type=db_type if isinstance(db_type, DatabaseType) else DatabaseType(db_type),
                schema_info=schema_info or None,
                use_llm=False,  # collector never calls LLM
            )
            _facts = await collect_facts(_req)
            facts_result = _facts.dict()
        except Exception as _e:
            facts_result = {"db_type": db_type, "warnings": [f"Plan collection skipped: {str(_e)}"], "findings": []}

        return {
            "parsing_result": parsed,
            "optimization_suggestions": suggestions,
            "optimized_query": optimized_query,
            "security_issues": security_issues,
            "readability_score": readability_score,
            "facts": facts_result,            # ← ADD THIS LINE
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

    def _safe_parse(self, query: str) -> Dict[str, Any]:
        try:
            parsed = self.parser.parse(query)
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception:
            # Parsing should never kill the API; return minimal info.
            return {}

    # -------------------------
    # Heuristics
    # -------------------------

    def _heuristic_suggestions(
        self,
        query: str,
        parsed: Dict[str, Any],
        db_type: str,
        focus: str,
    ) -> List[Dict[str, Any]]:
        q = query.strip()
        ql = q.lower()

        tables = parsed.get("tables") or []
        joins = parsed.get("joins") or []
        subqueries = parsed.get("subqueries") or 0
        complexity = parsed.get("complexity_score") or 0

        suggestions: List[Dict[str, Any]] = []

        # 1) SELECT *
        if re.search(r"\bselect\s+\*\b", ql):
            suggestions.append(self._suggest(
                type_="column_selection",
                severity="medium",
                suggestion="Avoid SELECT *; specify only needed columns",
                reason="Reduces I/O and memory usage; can improve planning and network transfer",
                estimated="5–15% faster (varies)",
            ))

        # 2) Missing WHERE for SELECT (risky)
        has_select = re.search(r"\bselect\b", ql, re.IGNORECASE) is not None
        has_where = re.search(r"\bwhere\b", ql, re.IGNORECASE) is not None

        if has_select and not has_where:
            suggestions.append(self._suggest(
                type_="full_scan_risk",
                severity="medium",
                suggestion="Query has no WHERE clause; ensure this is intentional",
                reason="May scan entire table(s), especially costly on large datasets",
                estimated="Varies",
            ))


        # 3) LIKE with leading wildcard
        if re.search(r"\blike\s+'%[^']*'\b", ql):
            suggestions.append(self._suggest(
                type_="like_wildcard",
                severity="high",
                suggestion="Leading-wildcard LIKE patterns (e.g., LIKE '%abc') usually cannot use a normal B-tree index",
                reason="For substring search consider full-text search or trigram indexes (DB-specific)",
                estimated="Often large",
            ))

        # 4) Functions on columns in WHERE
        if re.search(r"\bwhere\b.*\b(lower|upper|trim|substr|substring|cast|date|coalesce)\s*\(", ql, re.DOTALL):
            suggestions.append(self._suggest(
                type_="function_in_where",
                severity="high",
                suggestion="Avoid wrapping filtered columns in functions inside WHERE when possible",
                reason="Can prevent index usage; consider computed columns or function-based indexes (DB-specific)",
                estimated="Often large",
            ))

        # 5) ORDER BY without LIMIT (for user-facing endpoints)
        if " order by " in f" {ql} " and " limit " not in f" {ql} " and "fetch first" not in ql:
            suggestions.append(self._suggest(
                type_="order_by_no_limit",
                severity="medium",
                suggestion="Consider adding LIMIT/FETCH for user-facing queries with ORDER BY",
                reason="Sorting large result sets is expensive; limiting reduces sort work",
                estimated="Varies",
            ))

        # 6) Too many joins (complexity)
        join_count = ql.count(" join ")
        if join_count >= 4:
            suggestions.append(self._suggest(
                type_="join_complexity",
                severity="high",
                suggestion=f"Query has {join_count} JOINs; review join order, keys, and filter pushdown",
                reason="Many joins can amplify row counts and increase planner complexity",
                estimated="Varies",
            ))

        # 7) Subquery count
        if isinstance(subqueries, int) and subqueries >= 2:
            suggestions.append(self._suggest(
                type_="subquery_refactor",
                severity="medium",
                suggestion="Consider refactoring nested subqueries into CTEs (WITH) or JOINs where appropriate",
                reason="Improves readability; may improve planning depending on the DB and query shape",
                estimated="Varies",
            ))

        # 8) Complexity score
        try:
            c = float(complexity)
            if c >= 70:
                suggestions.append(self._suggest(
                    type_="high_complexity",
                    severity="medium",
                    suggestion="High complexity query: consider splitting into steps, using temp tables, or pre-aggregation",
                    reason="Complex queries are harder to optimize and maintain",
                    estimated="Varies",
                ))
        except Exception:
            pass

        # 9) Index hint (generic)
        if " where " in f" {ql} " and tables:
            suggestions.append(self._suggest(
                type_="index_review",
                severity="high",
                suggestion="Review indexes on columns used in WHERE, JOIN, GROUP BY, and ORDER BY",
                reason="Correct indexes are often the biggest performance lever",
                estimated="Often large",
            ))

        # Focus-specific (extensible)
        if focus == "security":
            # Keep it small; security checks are also reported separately.
            suggestions.append(self._suggest(
                type_="security_best_practice",
                severity="medium",
                suggestion="Ensure application uses parameterized queries (no string concatenation)",
                reason="Reduces SQL injection risk and improves query plan caching",
                estimated="Risk reduction",
            ))

        return self._dedupe_suggestions(suggestions)

    def _compose_optimized_query(self, query: str, suggestions: List[Dict[str, Any]], db_type: str) -> str:
        """
        Produces a *suggested* rewrite without silently changing semantics too much.
        Uses comments to guide the user rather than forcing risky changes.
        """
        q = query.strip()
        out_lines: List[str] = []

        out_lines.append("-- Suggested optimized SQL (review before using)")
        out_lines.append(f"-- DB: {db_type}")

        # Add index suggestion comment if relevant
        if any(s.get("type") in ("index_review", "index_missing") for s in suggestions):
            out_lines.append("-- Consider: add/verify indexes on WHERE/JOIN/GROUP BY/ORDER BY columns")

        # Replace SELECT * with placeholder columns (not possible to know actual columns without schema)
        if re.search(r"\bselect\s+\*\b", q, re.IGNORECASE):
            q = re.sub(
                r"\bselect\s+\*\b",
                "SELECT /* TODO: list required columns */",
                q,
                flags=re.IGNORECASE,
            )

        out_lines.append(q)
        return "\n".join(out_lines)

    # -------------------------
    # Security / readability
    # -------------------------

    def _security_checks(self, query: str) -> List[str]:
        ql = query.lower()
        issues: List[str] = []

        # Multiple statements
        # (semi-colon inside strings is not handled; this is a heuristic)
        if ql.count(";") >= 2:
            issues.append("Multiple SQL statements detected; consider restricting to a single statement")

        # Destructive keywords
        for op in (" drop ", " truncate ", " alter ", " grant ", " revoke "):
            if op in f" {ql} ":
                issues.append(f"Potentially destructive/admin operation detected: {op.strip().upper()}")

        # SQL injection indicators (heuristic)
        if "--" in query or "/*" in query:
            issues.append("SQL comments detected; ensure input is trusted/parameterized")

        if " union " in f" {ql} ":
            issues.append("UNION detected; validate inputs and prefer parameterized queries")

        # String concatenation patterns
        if "||" in query or "concat(" in ql:
            issues.append("String concatenation detected; use parameterized queries to reduce injection risk")

        return issues

    def _readability_score(self, query: str, parsed: Dict[str, Any]) -> float:
        score = 100.0

        complexity = parsed.get("complexity_score", 0) or 0
        try:
            score -= min(float(complexity) * 0.3, 30.0)
        except Exception:
            pass

        if re.search(r"\bselect\s+\*\b", query, re.IGNORECASE):
            score -= 10

        # Penalize extremely long lines / no newlines
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
        parsed: Dict[str, Any],
        suggestions: List[Dict[str, Any]],
        focus: str,
    ) -> str:
        # Keep prompts bounded for cost/speed.
        schema_trim = (schema_info or "")[:4000]
        parsed_summary = {
            "tables": parsed.get("tables"),
            "joins": parsed.get("joins"),
            "subqueries": parsed.get("subqueries"),
            "group_by": parsed.get("group_by"),
            "order_by": parsed.get("order_by"),
            "complexity_score": parsed.get("complexity_score"),
        }

        return f"""You are a senior SQL performance engineer.

Focus: {focus}
Database: {db_type}

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

    async def _try_llm(
        self,
        llm_provider: str,
        prompt: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Centralized LLM call.
        Returns: (insights_text, model_name, error_string)
        Never raises (so /analyze doesn't 500), but never fails silently.
        """
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

    def _suggest(self, type_: str, severity: str, suggestion: str, reason: str, estimated: str) -> Dict[str, Any]:
        return {
            "type": type_,
            "severity": severity,
            "suggestion": suggestion,
            "reason": reason,
            "estimated_improvement": estimated,
        }

    def _dedupe_suggestions(self, suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out: List[Dict[str, Any]] = []
        for s in suggestions:
            key = (s.get("type"), s.get("suggestion"))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out
