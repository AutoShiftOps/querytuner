# SQL Query Analyzer — 14-Day Learning Plan (Build + Understand)

This plan is designed for “I deployed it by copy-paste, now I want to truly understand and be able to write it myself.”

You will rebuild the project *intentionally* as a pipeline:
1) FastAPI request/response contract
2) SQL structure extraction (JSON-safe)
3) Rule-based analysis (heuristics)
4) Optional LLM enhancement (Hugging Face, later OpenAI)

FastAPI encourages organizing larger projects into multiple files/routers (“Bigger Applications”), which we’ll adopt by Day 3.  
Hugging Face chat completion uses a messages array (`role`, `content`), which matches our LLM interface.

---

## Ground rules (important)
- Commit daily: `day-X: <what you built>`
- Keep a `docs/LEARN_NOTES.md` and answer 3 questions each day:
  - What did I build?
  - Why do we need it?
  - What breaks if it’s removed?
- Add at least 1 test (or “golden query”) every day.
- Never store API keys in frontend code. Keys belong on the server.

---

## Repo targets (end of Day 14)
Backend:
- Stable `/analyze` endpoint returning JSON-safe response every time.
- SQL parser handles window functions without false clause detection.
- Heuristics return meaningful suggestions.
- Optional HF LLM insights with graceful fallback.

Frontend:
- Clean UI: input, suggestions, parsed structure, optimized query, execution plan (optional).
- Null-safe rendering (empty states never crash).
- Provider dropdown + “capabilities” detection.

Deploy:
- Backend on Render, frontend on Vercel.
- Understanding of CI warnings/build failures and how to fix them properly.

---

## Golden queries (keep these in `docs/golden_queries.md`)
Use these queries repeatedly to validate behavior. Copy them exactly.

### Q1: Simple filter + order
```sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

### Q2: Window function (must NOT trigger top-level ORDER BY)
```sql
SELECT
  id,
  order_date,
  order_amount,
  SUM(order_amount) OVER (ORDER BY order_date) AS running_total
