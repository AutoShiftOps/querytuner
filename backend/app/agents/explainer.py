from __future__ import annotations

from typing import Any, Dict, List, Optional


# Severity ordering for sorting findings
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class QueryExplainer:
    """
    Plain-English explanation layer.

    Takes the structured output from heuristic analysis and produces
    a human-readable, severity-ranked diagnosis — independently of the LLM.
    This runs always (fast, free) and feeds into the LLM prompt as context.

    Usage:
        explainer = QueryExplainer()
        explanation = explainer.explain(query, parsed, suggestions, db_type)
    """

    def explain(
        self,
        query: str,
        parsed: Dict[str, Any],
        suggestions: List[Dict[str, Any]],
        db_type: str,
        security_issues: Optional[List[str]] = None,
    ) -> str:
        """
        Returns a markdown-formatted plain-English explanation of what
        the query does and what problems were found.
        """
        sections: List[str] = []

        # 1 — Query summary
        sections.append(self._summarize_query(query, parsed, db_type))

        # 2 — Findings
        if suggestions:
            sections.append(self._format_findings(suggestions))
        else:
            sections.append("✅ **No performance issues detected** by heuristic analysis.")

        # 3 — Security
        if security_issues:
            sections.append(self._format_security(security_issues))

        # 4 — Readability tips
        readability_tip = self._readability_tip(query, parsed)
        if readability_tip:
            sections.append(readability_tip)

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _summarize_query(self, query: str, parsed: Dict[str, Any], db_type: str) -> str:
        tables = parsed.get("tables") or []
        joins = parsed.get("joins") or []
        subqueries = parsed.get("subqueries") or 0
        complexity = parsed.get("complexity_score") or 0
        query_type = parsed.get("query_type") or "SELECT"
        group_by = parsed.get("group_by") or []
        order_by = parsed.get("order_by") or []

        lines = [f"## Query Summary ({db_type.upper()})"]

        if tables:
            lines.append(f"- **Tables accessed:** {', '.join(tables)}")
        if joins:
            join_strs = [f"{j.get('type', 'JOIN')} {j.get('table', '?')}" for j in joins]
            lines.append(f"- **Joins:** {', '.join(join_strs)}")
        if group_by:
            lines.append(f"- **Grouped by:** {', '.join(str(c) for c in group_by)}")
        if order_by:
            lines.append(f"- **Ordered by:** {', '.join(str(c) for c in order_by)}")
        if subqueries > 0:
            lines.append(f"- **Nested subqueries:** {subqueries}")

        complexity_label = (
            "Low" if complexity < 30
            else "Medium" if complexity < 60
            else "High" if complexity < 80
            else "Very High"
        )
        lines.append(f"- **Complexity score:** {complexity:.0f}/100 ({complexity_label})")

        return "\n".join(lines)

    def _format_findings(self, suggestions: List[Dict[str, Any]]) -> str:
        sorted_suggestions = sorted(
            suggestions,
            key=lambda s: _SEVERITY_ORDER.get(s.get("severity", "low"), 99)
        )

        lines = ["## Performance Findings"]
        for i, s in enumerate(sorted_suggestions, 1):
            severity = s.get("severity", "low").upper()
            emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(severity, "⚪")
            lines.append(f"\n### {i}. {emoji} [{severity}] {s.get('type', '').replace('_', ' ').title()}")
            lines.append(f"**Issue:** {s.get('suggestion', '')}")
            lines.append(f"**Why it matters:** {s.get('reason', '')}")
            estimated = s.get("estimated_improvement", "")
            if estimated:
                lines.append(f"**Estimated impact:** {estimated}")

        return "\n".join(lines)

    def _format_security(self, issues: List[str]) -> str:
        lines = ["## 🛡️ Security Observations"]
        for issue in issues:
            lines.append(f"- ⚠️ {issue}")
        return "\n".join(lines)

    def _readability_tip(self, query: str, parsed: Dict[str, Any]) -> Optional[str]:
        tips: List[str] = []

        if query.count("\n") < 2:
            tips.append("Format your query across multiple lines — it improves readability and diff clarity in code review.")

        subqueries = parsed.get("subqueries") or 0
        if subqueries >= 2:
            tips.append(
                "This query has multiple nested subqueries. "
                "Consider extracting them into CTEs (`WITH` clauses) for clarity and potential planner benefits."
            )

        complexity = parsed.get("complexity_score") or 0
        if complexity >= 60:
            tips.append(
                "High complexity queries are harder to debug and maintain. "
                "Consider breaking this into intermediate steps or materialized views."
            )

        if not tips:
            return None

        lines = ["## 📖 Readability Tips"]
        for t in tips:
            lines.append(f"- {t}")
        return "\n".join(lines)
