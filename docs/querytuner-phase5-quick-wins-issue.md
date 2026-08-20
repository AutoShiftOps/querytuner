# Phase 5 — Quick Wins: #116, #118, #117

**Status:** Proposed — three separate backlog items, bundled here because each is small and self-contained; build and commit them independently (each gets its own commit/PR, same as `#54`).
**Depends on:** Nothing new — all three build on code that already exists and shipped.
**Goal:** Close three specific, already-scoped gaps in the existing report/index-recommendation pipeline.

---

## #116 — URL expiration and deletion for shareable reports

**Priority:** 🟡 Medium

### Why this matters

`GET /report/{analysis_id}` (`backend/app/main.py:462`) returns any analysis by UUID, forever, to anyone with the link — no auth check, no expiration. Shareable links are a real feature (`ShareButton.jsx`), but a permanent, unauthenticated, un-revocable link to someone's query (which may embed table/column names, sometimes literal WHERE-clause values) sitting on Slack or in a ticket forever is a data-retention gap, not just a nice-to-have.

### What exists today (confirmed by reading the repo)

- `analyses` table (`001_initial_schema.sql`) has `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` and an index on it (`idx_analyses_created_at`) — the data needed to compute age is already there.
- No `expires_at` column, no deletion endpoint, no scheduled cleanup job anywhere in the codebase (checked for cron/APScheduler/celery — none present).
- `get_analysis(analysis_id)` (`database.py:121`) does a plain lookup with no age check.

### Proposed scope

