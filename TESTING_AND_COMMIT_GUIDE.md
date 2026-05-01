# QueryTuner — Local Testing & Commit Guide

> Reference guide for testing locally and committing correctly before pushing to GitHub.

---

## The Golden Rule

```
write code → test locally → commit with "closes #N" → push → CI confirms
```

Never commit `closes #N` until your local test passes.
The issue closes automatically when the PR merges — not when you write the message.

---

## One-Time Setup

```bash
# Backend
cd backend
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash
# source venv/bin/activate         # Mac / Linux
pip install -r requirements.txt
pip install pytest pytest-cov

# Frontend
cd frontend
npm install
```

---

## Backend Testing (Python — heuristics, parser, optimizer, explainer)

### Run all tests
```bash
cd backend
pytest tests/ -v
```

### Run one test file
```bash
pytest tests/test_heuristics.py -v
```

### Run one specific test
```bash
pytest tests/test_heuristics.py::test_cartesian_join -v
```

### Run with coverage report
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

### Manual smoke test (before pytest fixtures exist)
```bash
cd backend
python -c "
from app.agents.sql_analyzer import SQLAnalyzerAgent
agent = SQLAnalyzerAgent()
result = agent.analyze('SELECT * FROM orders JOIN users', 'postgresql')
print(result['suggestions'])
"
```

### Lint check (must pass before every commit)
```bash
cd backend
ruff check .
ruff format --check .
```

### Fix lint issues automatically
```bash
ruff check . --fix
ruff format .
```

---

## Frontend Testing (React — components, UI, markdown)

### Start local dev server
```bash
cd frontend
npm run dev          # opens at localhost:5173
```

### Lint
```bash
npm run lint         # must pass before commit
```

### Build check (catches import/type errors)
```bash
npm run build        # must pass before commit
```

### Run frontend tests
```bash
npm test
```

---

## Full Stack — End-to-End Local Test

Run both servers at the same time:

```bash
# Terminal 1 — backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open `http://localhost:5173` → test your change manually in the browser.

---

## Pre-Commit Checklist

Run through this before **every** `git commit`:

```bash
# Step 1 — Backend lint
cd backend
ruff check . && ruff format --check .

# Step 2 — Backend tests
pytest tests/ -v

# Step 3 — Frontend lint + build
cd ../frontend
npm run lint && npm run build

# Step 4 — Only if all 3 pass, commit
git add .
git commit -m "feat: add cartesian_join heuristic closes #24"
git push origin feat/cartesian-join-heuristic
```

---

## One-Command Check (Makefile shortcut)

Add to `backend/Makefile`:

```makefile
check:
	ruff check .
	ruff format --check .
	pytest tests/ -v

.PHONY: check
```

Then just run before every commit:

```bash
cd backend && make check
```

All green → safe to commit.

---

## Branch + PR Workflow (Per Issue)

```bash
# 1. Start a new branch for each issue
git checkout -b feat/cartesian-join-heuristic
#   Naming convention:
#   feat/   → new feature
#   fix/    → bug fix
#   test/   → adding tests
#   ci/     → CI/CD changes
#   audit/  → code audit / refactor

# 2. Write code and test locally (see checklist above)

# 3. Commit — include "closes #N" to auto-close the issue on merge
git commit -m "feat: add cartesian_join heuristic closes #24"

# 4. Push and open PR
git push origin feat/cartesian-join-heuristic
gh pr create --fill

# 5. GitHub Actions runs CI automatically on the PR
#    If CI passes → merge
#    If CI fails  → fix locally, push again

# 6. Merge PR
#    → issue #24 auto-closes
#    → Kanban card moves to ✅ Done
#    → pick next issue from top of Backlog
```

---

## Commit Message Format

```
<type>: <short description> closes #<issue-number>

Types:
  feat     → new feature
  fix      → bug fix
  test     → adding or updating tests
  ci       → CI/CD pipeline changes
  refactor → code change with no behaviour change
  docs     → documentation only
  audit    → code review / cleanup

Examples:
  feat: add cartesian_join heuristic closes #24
  fix: remove trailing \b from SELECT * regex closes #23
  test: add 20 pytest fixtures for heuristic engine closes #29
  ci: wire pytest into GitHub Actions closes #30
  audit: fix query_parser GROUP BY always returns list closes #31
```

---

## Phase 1 — Issue Sequence Reference

| Priority | Issue # | Title | Blocked by |
|---|---|---|---|
| 1 | #31 | audit: query_parser.py | Nothing — START HERE |
| 2 | #23 | feat: index_review heuristic | #31 |
| 3 | #24 | feat: cartesian_join heuristic | #31 |
| 4 | #25 | feat: implicit_cast heuristic | #31 |
| 5 | #26 | feat: subquery_to_join heuristic | #31 |
| 6 | #27 | fix: optimizer LIMIT rewrite | #23–#26 |
| 7 | #28 | fix: optimizer LIKE rewrite | #23–#26 |
| 8 | #29 | test: 20 pytest fixtures | #23–#28 |
| 9 | #30 | ci: wire pytest into CI | #29 |

---

## Quick Reference Card

| Situation | Command |
|---|---|
| Run all backend tests | `pytest tests/ -v` |
| Run one test | `pytest tests/test_heuristics.py::test_name -v` |
| Fix lint | `ruff check . --fix && ruff format .` |
| Smoke test analyzer | `python -c "from app.agents.sql_analyzer import SQLAnalyzerAgent; ..."` |
| Start backend locally | `uvicorn app.main:app --reload --port 8000` |
| Start frontend locally | `npm run dev` |
| Full pre-commit check | `make check` (backend) + `npm run lint && npm run build` (frontend) |
| Create PR from branch | `gh pr create --fill` |
| Check CI status | `gh pr checks` |

---

## CI Will Catch It If You Miss It

Even if you skip the local checklist, GitHub Actions runs automatically on every push.
Check the status with:

```bash
gh pr checks                   # shows CI pass/fail on your PR
gh run list --limit 5          # shows last 5 workflow runs
gh run view --log              # shows full log of latest run
```

If CI fails after you push — fix locally, then:
```bash
git add .
git commit -m "fix: address CI failure"
git push origin feat/your-branch
```

CI re-runs automatically on every push to the branch.
