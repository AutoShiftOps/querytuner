# QueryTuner — Revised Calibrated Roadmap
**Updated:** May 1, 2026 | **Domain:** querytuner.com | **Stage:** Post-MVP → Enterprise Alpha

---

## ✅ Completed — Day 1 (May 1, 2026)

| # | Task | Status |
|---|---|---|
| 1 | README.md rewritten as product page (not learning diary) | ✅ Done |
| 2 | `sql_analyzer.py` — fixed LIKE wildcard `\b` regex bug | ✅ Done |
| 3 | `sql_analyzer.py` — fixed SELECT * `\b` regex bug | ✅ Done |
| 4 | `sql_analyzer.py` — expanded function_in_where pattern (YEAR, MONTH, etc.) | ✅ Done |
| 5 | `optimizer.py` — implemented full rewrite engine (YEAR → BETWEEN, SELECT * placeholder) | ✅ Done |
| 6 | `explainer.py` — implemented plain-English diagnosis layer | ✅ Done |
| 7 | `main.py` — wired plain_explanation into API response | ✅ Done |
| 8 | Vite migration — replaced CRA (react-scripts) | ✅ Done |
| 9 | Dependabot alerts: 76 → 0 | ✅ Done |
| 10 | react-markdown — AI insights + Query Diagnosis rendered as formatted markdown | ✅ Done |
| 11 | Sample Queries panel — 9 queries (Beginner / Intermediate / Advanced) | ✅ Done |
| 12 | explainer.py markdown spacing fix — findings no longer jumbled | ✅ Done |
| 13 | CI/CD — ruff format, eslint, pre-commit hooks all green | ✅ Done |
| 14 | Branch protection + dependabot.yml configured | ✅ Done |

---

## ✅ Phase 1 — Core Engine Hardening (Week 2–3, May 5–16)

**Goal:** Make the heuristic engine production-grade. Zero false positives.
**Exit criteria:** 20 real-world queries tested, all suggestions accurate.
**Status:** Exceeded — engine now covers **16 heuristic rules** with 102 passing tests.

| Day | Task | Priority |
|---|---|---|
| Day 2 | Add `index_review` heuristic — detect missing indexes on JOIN/WHERE/GROUP BY cols | 🔴 High |
| Day 2 | Add `implicit_cast` heuristic — detect type mismatch in WHERE (e.g. int col vs string literal) | 🔴 High |
| Day 3 | Add `cartesian_join` heuristic — detect JOINs without ON clause | 🔴 High |
| Day 3 | Add `subquery_to_join` heuristic — flag correlated subqueries in SELECT | 🟡 Medium |
| Day 4 | Fix `optimizer.py` — implement LIMIT rewrite for ORDER BY without LIMIT | 🔴 High |
| Day 4 | Fix `optimizer.py` — implement LIKE leading wildcard comment | 🟡 Medium |
| Day 5 | `query_parser.py` audit — ensure GROUP BY, ORDER BY, subquery count are always populated | 🔴 High |
| Day 6 | Write 20 test fixtures (query → expected suggestions) using pytest | 🟡 Medium |
| Day 7 | Wire pytest into GitHub Actions CI | 🟡 Medium |

**Later additions (July 2026) — 4 new heuristics, bringing the total from 12 to 16:**

| Task | Status |
|---|---|
| `not_in_nullable` heuristic — NOT IN with a nullable subquery returns zero rows | ✅ Done |
| `case_in_predicate` heuristic — CASE expression in WHERE prevents index use | ✅ Done |
| `or_expansion` heuristic — OR across different columns may force a full scan | ✅ Done |
| `cte_multiple_references` heuristic — CTE referenced 2+ times may re-execute per reference | ✅ Done |

---

## ➕ Phase 1.5 — Supabase setup + persistence (Week 2-3, May 7–10)

**Goal:** Sharable report link..
**Exit criteria:** Generated report links are accessible and functional.

| Issue | Task | Priority |
|---|---|---|
| #68 | Add Supabase persistence to /analyze endpoint | 🔴 High |
| #69 | Add shareable /report/:id route and ReportPage | 🔴 High |
| #70 | Add ShareButton with clipboard copy to ResultsPanel | 🔴 High |

---

## ➕ Phase 1.6 — UI Shell (Week 3-4, May 19–21)

**Goal:** App shell matches enterprise-grade visual standard before schema work begins.
**Exit criteria:** Consistent font, two-column layout, sticky nav, toast feedback.

| Issue | Task | Priority |
|---|---|---|
| #86 | Set IBM Plex Sans as global font via tailwind.config.js + index.html | 🔴 High |
| #87 | Add sticky Header with nav links and GitHub star CTA | 🔴 High |
| #88 | Add Hero value proposition strip above query tool | 🟡 Medium |
| #89 | Add Toast notification system — wire to analyze + share actions | 🔴 High |
| #90 | Add Footer with API Docs, GitHub, Roadmap, license links | 🟢 Low |
| #91 | Implement two-column AppLayout — results panel on right | 🔴 High |
| #92 | add GA4 event tracking via centralized analytics.js utility | 🔴 High |

