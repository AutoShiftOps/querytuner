# Phase 5 — EXPLAIN Plan Parser Chain (#61, #62, #63)

**Status:** Proposed — three linked backlog items; scope them as one chain since `#63` has no meaning without `#61`/`#62` producing something to cross-reference against.
**Depends on:** Nothing new to build first — this is genuinely greenfield, but it closes a gap in something already shipped and user-facing (see below).
**Goal:** Make QueryTuner's own existing claim about EXPLAIN plans true.

## Why this matters — this one's urgent, not just backlog hygiene

`QueryInput.jsx`'s EXPLAIN paste-in section (line ~227) tells every user, right now, in production:

> "Pasting a real EXPLAIN plan upgrades heuristic findings from **estimated** to **schema-verified** — QueryTuner cross-references your actual execution plan against the parsed query instead of guessing from syntax alone."

Traced the full path end to end — **this claim is false today.** `evidence_level` is computed exactly once, in `index_recommender.py`'s `_make()`: `evidence_level = "schema-verified" if schema_verified else "needs-runtime-evidence"`, and `schema_verified` comes from `schema.get(real_table, {})` — i.e. purely from a pasted `CREATE TABLE` DDL, parsed by `parse_schema_ddl()`. `explain_plan` never enters that function, never enters `index_recommender.py` at all. What actually happens to a pasted EXPLAIN plan today:

