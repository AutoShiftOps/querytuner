# Docs/issue sync for #153, #154, #155, #156 — and the Phase 4 audit's own follow-ups

**Why:** four PRs merged to `master` since the last docs-sync pass (`247c7d58` #153 Quiz Mode, `90b7fd0b` #154 Batch Workload Analysis, `221a23b9` #155 ReportPage back-to-history fix, `ecd66de7` #156 OpenAI Pro-tier gating fix) — verified independently (full test suites re-run, real diffs read, all confirmed on `master`) but none show up anywhere in `ROADMAP.md` or `CHANGELOG.md` yet. Same gap as last time: this session has read-only repo access and can't push or comment — handing off exact content so nothing has to be re-derived.

**Please verify against the real commit log/dates before applying** — drafted from what this session could see.

---

## 1. CHANGELOG.md — `[Unreleased]` section (top of file)

Add a new `### Added` block (after the existing EXPLAIN-parser-chain bullet) and a `### Fixed` entry:

```
- Quiz Mode — before revealing the analysis, up to 2–3 interview-style multiple-choice
  questions generated from the query's own findings (confidence-gated: only
  `evidence_level !== "needs-runtime-evidence"` suggestions are used as answer keys),
  with a "Skip quiz" path and full reveal underneath either way. Free-tier feature,
  not Pro-gated. (PR #153, `247c7d58`)
- Batch workload analysis — `POST /analyze/batch` (Pro-gated) accepts a pasted export
  from PostgreSQL `pg_stat_statements`, MySQL `performance_schema`, or SQL Server
  Query Store, ranks top-N queries by production cost, runs each through the existing
  index recommender, and reconciles overlapping/redundant index suggestions across
  queries into one deduplicated set rather than N independent recommendation lists
  (#115, #120, PR #154, `90b7fd0b`)
```

```
### Fixed
- MySQL backtick-quoted identifier columns (`` `status` `` etc.) were silently dropped
  from WHERE/comparison-operator extraction — `IndexRecommender`'s column-extraction
  regexes only matched double-quoted or bare identifiers. This affected **all**
  single-query MySQL analysis, not just the new batch mode that surfaced it. (PR #154,
  `90b7fd0b`)
- History page items linked via a plain `<a href>`, causing a full page reload on every
  click despite the app using `react-router-dom` throughout — switched to `<Link>` for
  client-side transitions (PR #155, `221a23b9`)
- Shared report page (`/report/:id`) had no way back into the app — both nav links
  pointed to the external marketing site, a leftover from before the History feature
  existed and started linking into this page. Signed-in users now see a "← Back to
  history" link in the nav (PR #155, `221a23b9`)
- **OpenAI (GPT-4o-mini) Pro-tier gating was not enforced server-side** — a signed-in
  free-tier user could select "OpenAI" in the AI-provider dropdown and the backend
  would honor it, running real GPT-4o-mini calls against Pro's cost budget with
  nothing checking `is_pro` anywhere in the call path. `POST /analyze` now returns a
  structured `403 pro_required` for this case; the dropdown also disables the option
  client-side for non-Pro users. Found during a full Phase 4 audit, fixed same-day
  (#53, PR #156, `ecd66de7`)
```

Also worth doing while in this file: the `[Unreleased]` intro sentence still says *"Phase 4 (auth + payments) has shipped to `master`, along with the first batch of Phase 5 quick wins below. These changes will become v0.3.0 once tagged."* — decide whether that's still accurate given how much has landed since (EXPLAIN chain, batch analysis, quiz mode, three bug fixes) or whether it's time to actually cut v0.3.0 and start a fresh `[Unreleased]` block. Same open question as last sync's note on `Header.jsx`'s hardcoded `v0.2.0` badge — still hasn't moved, now further behind reality.

---

## 2. ROADMAP.md — three separate edits

### a) Phase 4 section (around line 165) — currently a pre-shipping task list, never updated

Currently reads as an unshipped plan (`Day 22 | Define Free tier limits...`, no ✅ anywhere) despite Phase 4 being live in production and independently audited. Recommend replacing the whole table with a shipped-status version, matching the format Phase 5's table already uses (✅ + commit + deviation notes):

```
## 🗓️ Phase 4 — Monetization Infrastructure — ✅ Shipped

**Goal:** Free vs Pro tier functional. First paid user possible.
**Status:** Live in production. Audited against original GitHub acceptance criteria
2026-08-25 — see `docs/querytuner-phase4-audit.md`. All 10 issues (#46–#53, #116, #124)
have real shipped functionality behind them; several differ from their literal
original wording (documented per-issue below and in GitHub comments). One live gap
found and fixed same-day (#53). One issue (#124) is a genuine partial build.

| Issue | Task | Status |
|---|---|---|
| #46 | Free/Pro tier limits | ✅ 10 analyses/**month** (not /day as originally worded), enforced server-side |
| #47 | Clerk auth on `/analyze` | ✅ Matches original ask |
| #48 | Usage tracking | ✅ `user_usage` (monthly aggregate) + `user_accounts` (subscription state) — different table shape than the `usage_log` originally specified; see migration 007's own note for a real bug this split fixed |
| #49 | Enforce limit, upgrade prompt | ✅ Returns `402`, not `429` as originally worded |
| #50 | Checkout + webhook | ✅ Stripe **Payment Links** + `POST /webhook/stripe`, not a backend `/create-checkout-session` endpoint as originally worded |
| #51 | Pricing page | ⚠️ No dedicated `/pricing` route exists — pricing lives in `UpgradeModal.jsx`, shown on demand. Open scope question, not just a wording gap |
| #52 | Clerk provider + header | ✅ Provider lives in `main.jsx` (app root), not `App.jsx` as originally worded; inline sign-in prompt instead of a redirect |
| #53 | Pro-tier LLM routing | ✅ Fixed `ecd66de7` — was unenforced server-side until the Phase 4 audit caught it same-day |
| #116 | Report management (delete/expire) | ✅ Fixed 90-day expiry + owner revoke; user-selectable 7/30/never not built — tracked in GitHub comment thread |
| #124 | User report dashboard | ⚠️ ~25% done — list view (timestamp/dialect/severity) shipped; sanitized indicator, delete button, share button, and the sanitized-only filter are not built |

Full findings: `docs/querytuner-phase4-audit.md`.
```

(Adjust wording/formatting to match your own conventions — the content is what matters, not the exact markdown.)

### b) Phase 5 table (around line 190) — two rows need updating

Replace:
```
| #115 | Batch workload analysis — detect conflicting indexes across multiple queries | 🔴 High |
```
```
| #120 | Batch query input from Query Store / pg_stat_statements export | 🔴 High |
```

with a single combined row (they shipped together in one PR):
```
| #115 | ✅ Batch workload analysis — cross-query index reconciliation (`90b7fd0b`) | 🔴 High |
| #120 | ✅ Batch query input from pg_stat_statements / performance_schema / Query Store export (`90b7fd0b`) | 🔴 High |
```

### c) New row for Quiz Mode — no GitHub issue was filed for it

It shipped (PR #153) but was never numbered as a tracked issue — add a row so it doesn't fall through the same gap #53 did:
```
| — | ✅ Quiz Mode — pre-reveal test-yourself questions from real query findings (`247c7d58`) | 🟢 Low |
```

### d) Milestone Summary table (further down) — add the missing ✅

```
| Phase 4 — Monetize | Jun 23–Jul 4 | Stripe + Auth + Free/Pro tiers |
```
→
```
| ✅ Phase 4 — Monetize | Jun 23–Jul 4 | Stripe + Auth + Free/Pro tiers |
```

---

## 3. GitHub issue comments

### #115 / #120 — close
> Shipped in `90b7fd0b` — `POST /analyze/batch` (Pro-gated) accepts a pasted export from `pg_stat_statements`, `performance_schema`, or Query Store, ranks top-N by production cost, and reconciles overlapping index suggestions across queries (subset/superset collapse + column-order-conflict flagging) instead of returning N independent recommendation lists. As a side effect of building this, also fixed a real pre-existing bug: MySQL backtick-quoted identifiers were silently dropped from column extraction, affecting all single-query MySQL analysis, not just batch mode. Verified independently — 304 backend tests pass (1 intentional xfail), diff read in full.

### No issue exists for Quiz Mode — recommend filing one retroactively (or just linking the PR)
> Shipped in `247c7d58` — not filed as a numbered issue originally (came from a mid-session product idea), flagging here so it's traceable the same way as everything else. Pre-analysis multiple-choice questions generated from the query's own findings, gated to `evidence_level !== "needs-runtime-evidence"` suggestions only so the "correct answer" is never something QueryTuner itself is only guessing at. Free-tier, skippable. Verified independently — 45 frontend tests pass, `generateQuiz()`/`pickDistractors()` read in full.

### No issue exists for the ReportPage back-button fix — same as above
> Shipped in `221a23b9`, in response to a direct user report ("no back button upon selecting the history item"). Root cause: `ReportPage.jsx`'s nav predates the History feature and both its links pointed externally. Signed-in users now get a "← Back to history" link; `HistoryPage.jsx`'s row links also switched from `<a href>` to `<Link>` for client-side transitions while in the area. Verified independently — lint/build clean, 45 frontend tests pass.

### #53 — comment (this one **can** close, since PR #156 fully resolves the gap the earlier comment on this issue described)
> Fixed in `ecd66de7` — `POST /analyze` now returns a structured `403 pro_required` when a non-Pro user requests `llm_provider="openai"`; the frontend dropdown also disables the option client-side for non-Pro users, matching the pattern already used for the free-tier query-size limit. This closes the gap identified in the Phase 4 audit (see `docs/querytuner-phase4-audit.md`) — free users could previously select OpenAI and the backend honored it with no `is_pro` check anywhere in the path. Library naming (`langchain-openai` vs. the raw `openai` SDK) and structured-output strictness remain different from this issue's original literal wording — not fixed here, considered non-urgent, still worth a wording update to the issue text if you want the acceptance criteria to reflect the actual shipped shape. Verified independently — 4 new tests covering all four free/Pro × openai/huggingface × use_llm combinations, full 308-test backend suite + 45-test frontend suite pass, diff read in full.

### #51 and #124 — no new comment needed yet, already covered by the Phase 4 audit's existing comments (still open, flagged as real follow-up candidates, not just wording gaps)