1. **Migration** — add `analyses.expires_at TIMESTAMPTZ NULL` (nullable so existing rows aren't retroactively expired). Set a default expiration window at write time in `save_analysis()` (e.g. 90 days from `created_at` — pick a number and make it a named constant, not a magic literal).
2. **`GET /report/{id}` enforces it** — if `expires_at` is in the past, return the same 404 shape already used for "not found" (`main.py:462`'s existing `HTTPException(404, "Analysis not found. It may have expired or the link is incorrect.")` — the copy already anticipates this case, it just isn't wired up yet).
3. **Explicit delete** — a `DELETE /report/{id}` endpoint, auth-gated to the owning `user_id` (mirror the `Depends(get_current_user)` pattern) so a signed-in user can revoke their own shared link early. Anonymous-authored analyses (`user_id IS NULL`) have no owner to authorize against — skip delete for those in v1, expiration-only.
4. **Cleanup mechanism** — no in-app scheduler exists, so don't build one. Two reasonable options: (a) lazy — expired rows are simply never returned by the read path above but stay in the table until a periodic manual/external cleanup; or (b) a Supabase `pg_cron` job that hard-deletes rows past `expires_at`. Recommend (a) for v1 — it's zero new infrastructure and gets the actual user-facing guarantee ("this link stops working") without needing a working scheduler in the loop.
5. **Frontend** — `ReportPage.jsx`'s existing 404 handling already needs to render *something* for a dead link; confirm its current "not found" state reads fine for "expired" too (may just need the copy checked, not new UI).

### Explicit non-goals for v1

- Not building a per-share custom expiration (user picks 7d/30d/never) — fixed default window only.
- Not hard-deleting on `DELETE` in v1 if that's harder to wire safely than a soft `expires_at = now()` — soft-delete (retroactively set `expires_at` to immediately) accomplishes the same user-facing outcome with less risk.
- Not touching `GET /history` — a user's own history list can still show their expired analyses' metadata (snippet, severity) even after the shareable link 404s; only the detail page is gated by this.

---

## #118 — Write and storage cost estimate per index recommendation

**Priority:** 🟡 Medium

### Why this matters

Every `OptimizationSuggestion` (`backend/app/schemas/models.py:55`) already carries `estimated_improvement` — a free-text read-side benefit string like `"50-90% faster JOINs on large tables"`. There's no corresponding cost side. Every index has a write-amplification and storage cost; recommending five indexes with no mention of that trade-off reads as one-sided advice, especially for a tool positioning itself as the thing a reviewer trusts on a PR.

### What exists today (confirmed by reading the repo)

- `backend/app/tools/index_recommender.py` — `IndexRecommender.recommend()` builds each suggestion via `self._make(...)` (`index_recommender.py:437`), which takes `estimated` (mapped to `estimated_improvement`) as one of its args, per suggestion type (`join_key`, `where_filter`, `partial_index_candidate`, `order_by_index`, `group_by_index`, `composite_index`).
- No column count, no data-type awareness, no row-count estimate anywhere in this path — schema parsing (`parse_schema_ddl`) already extracts column info from a pasted `CREATE TABLE`, so column *count* and *type* are available when `schema_info` is provided; nothing currently reads them for a cost estimate.

### Proposed scope

1. **New field**: `OptimizationSuggestion.cost_estimate: str | None` (same free-text-with-optional-schema-verification pattern as `estimated_improvement` — don't over-engineer this into a structured numeric model when the existing field for the benefit side is plain text).
2. **Heuristic-only v1** (no live DB, no real row counts available) — base it on what's actually knowable at suggestion time: number of columns in the proposed index (more columns → higher write cost, larger index), whether it's a composite index (composites cost more per write than single-column), and column data types if schema is available (e.g. indexing a `TEXT`/large `VARCHAR` column costs more storage per row than an `INT`). A simple three-tier label (`"Low write cost"` / `"Moderate write cost"` / `"Higher write cost — N-column composite"`) is enough for v1, not a byte-precise estimate you can't actually back without EXPLAIN/table statistics.
3. **Where to compute it** — inside `_make()` or right before it's called, using the same `alias`/`col`/`schema` values already being passed through; no new parsing pass needed.
4. **Frontend** — `OptimizationSuggestions.jsx` already renders each suggestion's fields; add the new `cost_estimate` line next to (or under) the existing improvement estimate so the trade-off reads together, not just the upside.

### Explicit non-goals for v1

- Not estimating actual bytes/MB — that needs real table row counts, which needs live DB access (that's `#57`, separately scoped, out of reach here).
- Not factoring actual write QPS or workload mix — no telemetry on how write-heavy the table is exists anywhere in this pipeline.

---

## #117 — Column order reasoning in composite index DDL proposals

**Priority:** 🟢 Low

### Why this matters

This is a correctness gap, not just a polish item. `_detect_composite_opportunity()` (`backend/app/tools/index_recommender.py:145`) builds the composite column list via:

```python
for alias, col in where_cols + join_cols + order_by_cols:
```

Column order in the resulting DDL is purely extraction order (WHERE columns first, then JOIN, then ORDER BY, in whatever order the parser found them) — not the standard composite-index ordering rule (equality-predicate columns before range/inequality columns, and columns used for filtering before columns only used for sorting). A composite index with the wrong column order can perform close to a single-column index or worse for the query it was suggested for — QueryTuner would be recommending DDL that doesn't deliver the "highest-ROI index change" claim already in the suggestion text (`index_recommender.py:376`) for some queries.

### What exists today (confirmed by reading the repo)

- `_extract_where_columns()` returns columns from the WHERE clause but does not currently distinguish equality (`col = ?`) from range (`col > ?`, `col BETWEEN`, `col LIKE 'x%'`) predicates — that distinction doesn't exist anywhere in the extraction step yet.
- `_detect_composite_opportunity()` takes `where_cols`, `join_cols`, `order_by_cols` as three already-separate lists (so the *category* of each column — WHERE vs JOIN vs ORDER BY — is known at the call site), it just doesn't use that information to order the final `cols` list, only to decide whether a column belongs in the composite at all.

### Proposed scope

1. **Classify WHERE columns by predicate type** during extraction (or as a follow-up pass over `where_clause`) — equality vs range/inequality. This is the one piece of new parsing work in this item; everything else is reordering existing data.
2. **Apply standard ordering** when building the composite's `cols` list: equality WHERE columns first, then JOIN key columns, then range/inequality WHERE columns, then ORDER BY-only columns last. (Standard composite-index guidance: equality predicates should lead a composite index; range predicates and sort columns trail, since the index can only maintain sort order for one range/sort column onward from the first range column.)
3. **Explain the ordering in the suggestion text** — the composite suggestion (`index_recommender.py:177`) already has a `suggestion` string; append a short clause naming *why* this order ("`status` first — equality filter; `created_at` last — used for sorting") so the reasoning is visible, not just applied silently. This is also useful evidence for the `confidence: certain | inferred` field mentioned in the CI/CD proposal, if/when that lands.
4. **Tests** — this is exactly the kind of thing that's easy to get subtly wrong; add cases with WHERE-equality + JOIN + ORDER BY all present in one query and assert the DDL column order matches the rule, not just that a composite was suggested at all.

### Explicit non-goals for v1

- Not reasoning about column cardinality/selectivity ordering *within* the equality group (e.g. `status` vs `tenant_id` — which equality column should lead) — that needs real data distribution stats this tool doesn't have. Order within each category (equality/join/range) can stay extraction-order for now; only the category-level ordering is in scope.
- Not touching single-column index suggestions — this only affects `_detect_composite_opportunity`'s composite-column ordering.

---

## Suggested sequencing

Independent of each other — no shared dependency. Suggest building `#117` first (smallest, most self-contained, pure-function logic that's easy to test in isolation), then `#118` (touches the same file, natural to batch), then `#116` last (only one that touches auth/deletion semantics and needs the most care around what "expired" means for `/history` vs `/report/:id`).
