# Phase 1.5 — Implementation Guide
**Issues #40, #41, #42 | Estimated time: 3 × 30-min sprints**

---

## Sprint 1 — Supabase setup + persistence (Issue #40)

### Step 1 — Create Supabase project (5 min)
1. Go to [supabase.com](https://supabase.com) → New project → name it `querytuner`
2. Note your **Project URL** and **anon public key** from Settings → API

### Step 2 — Run the SQL schema (2 min)
Open the Supabase **SQL Editor** and paste + run this:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE analyses (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash        TEXT NOT NULL,
    db_type           TEXT NOT NULL,
    original_query    TEXT NOT NULL,
    findings          JSONB NOT NULL DEFAULT '[]',
    severity          TEXT NOT NULL DEFAULT 'low',
    optimized_query   TEXT,
    readability_score FLOAT,
    analysis_time_ms  FLOAT,
    used_ai           BOOLEAN DEFAULT FALSE,
    ai_model          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analyses_query_hash ON analyses(query_hash);
CREATE INDEX idx_analyses_created_at ON analyses(created_at DESC);
```

### Step 3 — Add files to backend (5 min)
- Copy `database.py` → `backend/app/utils/database.py`
- Replace `backend/app/utils/config.py` with the updated version

### Step 4 — Update main.py (10 min)
Open `MAIN_PY_DIFF.py` and apply the 3 changes described in it:
- Add import at top
- Wrap the return value in `/analyze` to call `save_analysis()`
- Add the `GET /report/{analysis_id}` route

### Step 5 — Add env vars (3 min)
Add to `backend/.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

Add the same two vars in Render dashboard → Environment

### Step 6 — Add httpx to requirements.txt (1 min)
```
httpx>=0.27.0
pydantic-settings>=2.0.0
```
(check if already present — `httpx` may be there from LangChain)

### Test it locally:
```bash
cd backend
uvicorn app.main:app --reload --port 8000

curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM orders", "db_type": "postgresql", "use_llm": false}'

# Response should now include:
# "analysis_id": "some-uuid",
# "share_url": "https://querytuner.com/report/some-uuid"
```

---

## Sprint 2 — Frontend report page (Issue #41)

### Step 1 — Add files (5 min)
- Copy `ReportPage.jsx` → `frontend/src/components/ReportPage.jsx`
- Copy `vercel.json` → repo root (next to `frontend/` and `backend/`)

### Step 2 — Install react-router-dom if needed (2 min)
```bash
cd frontend
npm install react-router-dom
```

### Step 3 — Update App.js (10 min)
Add the router wrapper as shown at the bottom of `ShareButton.jsx`:
```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ReportPage from './components/ReportPage';

function Root() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<YourExistingApp />} />
        <Route path="/report/:id" element={<ReportPage />} />
      </Routes>
    </BrowserRouter>
  );
}
export default Root;
```

### Test it:
1. Start frontend: `npm run dev`
2. Run an analysis, copy the `analysis_id` from response
3. Navigate to `http://localhost:5173/report/that-uuid`
4. You should see the read-only report page

---

## Sprint 3 — Share button (Issue #42)

### Step 1 — Add ShareButton.jsx (2 min)
- Copy `ShareButton.jsx` → `frontend/src/components/ShareButton.jsx`

### Step 2 — Add to ResultsPanel.jsx (10 min)
In `ResultsPanel.jsx` (or wherever you render analysis results):

```jsx
import ShareButton from './ShareButton';

// Add this near the top of your results section,
// where `result` is the response from /analyze:
<ShareButton analysisId={result.analysis_id} />
```

Make sure your state that holds the `/analyze` response
also stores `analysis_id`. If you have something like:
```js
const [result, setResult] = useState(null);
// after axios.post('/analyze'):
setResult(data); // data.analysis_id is now available
```
That's all you need.

### Test it:
1. Run an analysis
2. "Share analysis" button appears in results panel
3. Click it → URL copied to clipboard
4. Open the URL in an incognito tab → read-only report renders

---

## Commit message sequence

```bash
# After Sprint 1:
git commit -m "feat(#40): add Supabase persistence to /analyze endpoint"

# After Sprint 2:
git commit -m "feat(#41): add shareable /report/:id route and ReportPage"

# After Sprint 3:
git commit -m "feat(#42): add ShareButton with clipboard copy to ResultsPanel"
```

---

## What this unlocks

Once deployed, every analysis at querytuner.com gets a permanent URL like:
`https://querytuner.com/report/3a7f29bc-...`

**Next actions after this ships:**
1. Analyze one of the 9 sample queries yourself
2. Share the report URL on LinkedIn: *"I built a tool that generates shareable SQL analysis reports. Here's what it found on a real query: [link]"*
3. Post on r/SQL and r/programming with a real report link as proof

That link on a public post is your first EB-1A evidence artifact.
