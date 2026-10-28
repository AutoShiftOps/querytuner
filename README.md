<p align="center">
  <img src="assets/logo/querytuner-mark.svg" alt="QueryTuner logo" width="96" height="96" />
</p>

# QueryTuner — AI-Powered SQL Query Diagnostics

[![Version](https://img.shields.io/badge/version-0.3.0-blue)](CHANGELOG.md)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi)](https://api.querytuner.com/docs)
[![Frontend](https://img.shields.io/badge/frontend-React-61DAFB?logo=react)](https://querytuner.com)
[![AI](https://img.shields.io/badge/AI-Claude%20%7C%20OpenAI-D97757)](https://docs.claude.com)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-live-brightgreen)](https://querytuner.com)

> Only 0.3% of developers are database administrators.<br>
> The SQL performance tools that exist were built for them.<br>
> QueryTuner is for the other 99.7%.
>
> *— Stack Overflow Developer Survey 2024, 65,000+ developers*

**No database connection required. Paste-in and analyze.**

🔗 **Live Demo → [querytuner.com](https://querytuner.com)**
📖 **API Docs → [/docs](https://api.querytuner.com/docs)**

---

## What It Does

QueryTuner analyzes SQL queries in two layers:

1. **Heuristic Engine** (always on, instant) — rule-based detection of common performance
   anti-patterns: missing indexes, leading wildcards, functions in WHERE clauses, SELECT *,
   unbounded ORDER BY, and more.

2. **AI Layer** (optional) — powered by Anthropic Claude (default) or OpenAI
   (`gpt-4o-mini`). Generates CTE rewrites, CREATE INDEX statements with justification,
   and plain-English diagnosis.

---

## Features

- 🗄️ **5 Database Dialects** — PostgreSQL, MySQL, Oracle, SQL Server, SQLite
- ⚡ **Heuristic Engine** — 17 deterministic rules, always available, no external API calls required
- 🗂️ **Schema-Aware Analysis** — paste `CREATE TABLE` DDL and index recommendations upgrade from
  estimated to **confirmed**, resolved against your real table and column names
- 🔧 **Dialect-Correct Index DDL** — `CREATE INDEX CONCURRENTLY` (PostgreSQL),
  `ALTER TABLE ... ADD INDEX` (MySQL), `NOLOGGING` (Oracle), `WITH (ONLINE=ON)` (SQL Server)
- 🤖 **Dual AI Provider** — Anthropic Claude (default; 3 free AI analyses/day when signed in) or OpenAI (Pro), with structured JSON output
  (falls back to readable plain text if the model doesn't return JSON)
- 🔍 **Severity-Ranked Findings** — Critical → High → Medium → Low
- 📋 **Rewritten Query / Targeted Fixes** — a full AI rewrite for smaller, single-statement
  queries; individually-verifiable before/after "Targeted Fixes" for large (>3000 char) or
  multi-statement queries, where a single rewritten block risks silently changing results.
  A separate deterministic "Annotated Query" always adds safe inline comments only — it
  never restructures the query, and is intentionally not labeled as a rewrite
- 🔗 **Shareable Reports** — every analysis gets a permanent `/report/:id` URL
- 📈 **Analytics** — Google Analytics 4 event tracking on every user action
- 🛡️ **Security Scanning** — detects SQL injection patterns and unsafe constructs
- 📊 **Readability Score** — quantifies query clarity for code review
- 🔒 **Client-side query sanitizer** — replace proprietary table and column names with
  dummy values before analysis runs. Your real schema names never leave your browser.
  One click restores original names in DDL output after analysis. Substitution map
  lives in browser memory only — gone on page refresh, never persisted.
- 🔌 **REST API** — integrable into CI/CD pipelines and developer tooling
- 🚫 **No DB Connection Needed** — works entirely from pasted query text (schema DDL is optional,
  only needed to unlock confirmed mode)

---

## Live API

```bash
# Analyze a query (heuristics only, no API key needed)
curl -X POST https://api.querytuner.com/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC",
    "db_type": "postgresql",
    "use_llm": false
  }'

# With AI insights (requires ANTHROPIC_API_KEY on server)
curl -X POST https://api.querytuner.com/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT u.id, COUNT(o.id) FROM users u LEFT JOIN orders o ON o.user_id = u.id WHERE YEAR(o.created_at) = 2025 GROUP BY u.id",
    "db_type": "mysql",
    "use_llm": true,
    "llm_provider": "anthropic"
  }'
```

**Supported `db_type` values:** `postgresql` · `mysql` · `oracle` · `sqlserver` · `sqlite`
**Supported `llm_provider` values:** `anthropic` · `openai` (`huggingface` is accepted for old clients and treated as `anthropic`)

### Example Response

```json
{
  "optimization_suggestions": [
    {
      "type": "function_in_where",
      "severity": "high",
      "suggestion": "Avoid wrapping filtered columns in functions inside WHERE",
      "reason": "YEAR(created_at) prevents index usage on the created_at column",
      "estimated_improvement": "High — use range condition instead"
    }
  ],
  "ai_insights": "...",
  "optimized_query": "...",
  "readability_score": 83.5,
  "analysis_time_ms": 5.4,
  "used_ai": true,
  "ai_model": "claude-haiku-5-5"
}
```

Full schema at [`/docs`](https://api.querytuner.com/docs).

---

## Architecture

```
querytuner.com (Vercel)          api.querytuner.com (Render)
     │                                          │
     │  POST /analyze                           │
     └─────────────────────────────────────────►│
                                                │
                                    ┌───────────▼──────────────┐
                                    │   FastAPI + SQLAnalyzer  │
                                    │   ┌────────────────────┐ │
                                    │   │  Heuristic Engine  │ │  ← always runs
                                    │   │  (query_parser.py) │ │
                                    │   └────────┬───────────┘ │
                                    │            │             │
                                    │   ┌────────▼───────────┐ │
                                    │   │    LLM Router      │ │  ← optional
                                    │   │  Claude │ OpenAI   │ │
                                    │   │  (Hugging Face     │ │
                                    │   │   removed Oct 2026)│ │
                                    │   └────────────────────┘ │
                                    └──────────────────────────┘
```

**Stack:**
- Backend: Python · FastAPI · Pydantic · sqlparse · LangChain
- Frontend: React · Tailwind CSS · Axios · Lucide Icons
- AI: Anthropic Messages API (Claude) · OpenAI
- Deploy: Render (backend) · Vercel (frontend)

---

## Run Locally

**Prerequisites:** Python 3.11+, Node.js 18+

```bash
# Clone
git clone https://github.com/AutoShiftOps/querytuner
cd querytuner

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open `http://localhost:3000` (this project pins Vite's dev server port in `vite.config.js`;
it does not use Vite's default 5173)

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | No | — | Enables OpenAI provider |
| `ANTHROPIC_API_KEY` | Yes (for AI) | — | Enables Anthropic (Claude), the default provider |
| `ANTHROPIC_MODEL` | No | `claude-haiku-5-5` | Claude model ID for Pro users |
| `FREE_AI_MODEL` | No | `claude-haiku-5-5` | Claude model ID for signed-in free users |
| `FREE_AI_DAILY_LIMIT` | No | `3` | AI analyses per free user per rolling 24h |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model to use |
| `DEFAULT_LLM_PROVIDER` | No | `anthropic` | Default AI provider |
| `AI_MAX_TOKENS` | No | `1500` | Max tokens per LLM response |
| `MAX_QUERY_CHARS` | No | `32000` | Max query input size (Pro tier / absolute ceiling) |
| `SUPABASE_URL`      | No  | —  | Supabase project URL — enables shareable report URLs and persistence |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes (for persistence) | — | Supabase service_role key — required for all backend reads/writes to `analyses`/`user_usage` now that RLS is enabled on both tables. Bypasses RLS; **never** expose to the frontend. |
| `SUPABASE_ANON_KEY` | No  | —  | Supabase anon key. Not currently used by the backend (RLS-protected tables need service_role, and the frontend never talks to Supabase directly) — kept for reference/future public-read use cases. |

Create a `.env` file in `/backend` using `.env.example` as the template.

---

## Project Structure

```
sql-query-analyzer/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── sql_analyzer.py    # Main analyzer agent (heuristics + LLM orchestration)
│   │   │   ├── optimizer.py       # Deterministic "Annotated Query" comment pass (never rewrites)
│   │   │   └── explainer.py       # Plain-English explanation layer
│   │   ├── llm/
│   │   │   ├── router.py          # Dual-provider LLM router (Claude + OpenAI; HF removed Oct 2026)
│   │   │   ├── rewrite_check.py   # Verifies/filters AI rewrites + targeted fixes before they reach the UI
│   │   │   └── json_utils.py      # LLM JSON-response parsing helpers
│   │   ├── schemas/
│   │   │   └── models.py          # Pydantic request/response models
│   │   ├── tools/
│   │   │   ├── query_parser.py    # SQL structure extractor + heuristic rules
│   │   │   ├── execution_planner.py
│   │   │   ├── index_recommender.py
│   │   │   ├── batch_parsers.py   # Batch analysis: splits a pasted batch into queries
│   │   │   ├── batch_reconciler.py
│   │   │   ├── tabular_parse.py
│   │   │   ├── plan_crossref.py
│   │   │   ├── plan_parsers/      # EXPLAIN plan parsers (Postgres, MySQL)
│   │   │   └── collectors/        # Per-dialect EXPLAIN collection helpers (5 dialects)
│   │   ├── utils/
│   │   │   ├── config.py
│   │   │   ├── database.py          # Supabase persistence — save/fetch analyses
│   │   │   ├── dialect_config.py    # Dialect-specific DDL, rewrites, LLM prompts (Phase 1.7)
│   │   │   ├── db_connectors.py
│   │   │   └── ai_cache.py          # Caches AI output for the built-in sample queries
│   │   └── main.py                # FastAPI app, routes, rate limiting, Clerk auth, Stripe webhook
│   ├── migrations/                # Versioned Supabase schema (001_initial_schema.sql, ...)
│   ├── LIMITATIONS.md             # Known gaps and scope boundaries
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── QueryInput.jsx
│   │   │   ├── OptimizationSuggestions.jsx
│   │   │   ├── ExecutionPlan.jsx
│   │   │   ├── ResultsPanel.jsx
│   │   │   ├── ResultViews.jsx      # Tabbed result layout (Findings/AI Insights/Rewrite/etc.)
│   │   │   ├── ResultFollowUp.jsx
│   │   │   ├── SampleQueries.jsx    # Pre-built example queries
│   │   │   ├── Header.jsx           # Sticky enterprise nav
│   │   │   ├── Hero.jsx             # Value proposition strip
│   │   │   ├── Footer.jsx           # Links + attribution
│   │   │   ├── Toast.jsx            # Notification system
│   │   │   ├── ShareButton.jsx      # Share analysis URL
│   │   │   ├── QueryDiagnosis.jsx   # Structured plain-explanation renderer
│   │   │   ├── ReportPage.jsx       # Shareable /report/:id read-only page
│   │   │   ├── SanitizerPanel.jsx   # Three-state sanitizer UI
│   │   │   ├── BatchAnalysisPage.jsx  # /batch — paste-box batch analysis UI
│   │   │   ├── HistoryPage.jsx        # /history — signed-in analysis history
│   │   │   ├── PricingPage.jsx        # /pricing — Free vs Pro comparison
│   │   │   ├── UpgradeModal.jsx       # Pro upgrade CTA (checkout gated — see Roadmap)
│   │   │   ├── OptimizationComplete.jsx
│   │   │   └── QuizMode.jsx
│   │   ├── utils/
│   │   │   ├── analytics.js         # GA4 event tracking
│   │   │   ├── aiInsights.js        # Shared AI-JSON parsing (App.jsx + ResultsPanel.jsx)
│   │   │   ├── sanitizer.js         # Client-side query sanitizer (substitution map,
│   │   │   │                        #   sanitize/desanitize/buildDiff)
│   │   │   ├── aiPreference.js
│   │   │   ├── providerSelection.js
│   │   │   ├── serviceStatus.js
│   │   │   └── proWaitlist.js       # mailto: "Pro coming soon" flow (checkout gated)
│   │   └── App.jsx
│   └── package.json
├── docs/
├── CHANGELOG.md
└── .github/workflows/
```

---

## Roadmap

* [x] Core heuristic engine — 12 rules across 5 dialects — Phase 1 ✅
* [x] Persistent query history (Supabase) — Phase 1.5 ✅
* [x] Shareable /report/:id URLs — Phase 1.5 ✅
* [x] Enterprise UI shell (Header, Hero, Footer, Toast) — Phase 1.6 ✅
* [x] Google Analytics 4 event tracking — Phase 1.6 ✅
* [x] Dialect-aware DDL, rewrites, and LLM prompts (5 DB types) — Phase 1.7 ✅
* [x] Schema-aware analysis — paste DDL for confirmed (not just estimated) index suggestions — Phase 2 ✅
* [x] Heuristic engine grown to 17 rules across 5 dialects — ongoing
* [x] Batch workload analysis (`/batch`) + EXPLAIN plan collectors for all 5 dialects — Phase 3 ✅
* [ ] LangGraph agentic pipeline — Phase 3 ⏭ (deferred post-revenue)
* [x] User auth (Clerk, JWT-verified) + AI usage metering (daily caps per user/IP) — Phase 4 ✅
* [~] Stripe payments — backend integration (webhook, billing portal) and the Pro upgrade UI
  are built, but checkout is **intentionally disabled by default**
  (`VITE_PRO_CHECKOUT_ENABLED` must be explicitly set) while ensuring running a paid SaaS is
  compatible with a Canadian closed/employer-specific work permit. Signed-in users currently
  get Pro free on request instead — see `docs/pro-checkout-coming-soon.md` — Phase 4
* [ ] GitHub Action: `querytuner-analyze` for CI/CD pipelines — Phase 5 🔜
* [ ] Cross-database execution plan risk normalizer (UEPN) — Phase 5 🔜
* [ ] Live DB connection mode — Phase 5 🔜

---

## Known Limitations

See [LIMITATIONS.md](backend/LIMITATIONS.md) for the full list. Key limitations: no live DB
connection, AI insights depend on the Anthropic/OpenAI APIs being reachable, LATERAL join
correlated-column detection is not yet supported, and DDL-hint alias resolution
(`_extract_table_aliases`) is scoped to a multi-statement batch's first statement even though
the rest of the heuristic engine analyzes the whole batch.

---

## Contributing

Issues and PRs welcome. Please open an issue before submitting a large change.

```bash
git checkout -b feature/your-feature
# make changes, add tests
git commit -m "feat: describe your change"
git push origin feature/your-feature
# open a pull request
```

---

## License

MIT © 2026 [AutoShiftOps](https://github.com/AutoShiftOps)
Built by [Sudhakar Sajja](https://github.com/AutoShiftOps) — Application Architect, TechMahindra
