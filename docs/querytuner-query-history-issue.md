# Phase 5 — Query History (backlog #54)

**Status:** Proposed — not started, filed in ROADMAP.md Phase 5 as `#54` ("Query history — save + replay past analyses per user", 🔴 High)
**Depends on:** Nothing new — Phase 4 auth (Clerk) and persistence are already shipped
**Goal:** Give Pro users a page listing their past analyses, each linking to its existing shareable report.

## Why this matters

`UpgradeModal.jsx` already advertises "Query history" as one of three Pro perks (`FEATURES` array, alongside "Unlimited analyses" and "Priority AI") — but the feature doesn't exist. Any signed-in Pro user who checks is currently being sold something QueryTuner isn't delivering. Since you now have a real (test) paying account to validate against, this gap should close before more Pro signups happen.

## What exists today (confirmed by reading the repo)

- `backend/migrations/006_user_accounts.sql` added `analyses.user_id TEXT NULL` with a btree index (`idx_analyses_user_id`) — every analysis from a signed-in user is already tagged with their Clerk `user_id`.
- `backend/app/main.py` `analyze_query` (`POST /analyze`) calls `save_analysis(response_payload)` with `user_id` included on every request from an authenticated caller, and returns `analysis_id` + `share_url`.
- `GET /report/{analysis_id}` (`main.py:462`) already returns a full stored analysis by UUID — `db_type`, `original_query`, `optimization_suggestions`, `severity`, `readability_score`, `created_at`, etc. — no new rendering logic needed once we know which IDs belong to a user.
- `GET /usage` (`main.py:389`) already establishes the pattern of `user_id: str | None = Depends(get_current_user)` returning per-user data, and `get_user_usage` shows how `is_pro` is looked up.
- Frontend already has `ReportPage.jsx` rendering `/report/:id`, and `Header.jsx` already conditionally renders based on `<SignedIn>` / `<SignedOut>` (Clerk) with room for another nav link.
- There is **no** endpoint today that lists analyses by `user_id` — only single-record lookup by `analysis_id` exists.

## Proposed scope

1. **Backend: `GET /history` endpoint** — `user_id: str | None = Depends(get_current_user)`, same auth pattern as `/usage` and `/analyze`. Returns 401/empty for anonymous callers; for signed-in callers, queries `analyses` by `user_id`, ordered by `created_at DESC`, paginated (`limit`/`offset` or cursor). Gate the *data*, not just the UI: check `is_pro` server-side via `get_user_usage` the same way `/analyze` does, so a free user hitting the endpoint directly doesn't get history back either.
2. **Response shape** — a lightweight summary per row, not the full analysis: `id`, `db_type`, a truncated `original_query` snippet, `severity`, count of `optimization_suggestions`, `created_at`. Avoid `SELECT *` — the full payload (execution plans, AI insights) is already available via the existing `/report/:id` on click-through.
3. **Frontend: History page** — new route (e.g. `/history`), lists rows from step 2 as a table/list: query snippet, db type badge, severity, issue count, relative timestamp — each row links to `/report/:id` (existing `ReportPage.jsx`, no new rendering).
4. **Gating** — mirror how the AI-insights checkbox is gated behind `isSignedIn` today: show the History link in `Header.jsx` (next to where "Manage subscription" would go) for `<SignedIn>` users; if the user is signed in but not Pro, either hide the link or show it linking to a locked state that opens `UpgradeModal.jsx` (reusing its existing Pro pitch rather than building a second paywall UI).
5. **Empty/loading/error states** — first-run empty state ("Your analyses will show up here"), since every current Pro tester will initially have zero history rows until this ships.
6. **Pagination** — even a simple offset-based "Load more" is enough for v1; do not attempt infinite scroll or virtualization yet.

## Explicit non-goals for v1

- Not building search/filter (by db_type, severity, date range) yet — validate that the flat list is used before adding filters.
- Not building delete/archive of individual history entries — out of scope until requested.
- Not changing `/report/:id` itself — it already returns everything the detail view needs.
- Not backfilling anonymous (`user_id IS NULL`) analyses into anyone's history — those were never tied to an account and stay untied.

## Suggested sequencing

This is scoped tightly enough to build directly — no external dependency like the CI/CD issue's `confidence` field. Backend endpoint first (testable in isolation via `/docs`), then the frontend page, then the header link + gating last so the entry point only appears once the page behind it works.