FROM orders;
```

### Q3: Join + filter
```sql
SELECT u.id, u.email, COUNT(o.id) AS orders
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.status = 'active'
GROUP BY u.id, u.email
ORDER BY orders DESC
LIMIT 50;
```

### Q4: Leading wildcard LIKE (performance smell)
```sql
SELECT id, email
FROM users
WHERE email LIKE '%@gmail.com';
```

### Q5: Function in WHERE (index usage smell)
```sql
SELECT id
FROM users
WHERE LOWER(email) = 'a@b.com';
```

## Day-by-day guide
### Day 1 — Understand the pipeline (no new features)
**Read/learn**
- Trace request → response: What does /analyze accept and return?
- List every response field and what produces it.

**Lab**
- Call /docs (Swagger UI) and run Q1–Q5.
- Save one real response JSON per query into docs/sample_responses/.

**Deliverables**
- `docs/LEARN_NOTES.md` (Day 1 entry)
- `docs/golden_queries.md`
- `docs/sample_responses/*.json`

### Day 2 — API contract (Pydantic models = your truth)
**Goals**
- A predictable contract: request/response models that always serialize cleanly.
- Learn why “JSON-safe types only” matters.

**Lab**
- Create (or tighten) QueryRequest and QueryAnalysisResult.
- Add input validation:
    - empty query => 400
    - too large query => 400
- Ensure response never contains non-serializable objects.

**Done checklist**
- ✅ invalid payload returns 422 (FastAPI validation)
- ✅ empty query returns 400 with message
- ✅ response serialization never crashes

### Day 3 — Structure backend like a real app (routers/modules)
**Why**
- FastAPI recommends using multiple files and APIRouter for bigger apps.

**Lab**
- Split into:
    - app/main.py (create app, middleware, include routers)
    - app/routers/analyze.py (analyze endpoint)
    - app/schemas.py (Pydantic models)

- Keep imports clean (avoid circular imports).

**Done checklist**
- ✅ same endpoints still work
- ✅ no ModuleNotFoundError: app

### Day 4 — Configuration: .env locally vs hosted env vars
**Goals**
- Understand local .env loading vs Vercel/Render environment variables.
- Learn where keys must live.

**Lab**
- Add python-dotenv and load_dotenv() locally (optional in prod).
- Add .env.example with non-secret placeholders.

**Done checklist**
- ✅ local run picks up .env
- ✅ deployed run uses host env vars (no .env dependency)

### Day 5 — SQL parsing baseline (JSON-safe extraction only)
**Goals**
- Learn what sqlparse is: a non-validating SQL parser.
- Only return JSON-safe primitives in parsed_query.

**Lab**
- Implement `QueryParser.parse(query)` returning:
    - query_type, tables, joins
    - where_clause (top-level only)
    - group_by, order_by (top-level only)
    - select_items (can be empty today)
- Confirm no token objects leak into responses.

**Done checklist**
- ✅ Q1 returns tables=[orders], where_clause not empty
- ✅ no _TokenType serialization errors

### Day 6 — Top-level clauses correctly (window function safety)
**Goals**
- Learn why nested ORDER BY inside OVER(...) must be ignored for top-level clause extraction.

**Lab**
- Implement paren-depth + quote-aware scanners:
    - extract WHERE body
    - extract GROUP BY list
    - extract ORDER BY list

- Validate using Q2:
    - order_by must be empty (since ORDER BY is inside OVER)

**Done checklist**
- ✅ Q2 does NOT populate top-level order_by
- ✅ Q3 returns correct group_by and order_by

### Day 7 — SELECT list extraction: select_items
**Goals**
- Output columns vs expressions (aliasing)
- Split SELECT items by top-level commas only

**Lab**
- Implement:
    - `select_items = [{output, expr, has_alias}]`
    - `columns = [output...]` derived from select_items
- Validate Q2:
    - select_items includes exactly one window expression with output running_total

**Done checklist**
- ✅ no “SUM is a column” bug
- ✅ columns for Q2 = id, order_date, order_amount, running_total
- ✅ columns for Q2 = id, order_date, order_amount, running_total

### Day 8 — Heuristics engine (rules you can explain)
**Goals**
- Rules depend on parsed facts + simple query text checks.
- Each suggestion has: type, severity, suggestion, reason, estimated_improvement.

**Lab: implement 6 rules**
- SELECT * -> suggest selecting needed columns
- ORDER BY without LIMIT -> suggest limit for user-facing
- Leading wildcard LIKE -> warn about index usage
- Function on column in WHERE -> warn about index usage
- Many JOINs -> complexity warning
- Missing WHERE on SELECT -> “full scan risk” (fix false positives)

**Done checklist**
- ✅ Q4 triggers LIKE warning
- ✅ Q5 triggers function-in-where warning
- ✅ Q1 does NOT trigger “missing where”

### Day 9 — Tests (your future self will thank you)
**Goals**
- Prevent regressions in parser and heuristics.

**Lab**
- Add pytest tests for:
    - clause extraction for Q1/Q2
    - select_items extraction for Q2
    - 2 heuristic rules (LIKE, SELECT *)

**Done checklist**
- ✅ pytest passes
- ✅ changing parser logic breaks tests (good!)
- ✅ changing parser logic breaks tests (good!)

### Day 10 — LLM enhancement with Hugging Face (optional layer)
**Goals**
- Learn the “messages” pattern for chat completion:
    - [{role:"user", content:"..."}]

**Lab**
- Implement app/llm/hf_client.py
- Implement app/llm/router.py with provider switch:
    - huggingface (default)
    - openai (future)
- In analyzer: call LLM only when use_llm=true.

**Done checklist**
- ✅ without HF key => ai_insights null but request succeeds
- ✅ with HF key => ai_insights contains text

### Day 11 — Capabilities + provider UX
**Goals**
- UI should not offer providers that aren’t configured.

**Lab**
- Add /capabilities endpoint:
    - openai_available true/false
    - huggingface_available true/false
- Frontend: fetch capabilities on load with useEffect.

**Done checklist**
- ✅ OpenAI option disabled unless configured
- ✅ no “useEffect is not a function” mistakes (correct imports)

### Day 12 — Frontend components that never crash
**Goals**
- Learn default vs named exports/imports (avoid “Element type invalid”).

**Lab**
- Create components:
    - QueryInput.jsx
    - ResultsPanel.jsx
    - OptimizationSuggestions.jsx
    - ExecutionPlan.jsx (optional)
        Ensure each component exports a default React function.

**Done checklist**
- ✅ no runtime “Element type invalid” errors
- ✅ empty responses render gracefully

### Day 13 — Deployment & CI reality
**Goals**
- Understand Vercel CI builds and CRA warnings-as-errors.

**Lab**
- Deploy frontend to Vercel, backend to Render.
- Fix warnings properly (preferred) instead of bypassing CI.

**Done checklist**
- ✅ build is green
- ✅ you know where to set env vars on each platform

### Day 14 — Turn it into a product-quality tool
**Goals**
- Documentation, stability, demo.

**Lab**
- Write:
    - README.md quickstart
    - docs/SETUP.md
    - docs/DEPLOYMENT.md
- Add a “Demo queries” button in UI that loads Q1–Q5.
- Add GitHub Actions to run tests.

**Done checklist**
- ✅ a new user can run it quickly
- ✅ tests protect you from regressions

## Appendix: What to explain in interviews (or to yourself)
- Why parsing is deterministic and LLM is optional
- Why top-level scanning matters (window functions)
- Why response must be JSON-safe (Pydantic serialization)
- Why provider routing belongs server-side
- How you avoided exposing API keys