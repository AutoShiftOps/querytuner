from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.agents.explainer import QueryExplainer
from app.agents.optimizer import QueryOptimizer
from app.llm.router import call_llm
from app.schemas.models import DatabaseType
from app.schemas.models import QueryRequest as QR
from app.tools.execution_planner import collect_facts
from app.tools.index_recommender import IndexRecommender
from app.tools.query_parser import QueryParser
from app.utils.dialect_config import get_llm_context

logger = logging.getLogger(__name__)

# Three-tier evidence labels for heuristic (non-index-recommender) findings.
# Deterministic: the pattern is always correct regardless of data distribution.
# Everything else falls back to "needs-runtime-evidence" — pattern-based,
# cannot be confirmed without live DB stats or an EXPLAIN plan.
_DETERMINISTIC_TYPES = frozenset(
    {
        "cartesian_join",
        "like_wildcard",
        "function_in_where",
        "implicit_cast",
        "subquery_to_join",
        "column_selection",
    }
)


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
        - openai using OPENAI_API_KEY
    """

    def __init__(self, config: AnalyzerConfig | None = None):
        self.config = config or AnalyzerConfig.from_env()
        self.parser = QueryParser()
        self.optimizer = QueryOptimizer()
        self.explainer = QueryExplainer()
        self.index_recommender = IndexRecommender()

    async def analyze(
        self,
        query: str,
        db_type: str,
        schema_info: str | None = None,
        use_llm: bool = False,
        llm_provider: str = "huggingface",
        focus: str = "performance",
        explain_plan: str | None = None,  # Issue #60: EXPLAIN plan paste-in
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ValueError("Query is empty")

        if len(query) > self.config.max_query_chars:
            raise ValueError(f"Query too large (>{self.config.max_query_chars} chars)")

        schema_info = (schema_info or "").strip()
        explain_plan = (explain_plan or "").strip()
        focus = (focus or "performance").strip().lower()
        llm_provider = (llm_provider or "huggingface").strip().lower()

        parsed = self._safe_parse(query)
        security_issues = self._security_checks(query)
        readability_score = self._readability_score(query, parsed)
        suggestions = self._heuristic_suggestions(
            query,
            parsed,
            db_type=db_type,
            focus=focus,
            schema_info=schema_info,  # Phase 2: pass schema through
        )
        optimized_query = self.optimizer.rewrite(query, suggestions, db_type=db_type)

        plain_explanation = self.explainer.explain(
            query=query,
            parsed=parsed,
            suggestions=suggestions,
            db_type=db_type,
            security_issues=security_issues,
            schema_info=schema_info,  # Phase 2: pass schema through
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
                explain_plan=explain_plan,  # Issue #60: pass EXPLAIN plan into LLM context
                parsed=parsed,
                suggestions=suggestions,
                focus=focus,
            )
            # Issue #74 fix: pass db_type so router injects dialect context
            ai_insights, ai_model, ai_error = await self._try_llm(
                llm_provider=llm_provider,
                prompt=prompt,
                db_type=db_type,
            )
            used_ai = bool(ai_insights and str(ai_insights).strip())

        facts_result = None
        try:
            _req = QR(
                query=query,
                db_type=db_type if isinstance(db_type, DatabaseType) else DatabaseType(db_type),
                explain_plan=explain_plan or None,
                schema_info=schema_info or None,
                use_llm=False,
            )
            _facts = await collect_facts(_req)
            facts_result = _facts.model_dump()
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
        schema_info: str | None = None,
    ) -> list[dict[str, Any]]:
        q = query.strip()
        ql = q.lower()

        subqueries = parsed.get("subqueries") or 0
        complexity = parsed.get("complexity_score") or 0

        suggestions: list[dict[str, Any]] = []

        # 1) SELECT *
        if re.search(r"\bselect\s+\*", ql):
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

        # 3) LIKE with leading wildcard (ILIKE included — PostgreSQL case-insensitive LIKE)
        if re.search(r"\bi?like\s+'%[^']*'", ql):
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
        # Uses the parser's top-level order_by (excludes ORDER BY inside window
        # function OVER(...) clauses) instead of a raw whole-string regex.
        if (
            bool(parsed.get("order_by"))
            and not bool(re.search(r"\blimit\b", ql))
            and not bool(re.search(r"\bfetch\s+first\b", ql))
        ):
            suggestions.append(
                self._suggest(
                    type_="order_by_no_limit",
                    severity="medium",
                    suggestion="Consider adding LIMIT/FETCH FIRST for user-facing queries with ORDER BY",
                    reason="Sorting large result sets is expensive; limiting reduces sort work",
                    estimated="Varies",
                )
            )

        # 6) Too many JOINs
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

        # 6.5) Cartesian JOIN — JOIN without ON or USING
        cartesian_joins = re.findall(
            r"\bJOIN\s+\S+(?:\s+\w+)?\s*(?!ON\b|USING\b)(?=\s+(?:JOIN|WHERE|GROUP|ORDER|LIMIT|FETCH|$)|\s*;|$)",
            q,
            re.IGNORECASE | re.DOTALL,
        )
        if cartesian_joins:
            suggestions.append(
                self._suggest(
                    type_="cartesian_join",
                    severity="critical",
                    suggestion=(
                        f"Cartesian JOIN detected ({len(cartesian_joins)} occurrence(s)) — "
                        f"JOIN used without ON or USING clause"
                    ),
                    reason=(
                        "A JOIN without ON/USING produces a cartesian product: every row in the left "
                        "table is matched with every row in the right table. On tables with 1k rows each "
                        "this returns 1,000,000 rows. Almost always a bug."
                    ),
                    estimated="Query may return exponentially more rows than intended",
                )
            )

        # 7) Subquery count — generic refactor suggestion
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

        # 8) Issue #25: implicit_cast — detect type coercion patterns in WHERE
        # Catches: PostgreSQL cast operator (::), SQL Server CONVERT(type, col),
        # and ID columns compared to string literals (e.g. WHERE user_id = '123')
        _implicit_cast_patterns = [
            # PostgreSQL cast operator in WHERE: col::type
            (r"\bwhere\b.*[\w.]+\s*::\s*\w+", "PostgreSQL :: cast operator in WHERE prevents index use"),
            # SQL Server / MySQL CONVERT(type, col) — already caught by function_in_where,
            # but flag explicitly here for type-coercion context
            (r"\bconvert\s*\(\s*\w+\s*,\s*[\w.]+\s*\)", "CONVERT() performs an implicit type cast"),
            # ID/FK columns compared to string literals — likely implicit int→varchar cast
            (
                r"\b(user_id|customer_id|order_id|product_id|account_id|tenant_id)\s*=\s*'[^']+'",
                "ID column compared to string literal — implicit cast may prevent index use",
            ),
            # Numeric literal compared to column that looks like a string/code column
            (
                r"\b(status|code|flag|type|kind|role|tier)\s*=\s*\d+\b",
                "String-like column compared to numeric literal — implicit cast may prevent index use",
            ),
        ]

        implicit_cast_reasons = []
        for pattern, reason in _implicit_cast_patterns:
            if re.search(pattern, ql, re.IGNORECASE | re.DOTALL):
                implicit_cast_reasons.append(reason)

        if implicit_cast_reasons:
            suggestions.append(
                self._suggest(
                    type_="implicit_cast",
                    severity="high",
                    suggestion=(
                        "Implicit or explicit type cast detected in WHERE — "
                        "may prevent index use and cause full scans"
                    ),
                    reason=(
                        f"{implicit_cast_reasons[0]}. "
                        "Ensure the comparison value matches the column's data type to allow index seeks."
                    ),
                    estimated="Often significant — removes type-coercion full scan",
                )
            )

        # 9) Issue #26: subquery_to_join — flag correlated subqueries in SELECT list
        # Pattern: SELECT (...) , ... where the subquery references outer columns
        # Detect subqueries directly in the SELECT clause (not just in WHERE)
        select_clause = self._extract_select_clause(q)
        select_subquery_count = len(re.findall(r"\bSELECT\b", select_clause, re.IGNORECASE))
        # select_subquery_count > 0 means there is a nested SELECT in the SELECT list
        if select_subquery_count > 0:
            suggestions.append(
                self._suggest(
                    type_="subquery_to_join",
                    severity="high",
                    suggestion=(
                        f"Correlated subquery detected in SELECT clause "
                        f"({select_subquery_count} occurrence(s)) — consider rewriting as a JOIN or CTE"
                    ),
                    reason=(
                        "A subquery in the SELECT list executes once per row of the outer query. "
                        "On a 10,000-row result set this means 10,000 separate lookups. "
                        "A LEFT JOIN or CTE is evaluated once and is far more efficient."
                    ),
                    estimated="Often 10x–100x faster for large result sets",
                )
            )

        # 10) Complexity score
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

        # 11) Column-level index recommendations
        index_suggestions = self.index_recommender.recommend(
            query=q,
            parsed=parsed,
            db_type=db_type,
            schema_info=schema_info,  # Phase 2: pass schema through
        )
        suggestions.extend(index_suggestions)

        # Boost complexity score based on HIGH index findings
        high_index_count = sum(1 for s in index_suggestions if s.get("severity") == "high")
        if high_index_count > 0:
            base_score = float(parsed.get("complexity_score") or 0)
            parsed["complexity_score"] = min(100.0, base_score + (high_index_count * 8.0))

        # 12) Focus-specific
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
    # Helpers
    # -------------------------

    def _extract_select_clause(self, query: str) -> str:
        """Extract everything between SELECT and FROM at top level."""
        q = re.sub(r"\s+", " ", query).strip()
        ql = q.lower()
        sel = ql.find("select")
        if sel == -1:
            return ""
        frm = ql.find(" from ", sel)
        if frm == -1:
            return q[sel + 6 :]
        return q[sel + 6 : frm]

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
        explain_plan: str = "",  # Issue #60
    ) -> str:
        schema_trim = (schema_info or "")[:4000]
        explain_trim = (explain_plan or "")[:3000]  # Issue #60: include EXPLAIN plan in prompt

        parsed_summary = {
            "tables": parsed.get("tables"),
            "joins": parsed.get("joins"),
            "subqueries": parsed.get("subqueries"),
            "group_by": parsed.get("group_by"),
            "order_by": parsed.get("order_by"),
            "complexity_score": parsed.get("complexity_score"),
        }

        # Issue #74: use dialect_config context instead of inline dict
        dialect_context = get_llm_context(db_type)

        explain_section = f"\nEXPLAIN plan output (provided by user):\n{explain_trim}\n" if explain_trim else ""

        return f"""{dialect_context}