---

## ✅ Phase 1.7 — Dialect Intelligence (Completed)

**Goal:** Every recommendation, DDL statement, and LLM output is dialect-correct.
Generic output that could mislead engineers using Oracle, SQL Server, or SQLite is eliminated.

**Exit criteria met:** Same query run against all 5 dialects produces distinct DDL,
rewrites, and maintenance commands in each response.

| Issue | Task | Status |
|---|---|---|
| #72 | Dialect-aware index DDL generator — CONCURRENTLY / ALTER TABLE / NOLOGGING / ONLINE=ON / IF NOT EXISTS | ✅ Done |
| #73 | Dialect-aware query optimizer — YEAR() rewrites, LOWER() hints, pagination per DB | ✅ Done |
| #74 | Dialect-aware LLM prompts — DB-specific system context in HF and OpenAI calls | ✅ Done |
| #75 | Dialect-aware maintenance recommendations — VACUUM / ANALYZE TABLE / DBMS_STATS / UPDATE STATISTICS | ✅ Done |

**Files added / modified:**
- `backend/app/utils/dialect_config.py` — new: single source of truth for all dialect config
- `backend/app/tools/index_recommender.py` — wired: dialect DDL via get_index_ddl()
- `backend/app/agents/optimizer.py` — wired: dialect rewrites + pagination
- `backend/app/agents/explainer.py` — wired: maintenance section + get_llm_context()
- `backend/app/llm/router.py` — wired: db_type param + dialect system prompt (OpenAI)
- `backend/app/llm/hf_client.py` — wired: db_type param + dialect system prompt (HF)

---

## ✅ Phase 2 — Schema-Aware Analysis (Week 4–5, May 19–30)

**Goal:** Users can paste DDL and get column-specific advice instead of generic warnings.
**Exit criteria met:** Index suggestion names the actual column (`idx_orders_created_at`).

| Day | Task | Priority |
|---|---|---|
| Day 8 | Add `schema_info` text area to QueryInput.jsx (collapsible) | 🟡 Medium |
| Day 9 | `query_parser.py` — extract column names from WHERE/JOIN/GROUP BY | 🔴 High |
| Day 10 | `sql_analyzer.py` — cross-reference parsed columns vs schema DDL | 🔴 High |
| Day 11 | `optimizer.py` — generate named CREATE INDEX statements from schema | 🔴 High |
| Day 12 | `explainer.py` — reference actual table/column names in findings | 🟡 Medium |
| Day 13 | LangChain text splitter — chunk large DDL schemas before LLM call | 🟡 Medium |

---

## ✅ Post-Phase 2 — Report Page & Evidence System Hardening (July 2026)

**Goal:** Close the gap between the main app and the shareable report page, and replace
the binary confirmed/estimated flag with an honest three-tier evidence system.