1. It gets trimmed to 3000 chars and dropped into the LLM prompt as extra narrative context (`sql_analyzer.py:631`, Issue #60) — only affects the AI Insights *text*, when AI is even enabled, and even then only as unstructured context, not a verification signal.
2. It gets passed into `QueryRequest.explain_plan` → `collect_facts()` → `PostgresCollector.collect()`, which **ignores it entirely** and only attempts a *live* DSN connection (`POSTGRES_DSN` env var, which isn't set in this deployment). The pasted text is never read by the collector.
3. The resulting `facts` blob (with `facts.findings`) is returned in the API response (`main.py:360`) but **is never rendered anywhere in the frontend** — confirmed by grepping every `.jsx` file for `facts`. It's dead data on the wire today, for the one code path (live Postgres) where it's even populated.

So the "✓ plan attached" badge and the estimated→schema-verified promise are both currently cosmetic. Given the acquirer-diligence concern already raised this session about doc/issue staleness, a paying user (or a technical reviewer) pasting an EXPLAIN plan and checking whether anything actually changed is the single highest-risk unverified claim in the product right now — worse than a stale ROADMAP row, because it's live and user-facing.

## What exists today (confirmed by reading the repo)

- **Schema is already there and unused for this**: `PlanArtifact` (`format: "json"|"xml"|"text"`, `raw: Any`) and `AnalysisFacts` (`findings: list[Finding]`, `plan: PlanArtifact | None`) in `schemas/models.py` are exactly the right shape for parsed-plan output — no schema changes needed, just something to populate them from pasted text.
- **A real (partial) Postgres JSON-plan parser already exists**, just wired to the wrong input: `backend/app/tools/collectors/postgres.py`'s `_extract_findings`/`_walk_node` walks a `EXPLAIN (FORMAT JSON)` tree and emits `Finding`s for exactly three node types — `Seq Scan` (rows > 1000), `Nested Loop` (cost > 5000), `Hash Join` (informational). It only runs today when `PostgresCollector.collect()` gets a live `asyncpg` connection back with JSON already parsed by the driver — it has never been pointed at `request.explain_plan` (a raw string the user pasted).
- **MySQL collector is a stub**: `collectors/mysql.py` is `return self.not_configured("mysql")  # full impl coming Week 2` — that week never came. `#62` is genuinely from scratch.
- **The frontend already collects dialect-specific pasted text** with real placeholder examples per dialect (`QueryInput.jsx`'s `explainPlaceholders`) — Postgres JSON, MySQL `EXPLAIN FORMAT=JSON`, Oracle `DBMS_XPLAN.DISPLAY`, SQLite `EXPLAIN QUERY PLAN` — so the UI already anticipates multiple pasted formats; the backend just never parses any of them.
- **`evidence_level` already has three tiers** (`"deterministic" | "schema-verified" | "needs-runtime-evidence"`, per `OptimizationSuggestion`'s docstring) — a plan-confirmed tier needs to either reuse `"schema-verified"` (matching the UI copy's exact wording) or the doc should decide on a fourth tier (e.g. `"plan-verified"`) if plan-confirmation should be visually distinct from schema-confirmation. Recommend reusing `"schema-verified"` for `#63` v1, since that's the literal word already promised in the UI — don't introduce new UI states this doc hasn't scoped.

## Proposed scope

### #61 — Postgres EXPLAIN parser (parse *pasted* output, not just live)

1. New `backend/app/tools/plan_parsers/postgres.py` (or extend `query_parser.py` — pick based on where schema-DDL parsing already lives, for consistency) — `parse_postgres_explain(raw: str) -> PlanArtifact | None`.
2. **Two input shapes to handle**, matching what the UI already invites users to paste (`explainPlaceholders.postgresql` shows plain `EXPLAIN (ANALYZE, BUFFERS)` text output, not JSON): (a) JSON — if the pasted text parses as JSON, reuse/generalize the existing `_walk_node` logic rather than duplicating it; (b) plain-text tabular EXPLAIN output (the actual placeholder example: `Seq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)`) — needs a real text parser, since `_walk_node` only handles the JSON tree shape. Don't silently support only JSON while the UI's own placeholder promises text works too.
3. Expand node-type coverage beyond the existing three (`Seq Scan`, `Nested Loop`, `Hash Join`) to at least: `Index Scan`/`Index Only Scan`/`Bitmap Heap Scan` (positive signal — confirms an index *is* being used, important for #63's negative-confirmation case below), and filesort-equivalent (`Sort` node with a large row estimate, relevant to the existing `order_by_index` heuristic).
4. Wire this into `collect_facts()`/`PostgresCollector` as a fallback: if `request.explain_plan` is present, parse it (no DSN needed); only fall back to a live connection attempt if a DSN is configured and no pasted plan was given. Today those are mutually exclusive-in-practice paths that should both feed the same `AnalysisFacts`.

### #62 — MySQL EXPLAIN parser

1. Same shape as #61, new `parse_mysql_explain(raw: str) -> PlanArtifact | None`. MySQL's `EXPLAIN FORMAT=JSON` output has a different tree shape (`query_block.table.access_type`, not `Node Type`) — this is not a copy-paste of the Postgres parser, it's a distinct format per the UI's own placeholder example (`"access_type": "ALL"` for a full scan, the MySQL equivalent of `Seq Scan`).
2. `collectors/mysql.py`'s stub gets a real `collect()` that at minimum parses `request.explain_plan` the same way the Postgres path does in #61 — replace the "full impl coming Week 2" comment, since this only needs the pasted-text path to close the UI's claim, not a live DSN connection (that part can stay out of scope, matching Postgres's existing optional-DSN pattern).
3. Map `access_type: "ALL"` (full table scan) to the same severity/finding shape as Postgres's `Seq Scan` finding, so #63's cross-referencing logic in the next section doesn't need dialect-specific branches later.

### #63 — Cross-reference parsed plan against heuristic suggestions (the part that makes the UI claim true)

This is the actual point of the whole chain — #61/#62 without this just produce another unused `facts` blob.

1. After `collect_facts()` returns a populated `AnalysisFacts.plan`, cross-reference its parsed nodes against the columns/tables already implicated in `optimization_suggestions` from `index_recommender.py`. Two directions, both matter:
   - **Confirmation** (the UI's literal promise): a suggestion whose table shows a `Seq Scan`/`access_type: ALL` in the real plan gets `evidence_level` upgraded to `"schema-verified"` (reusing the existing tier per the recommendation above) — this is the estimated→schema-verified transition the UI already advertises.
   - **Contradiction** (equally important, currently has zero handling anywhere): if the plan shows an `Index Scan` already being used on a column a heuristic flagged as unindexed, that heuristic's suggestion is likely wrong (schema drifted, or the heuristic's column-extraction missed an existing index) — don't just silently upgrade evidence, actively flag the mismatch so a wrong suggestion doesn't ship with false confidence. A new `evidence_level` value or a `plan_contradicts: bool` field on the suggestion is reasonable here — pick whichever fits the existing schema shape better without over-engineering a new UI state.
2. **Frontend**: `OptimizationSuggestions.jsx` already renders `evidence_level` badges (confirmed by #118's diff touching this same file) — a suggestion upgraded to `schema-verified` via plan cross-reference should read identically to one upgraded via schema DDL, since that's literally what the existing UI copy promises ("upgrades... to schema-verified"). No new badge needed for the confirmation case; the contradiction case does need something, even if it's just a distinct warning icon/tooltip in v1.
3. **Tests**: this is the one place in this chain where a wrong answer is worse than no answer — a false "schema-verified" upgrade actively misleads a user into trusting a bad recommendation. Prioritize test coverage on the cross-referencing logic itself (does it correctly match plan table/column names back to suggestion table/column names — string-matching table aliases against real plan relation names is the likely fragile point) over broadening node-type coverage further.

## Explicit non-goals for v1

- Not building live DB connection wiring beyond what already exists for Postgres (`POSTGRES_DSN`) — that's `#57`, separately scoped, and this chain's core value (making the paste-in claim true) doesn't need it.
- Not parsing Oracle (`DBMS_XPLAN.DISPLAY`) or SQL Server plan output, even though the UI already shows placeholders for both — Postgres and MySQL only, matching the issue numbers actually filed (`#61`/`#62`). Flag this: the UI placeholder for Oracle/SQL Server sets the same expectation this whole doc is about fixing for Postgres/MySQL — worth a follow-up issue, not silently expanding this chain's scope.
- Not attempting to auto-detect which dialect's format was pasted from content alone if `db_type` disagrees with what was pasted — trust the `db_type` the request already carries (the frontend already collects EXPLAIN text per-dialect via `explainHint[dbType]`, so a mismatch would be a user error, not something to silently guess around).
- Not changing the `#60` LLM-prompt-context behavior (raw text still gets passed to the LLM as narrative) — that's additive and orthogonal to the structured parsing this chain adds.

## Suggested sequencing

`#61` first (extends existing partial code, lowest risk), `#62` second (same shape, new dialect, no shared code with #61 to block on), `#63` last and by far the most carefully — it's the one part of this chain that changes what users are told to trust, not just what gets parsed.
