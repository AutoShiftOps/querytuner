# QueryTuner — AI-Powered SQL Query Diagnostics

[![Version](https://img.shields.io/badge/version-0.2.0-blue)](CHANGELOG.md)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi)](https://sql-query-analyzer-ekbk.onrender.com/docs)
[![Frontend](https://img.shields.io/badge/frontend-React-61DAFB?logo=react)](https://querytuner.com)
[![AI](https://img.shields.io/badge/AI-HuggingFace%20%7C%20OpenAI-FFD21F?logo=huggingface)](https://huggingface.co)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-live-brightgreen)](https://querytuner.com)

> Paste any SQL query. Get instant performance diagnosis,
> index recommendations, and an optimized rewrite —
> across **PostgreSQL, MySQL, Oracle, SQL Server, and SQLite**.

**No database connection required. Paste-in and analyze.**

🔗 **Live Demo → [querytuner.com](https://querytuner.com)**
📖 **API Docs → [/docs](https://sql-query-analyzer-ekbk.onrender.com/docs)**

---

## What It Does

QueryTuner analyzes SQL queries in two layers:

1. **Heuristic Engine** (always on, instant) — rule-based detection of common performance
   anti-patterns: missing indexes, leading wildcards, functions in WHERE clauses, SELECT *,
   unbounded ORDER BY, and more.

2. **AI Layer** (optional) — powered by HuggingFace (`Qwen/Qwen2.5-Coder`) or OpenAI
   (`gpt-4o-mini`). Generates CTE rewrites, CREATE INDEX statements with justification,
   and plain-English diagnosis.

---

## Features

- 🗄️ **5 Database Dialects** — PostgreSQL, MySQL, Oracle, SQL Server, SQLite
- ⚡ **Heuristic Engine** — 12 deterministic rules, always available, no external API calls required
- 🗂️ **Schema-Aware Analysis** — paste `CREATE TABLE` DDL and index recommendations upgrade from
  estimated to **confirmed**, resolved against your real table and column names
- 🔧 **Dialect-Correct Index DDL** — `CREATE INDEX CONCURRENTLY` (PostgreSQL),
  `ALTER TABLE ... ADD INDEX` (MySQL), `NOLOGGING` (Oracle), `WITH (ONLINE=ON)` (SQL Server)
- 🤖 **Dual AI Provider** — HuggingFace (default, free) or OpenAI, with structured JSON output
  (falls back to readable plain text if the model doesn't return JSON)
- 🔍 **Severity-Ranked Findings** — Critical → High → Medium → Low
- 📋 **Optimized Query Output** — rewritten SQL you can copy and run
- 🔗 **Shareable Reports** — every analysis gets a permanent `/report/:id` URL
- 📈 **Analytics** — Google Analytics 4 event tracking on every user action
- 🛡️ **Security Scanning** — detects SQL injection patterns and unsafe constructs
- 📊 **Readability Score** — quantifies query clarity for code review
- 🔌 **REST API** — integrable into CI/CD pipelines and developer tooling
- 🚫 **No DB Connection Needed** — works entirely from pasted query text (schema DDL is optional,
  only needed to unlock confirmed mode)

---

## Live API

```bash
# Analyze a query (heuristics only, no API key needed)
curl -X POST https://sql-query-analyzer-ekbk.onrender.com/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC",
    "db_type": "postgresql",
    "use_llm": false
  }'

# With AI insights (requires HF_API_KEY on server)
curl -X POST https://sql-query-analyzer-ekbk.onrender.com/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT u.id, COUNT(o.id) FROM users u LEFT JOIN orders o ON o.user_id = u.id WHERE YEAR(o.created_at) = 2025 GROUP BY u.id",
    "db_type": "mysql",
    "use_llm": true,
    "llm_provider": "huggingface"
  }'
```

**Supported `db_type` values:** `postgresql` · `mysql` · `oracle` · `sqlserver` · `sqlite`
**Supported `llm_provider` values:** `huggingface` · `openai`

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
  "ai_model": "Qwen/Qwen2.5-Coder-3B-Instruct"
}
```

Full schema at [`/docs`](https://sql-query-analyzer-ekbk.onrender.com/docs).

---

## Architecture

```
querytuner.com (Vercel)          sql-query-analyzer-ekbk.onrender.com (Render)
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
                                    │   │  HuggingFace│OpenAI│ │
                                    │   └────────────────────┘ │
                                    └──────────────────────────┘
```

**Stack:**
- Backend: Python · FastAPI · Pydantic · sqlparse · LangChain
- Frontend: React · Tailwind CSS · Axios · Lucide Icons
- AI: HuggingFace Inference API (`Qwen/Qwen2.5-Coder-3B-Instruct`) · OpenAI-compatible
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
cp .env.example .env          # add your HF_API_KEY
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
| `HF_API_KEY` | Yes (for AI) | — | HuggingFace API key |
| `HF_MODEL` | No | `Qwen/Qwen2.5-Coder-3B-Instruct` | HuggingFace model ID |
| `OPENAI_API_KEY` | No | — | Enables OpenAI provider |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model to use |
| `DEFAULT_LLM_PROVIDER` | No | `huggingface` | Default AI provider |
| `AI_MAX_TOKENS` | No | `800` | Max tokens per LLM response |
| `MAX_QUERY_CHARS` | No | `20000` | Max query input size |
| `SUPABASE_URL`      | No  | —  | Supabase project URL — enables shareable report URLs |
| `SUPABASE_ANON_KEY` | No  | —  | Supabase anon key — enables analysis persistence     |

Create a `.env` file in `/backend` using `.env.example` as the template.

---

## Project Structure

```
sql-query-analyzer/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── sql_analyzer.py    # Main analyzer agent (heuristics + LLM orchestration)
│   │   │   ├── optimizer.py       # Query rewrite engine
│   │   │   └── explainer.py       # Plain-English explanation layer
│   │   ├── llm/
│   │   │   ├── hf_client.py       # HuggingFace async client
│   │   │   └── router.py          # Dual-provider LLM router (HF + OpenAI)
│   │   ├── schemas/
│   │   │   └── models.py          # Pydantic request/response models
│   │   ├── tools/
│   │   │   ├── query_parser.py    # SQL structure extractor + heuristic rules
│   │   │   ├── execution_planner.py
│   │   │   └── index_recommender.py
│   │   ├── utils/
│   │   │   ├── config.py
│   │   │   ├── database.py          # Supabase persistence — save/fetch analyses
│   │   │   ├── dialect_config.py    # Dialect-specific DDL, rewrites, LLM prompts (Phase 1.7)
│   │   │   └── db_connectors.py
│   │   └── main.py                # FastAPI app, routes, rate limiting
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
│   │   │   ├── SampleQueries.jsx    # Pre-built example queries
│   │   │   ├── Header.jsx           # Sticky enterprise nav
│   │   │   ├── Hero.jsx             # Value proposition strip
│   │   │   ├── Footer.jsx           # Links + attribution
│   │   │   ├── Toast.jsx            # Notification system
│   │   │   ├── ShareButton.jsx      # Share analysis URL
│   │   │   ├── QueryDiagnosis.jsx   # Structured plain-explanation renderer
│   │   │   └── ReportPage.jsx       # Shareable /report/:id read-only page
│   │   ├── utils/
│   │   │   ├── analytics.js         # GA4 event tracking
│   │   │   └── aiInsights.js        # Shared AI-JSON parsing (App.jsx + ResultsPanel.jsx)
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
* [ ] LangGraph agentic pipeline — Phase 3 ⏭ (deferred post-revenue)
* [ ] API key auth + usage metering — Phase 4 🔜
* [ ] Stripe payments — Free / Pro / Team tiers — Phase 4 🔜
* [ ] GitHub Action: `querytuner-analyze` for CI/CD pipelines — Phase 5 🔜
* [ ] Cross-database execution plan risk normalizer (UEPN) — Phase 5 🔜
* [ ] Live DB connection mode — Phase 5 🔜

---

## Known Limitations

See [LIMITATIONS.md](backend/LIMITATIONS.md) for the full list. Key limitations: no live DB
connection, stateless analysis (no query history across runs), LLM availability depends on the
HuggingFace free tier, and LATERAL join correlated-column detection is not yet supported.

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