Focus: {focus}

Schema (optional, may be partial):
{schema_trim}

SQL:
{query}
{explain_section}
Parsed summary:
{parsed_summary}

Heuristic suggestions already found:
{suggestions}

Tasks:
1) Provide the most impactful performance improvements (prioritized).
2) Recommend concrete indexes (include dialect-correct CREATE INDEX statements).
3) Provide a rewritten query if it can reduce cost (CTEs/JOIN refactors/filters).
4) Call out any risky assumptions (unknown cardinalities, missing schema).
Keep it concise and actionable.
"""

    async def _try_llm(
        self,
        llm_provider: str,
        prompt: str,
        db_type: str = "postgresql",  # Issue #74 fix: pass to router
    ) -> tuple[str | None, str | None, str | None]:
        """
        Bug fix: call_llm now returns a dict, not a tuple.
        Previous code: text, model, err = await call_llm(...) — this was broken.
        """
        try:
            result = await call_llm(
                prompt=prompt,
                provider=llm_provider,
                db_type=db_type,  # Issue #74: dialect context injection
            )
            text = result.get("text")
            model = result.get("model")
            err = result.get("error")

            if not text or not str(text).strip():
                return None, model, err or "LLM returned empty response"
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
            "evidence_level": ("deterministic" if type_ in _DETERMINISTIC_TYPES else "needs-runtime-evidence"),
        }

    def _dedupe_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set = set()
        out: list[dict[str, Any]] = []
        for s in suggestions:
            key = (s.get("type"), s.get("suggestion"))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out