| Task | Commit | Status |
|---|---|---|
| Three-tier evidence labels (`deterministic` / `schema-verified` / `needs-runtime-evidence`) | `1fcb82a0` | ✅ Done |
| Rollback DDL per dialect on all index recommendations | `ff9b05d` | ✅ Done |
| Privacy warnings on share button and report page | `0735519` | ✅ Done |
| `schema_verified` rename (replaces `confirmed` — doesn't imply the planner will use the index) | `2e3bad58` | ✅ Done |
| Report page brought to full parity with the main app (evidence badges, DDL blocks, rollback toggles, Query Diagnosis) | `6eb3305c` | ✅ Done |
| AI Insights persisted and rendered on the shareable report page | `05ea8c37` | ✅ Done |
| `findKey()` resilient AI JSON parser — handles key-name variation across LLM providers | `e5197fb1` | ✅ Done |
| CSS specificity fix for report page (`:where()` reset) | `530f278` | ✅ Done |

---

## ⏭ Phase 3 — LangGraph Agentic Pipeline (deliberately deferred — post revenue)

**Goal:** Replace single analyze() call with a resumable multi-node agent graph.
**Exit criteria:** LangGraph trace visible in LangSmith for each analysis.
**Status:** Not started. Deliberately deferred until after Phase 4 (monetization) ships —
no `langgraph` usage exists in the codebase yet. Issues #39–45 remain open and untouched.

| Day | Task | Priority |
|---|---|---|
| Day 14 | Define LangGraph state schema (QueryState dataclass) | 🔴 High |
| Day 15 | ParseNode — wrap QueryParser as LangGraph node | 🔴 High |
| Day 16 | PlanNode — wrap execution_planner as LangGraph node | 🔴 High |
| Day 17 | ExplainNode — wrap QueryExplainer as LangGraph node | 🔴 High |
| Day 18 | OptimizeNode — wrap QueryOptimizer as LangGraph node | 🔴 High |
| Day 19 | VerifyNode — NEW: validates rewritten SQL is semantically equivalent | 🟡 Medium |
| Day 20 | Wire LangGraph graph into SQLAnalyzerAgent.analyze() | 🔴 High |
| Day 21 | LangSmith tracing — add LANGCHAIN_API_KEY to Render env vars | 🟡 Medium |

---

## 🗓️ Phase 4 — Monetization Infrastructure (Week 9–10, June 23 – July 4)

**Goal:** Free vs Pro tier functional. First paid user possible.
**Exit criteria:** Stripe checkout works end-to-end in production.

| Day | Task | Priority |
|---|---|---|
| Day 22 | Define Free tier limits (10 analyses/day, no schema, no AI) | 🔴 High |
| Day 23 | Define Pro tier ($19/mo — unlimited, schema, GPT-4o-mini, history) | 🔴 High |
| Day 24 | Auth — add Clerk or Supabase Auth (email + Google OAuth) | 🔴 High |
| Day 25 | Backend — add usage tracking table (user_id, timestamp, query_hash) | 🔴 High |
| Day 26 | Backend — enforce rate limits per tier from DB | 🔴 High |
| Day 27 | Stripe — add checkout session endpoint | 🔴 High |
| Day 28 | Frontend — upgrade/pricing page | 🟡 Medium |
| Day 29 | Frontend — login/logout flow + protected routes | 🔴 High |

---

## 🗓️ Phase 5 — Enterprise Features (July, Week 11–14)

**Goal:** Features that justify $299/mo team plan to engineering managers.
**Exit criteria:** One pilot customer using the tool on their real queries.

| Issue | Task | Priority |
|---|---|---|
| #54 | Query history — save + replay past analyses per user | 🔴 High |
| #55 | Team workspaces — share queries + results with teammates | 🔴 High |
| #56 | Slack integration — `/querytuner analyze <sql>` slash command | 🟡 Medium |
| #59 | VS Code extension — analyze SQL from editor (Phase 5 stretch) | 🟡 Medium |
| #57 | Live DB connection — connect real DB for EXPLAIN plan (not paste-in) | 🔴 High |
| #58 | PDF/CSV export of analysis report | 🟡 Medium |
| — | OpenAI GPT-4o upgrade for Pro tier | 🔴 High |
| — | Custom branding / white-label for Enterprise tier | 🟢 Low |
| #61 | EXPLAIN plan parser — parse PostgreSQL EXPLAIN output | 🔴 High |
| #62 | EXPLAIN plan parser — parse MySQL EXPLAIN output | 🔴 High |
| #63 | Cross-reference heuristics with parsed EXPLAIN plan | 🔴 High |
| #115 | Batch workload analysis — detect conflicting indexes across multiple queries | 🔴 High |
| #116 | URL expiration and deletion for shareable reports | 🟡 Medium |
| #117 | Column order reasoning in composite index DDL proposals | 🟢 Low |
| #118 | Write and storage cost estimate per index recommendation | 🟡 Medium |
| #119 | Parameter sniffing detection — compiled vs runtime parameter values | 🔴 High |
| #120 | Batch query input from Query Store / pg_stat_statements export | 🔴 High |

---

## 📊 Milestone Summary

| Phase | Timeline | Key Deliverable |
|---|---|---|
| ✅ Phase 0 — MVP | Apr 2026 | Live product at querytuner.com |
| ✅ Phase 1.5 — MVP | May 2026 | Supabase setup + persistence |
| ✅ Phase 1.6 — MVP | May 19-21 | UI Shell |
| ✅ Phase 1.7 — Dialect Intelligence | May–Jun 2026 | Dialect-correct DDL, rewrites, LLM prompts |
| ✅ Phase 1 — Engine | May 5–16 | 16 heuristics, 102 passing tests, CI green |
| ✅ Phase 2 — Schema | May 19–30 | Column-specific index suggestions |
| ✅ Post-Phase 2 — Hardening | Jul 2026 | Evidence system, rollback DDL, report page parity |
| ⏭ Phase 3 — Agents (deferred) | Jun 2–20 | LangGraph pipeline + LangSmith traces |
| Phase 4 — Monetize | Jun 23–Jul 4 | Stripe + Auth + Free/Pro tiers |
| Phase 5 — Enterprise | July | Team plan, Slack, live DB |

---

## 💡 Tracking Recommendation

### Daily (5 min)
- One GitHub commit minimum — even a 1-line fix counts
- Update the task you worked on to ✅ in your tracking doc

### Weekly (30 min — every Friday)
- Review what moved from 🔄 to ✅
- Identify the single biggest blocker
- Write one sentence in a `DEVLOG.md` committed to the repo

### Monthly (1 hour — first Monday)
- Review phase exit criteria — are you on track?
- Update the roadmap for the next phase
- Screenshot querytuner.com — visual progress record for EB-1A petition

### Tools
| Need | Tool | Why |
|---|---|---|
| Task tracking | **GitHub Projects (Kanban)** | Free, lives next to code, shows activity graph |
| Daily log | **DEVLOG.md in repo** | Every commit is timestamped evidence |
| Phase planning | **GitHub Milestones** | Links issues to phases automatically |
| Weekly review | **Notion or plain .md** | Low friction |
