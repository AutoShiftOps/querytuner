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

## 🗓️ Phase 1 — Core Engine Hardening (Week 2–3, May 5–16)

**Goal:** Make the heuristic engine production-grade. Zero false positives.
**Exit criteria:** 20 real-world queries tested, all suggestions accurate.

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

---

## 🗓️ Phase 2 — Schema-Aware Analysis (Week 4–5, May 19–30)

**Goal:** Users can paste DDL and get column-specific advice instead of generic warnings.
**Exit criteria:** Index suggestion names the actual column (`idx_orders_created_at`).

| Day | Task | Priority |
|---|---|---|
| Day 8 | Add `schema_info` text area to QueryInput.jsx (collapsible) | 🟡 Medium |
| Day 9 | `query_parser.py` — extract column names from WHERE/JOIN/GROUP BY | 🔴 High |
| Day 10 | `sql_analyzer.py` — cross-reference parsed columns vs schema DDL | 🔴 High |
| Day 11 | `optimizer.py` — generate named CREATE INDEX statements from schema | 🔴 High |
| Day 12 | `explainer.py` — reference actual table/column names in findings | 🟡 Medium |
| Day 13 | LangChain text splitter — chunk large DDL schemas before LLM call | 🟡 Medium |

---

## 🗓️ Phase 3 — LangGraph Agentic Pipeline (Week 6–8, June 2–20)

**Goal:** Replace single analyze() call with a resumable multi-node agent graph.
**Exit criteria:** LangGraph trace visible in LangSmith for each analysis.

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

| Task | Priority |
|---|---|
| Query history — save + replay past analyses per user | 🔴 High |
| Team workspaces — share queries + results with teammates | 🔴 High |
| Slack integration — `/querytuner analyze <sql>` slash command | 🟡 Medium |
| VS Code extension — analyze SQL from editor (Phase 5 stretch) | 🟡 Medium |
| Live DB connection — connect real DB for EXPLAIN plan (not paste-in) | 🔴 High |
| PDF/CSV export of analysis report | 🟡 Medium |
| OpenAI GPT-4o upgrade for Pro tier | 🔴 High |
| Custom branding / white-label for Enterprise tier | 🟢 Low |

---

## 📊 Milestone Summary

| Phase | Timeline | Key Deliverable |
|---|---|---|
| ✅ Phase 0 — MVP | Apr 2026 | Live product at querytuner.com |
| 🔄 Phase 1 — Engine | May 5–16 | 8 heuristics, 20 pytest fixtures, CI green |
| Phase 2 — Schema | May 19–30 | Column-specific index suggestions |
| Phase 3 — Agents | Jun 2–20 | LangGraph pipeline + LangSmith traces |
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
