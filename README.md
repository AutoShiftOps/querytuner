# QueryTuner — AI-Powered SQL Query Diagnostics

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

- 🗄️ **5 Database Flavors** — PostgreSQL, MySQL, Oracle, SQL Server, SQLite
- ⚡ **Instant Heuristic Analysis** — sub-5ms, no external API calls required
- 🤖 **Dual AI Provider** — HuggingFace (default, free) or OpenAI
- 🔍 **Severity-Ranked Findings** — Critical → High → Medium → Low
- 📋 **Optimized Query Output** — rewritten SQL you can copy and run
- 🛡️ **Security Scanning** — detects SQL injection patterns and unsafe constructs
- 📊 **Readability Score** — quantifies query clarity for code review
- 🔌 **REST API** — integrable into CI/CD pipelines and developer tooling
- 🚫 **No DB Connection Needed** — works entirely from pasted query text

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
git clone https://github.com/AutoShiftOps/sql-query-analyzer
cd sql-query-analyzer

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your HF_API_KEY
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "REACT_APP_API_URL=http://localhost:8000" > .env.local
npm start
```

Open `http://localhost:3000`

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
│   │   │   └── db_connectors.py
│   │   └── main.py                # FastAPI app, routes, rate limiting
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── QueryInput.jsx
│   │   │   ├── OptimizationSuggestions.jsx
│   │   │   ├── ExecutionPlan.jsx
│   │   │   └── ResultsPanel.jsx
│   │   └── App.js
│   └── package.json
├── docs/
└── .github/workflows/
```

---

## Roadmap

- [ ] Persistent query history (Supabase)
- [ ] API key auth + usage metering
- [ ] Explain plan paste-in mode (Oracle `DBMS_XPLAN`, PostgreSQL `EXPLAIN ANALYZE`)
- [ ] Cross-database execution plan risk normalizer (UEPN)
- [ ] GitHub Action: `querytuner-analyze` for CI/CD pipelines
- [ ] Schema-aware analysis (paste your DDL for richer suggestions)
- [ ] OpenAI GPT-4o tier

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
