# Changelog

All notable changes to QueryTuner are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Dedicated `/pricing` route — Free vs Pro feature comparison table + pricing cards,
  linked from the main nav. The Phase 4 audit's only real ("not just wording") gap
  (#51, PR #162, `e2709f1f`)

### Fixed
- `parse_schema_ddl()` silently dropped columns whose SQL Server type was itself
  bracket-wrapped (`[varchar](50)`, `[uniqueidentifier]`, `[int]`) — exactly what
  SSMS's own "Script Table as CREATE" produces. A DDL block using this style
  throughout returned an empty schema for the whole table (#126, PR #161, `7010cc9f`)
- CORS allowlist only covered the bare domain (`querytuner.com`); the deployed
  frontend's real browser Origin is `www.querytuner.com` (DNS/Vercel redirect),
  so every real visitor's `/analyze`, `/capabilities`, and `/usage` call was
  silently CORS-blocked in production despite succeeding server-side. Both
  origins now explicitly allowed (#163, `9156cb86`)

### Tests
- #151 (confidence labeling on findings) audited against its acceptance
  criteria and found already fully satisfied by the three-tier `evidence_level`
  system shipped a month earlier (`1fcb82a0`) — deterministic/schema-verified
  count as "certain," needs-runtime-evidence as "inferred," and index
  recommendations already upgrade tiers exactly when schema resolves the
  uncertainty, the literal behavior the issue asked for. Added regression
  tests pinning `evidence_level` per heuristic type, since nothing previously
  asserted the tier itself — only that a type fires

### Security
- 7 Dependabot alerts on `frontend/` (6 high, 1 moderate) resolved via
  `npm audit fix` — all within existing `package.json` semver ranges, no
  direct dependency version bumped, only `package-lock.json` changed.
  Notably `@clerk/clerk-react` (5.61.3 → 5.61.9): an authorization bypass
  when combining organization, billing, or reverification checks
  (GHSA-w24r-5266-9c3c) — directly relevant here since Clerk gates the
  Free/Pro tier boundary. Also `postcss` (8.5.13 → 8.5.26, two path-traversal
  advisories via sourcemap auto-loading), `nanoid`, `js-yaml`, and
  `brace-expansion` (all transitive, dev-tooling only)

## [0.3.0] — 2026-08-28

Phase 4 (auth + payments) is live in production and independently audited
against its original GitHub acceptance criteria (`docs/querytuner-phase4-audit.md`)
— the one live gap the audit found (`#53`, unenforced Pro-tier LLM routing)
was fixed the same day. Also includes the first batch of Phase 5 quick
wins, the EXPLAIN plan parser chain, Quiz Mode, batch workload analysis,
the report management dashboard's completion, and three bugs found
live-testing the deployed site.

### Added
- Client-side query sanitizer (commit 042a23fd):
  - Table and column names replaced with dummy values (`table_a`, `col_b`) in browser
    before any data sent to server. Real schema names never reach QueryTuner's backend
    or Supabase.
  - Substitution map stored in React `useState` only — never localStorage, never
    server, gone on page refresh.
  - "Restore original names" button on DDL output applies reverse substitution —
    produces copy-pasteable DDL with real table names.
  - Same map applied to EXPLAIN plan if provided, for consistency.
  - 15 tests via vitest.
- 4 new heuristic rules (total now 16):
  - `not_in_nullable` (high, deterministic) — NOT IN with nullable subquery returns zero rows
  - `case_in_predicate` (high, deterministic) — CASE in WHERE prevents index use
  - `or_expansion` (medium, estimated) — OR on different columns may force full scan
  - `cte_multiple_references` (medium, estimated) — CTE referenced 2+ times may re-execute
- Three-tier evidence labelling system: deterministic / schema-verified / needs-runtime-evidence
- Rollback DDL per dialect on all index recommendations (5 dialect-correct statements)
- Privacy warning on share button and report page
- AI Insights section on shareable report page
- Report page brought to full parity with main app: evidence badges, DDL blocks, rollback
  toggles, Query Diagnosis section, AI Insights
- `findKey()` resilient JSON parser for AI output — handles key name variations across LLM
  providers
- OpenAI (recommended) label added to AI provider dropdown (UI label change only — provider
  selection remains user's choice)
- Phase 4: Authentication + Stripe payments
- Query history for Pro users — `GET /history`, gated server-side on Pro status (#54, `db2f1306`)
- Shareable report link expiration (90-day default) + owner-initiated early revoke via
  `DELETE /report/{id}` (#116, `860950e3`)
- Composite index recommendations now order columns by standard convention (equality →
  JOIN → range → sort) instead of raw extraction order (#117, `7121cc12`)
- Write/storage cost estimate alongside every index recommendation's existing read-side
  benefit estimate (#118, `4e747b95`)
- EXPLAIN plan parser chain — full acceptance-criteria coverage: remaining Postgres node
  types (Merge Join, Hash Aggregate, Group Aggregate) + EXPLAIN ANALYZE actual-time/rows
  parsing, MySQL plain tabular EXPLAIN parsing + explicit `key=NULL` flagging + `Using
  filesort`/`Using temporary` detection, and `full_scan_risk`/`order_by_no_limit`/
  `function_in_where` cross-referencing against the parsed plan (#61, #62, #63, `428facb5`)
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
- User report dashboard (History page) completed — sanitized/unsanitized indicator
  and a "Show sanitized only" filter (new `analyses.was_sanitized` column, migration
  009, self-reported by the client's own sanitizer state), a delete button wired to
  the existing `DELETE /report/{id}` (#116), and a copy-link button per row (#124,
  PR #159, `aedf65fe`)

### Fixed
- `schema_verified` terminology replaces "confirmed" — more accurate, does not imply planner
  will use the index
- CSS wildcard reset specificity conflict on report page — was zeroing Tailwind utility
  classes, fixed with `:where()` wrapper
- Markdown fence regex anchoring in AI JSON parser — trailing LLM prose after closing fence
  was causing raw JSON display
- QueryInput help text updated to schema-verified
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
- **Quiz Mode's AI Insights panel leaked the quiz answer before reveal** — the
  panel's render condition had no reference to the quiz's reveal state at all, so it
  rendered unconditionally whenever AI insights was on, showing the recommended DDL
  right under an unanswered question. Now gated behind the same quiz-then-reveal
  condition `OptimizationSuggestions` already uses. Found live-testing the deployed
  site (PR #157, `7746df08`)
- AI provider dropdown could get stuck showing a disabled "OpenAI (Pro only)" option
  as selected with no way back (a stale selection from before the `#53` Pro-gate, or
  after Pro status lapsed), and confirmed Pro users weren't defaulted to OpenAI
  either despite it being the recommended, already-paid-for option. Now resets a
  stale/disallowed selection automatically and auto-selects OpenAI once for a fresh
  Pro session, without fighting a later manual switch back (PR #157, `7746df08`)
- CORS `allow_origins` was `"*"` — a known dev-mode leftover flagged ahead of launch
  readiness. Replaced with a real allowlist (`settings.frontend_url` +
  `localhost:3000` for local dev), reusing the existing `FRONTEND_URL` setting
  already used elsewhere — no new env var (PR #158, `deacb6ca`)

### Tests
- 316 backend tests passing (1 intentional xfail — LATERAL join correlated-column
  detection), up from 102 at v0.2.0
- 59 frontend tests passing (vitest) — all added this cycle; v0.2.0 had none

## [0.2.0] — 2026-07-20

### Added
- Schema-aware analysis: paste `CREATE TABLE` DDL for confirmed index recommendations
  with real table names
- `parse_schema_ddl()` and `get_indexed_columns()` in `query_parser.py`
- `confirmed`/estimated flag per suggestion (`confirmed: true` when cross-referenced
  against provided schema)
- Schema Context section in Query Diagnosis output
- Schema DDL accordion in QueryInput UI
- EXPLAIN plan paste-in field (QueryInput + backend wiring)
- Enterprise-grade rendering: structured AI Insights panel, human-readable suggestion
  labels, styled code blocks
- Risky assumptions rendered as readable warning cards
- "✓ Confirmed by AI" badge on heuristically-confirmed findings, with the two panels
  reframed as complementary (heuristic vs. AI-additive) rather than duplicated
- `migrations/` folder with versioned schema files
- `dialect_config.py`: single source of truth for dialect-aware DDL, rewrites, and
  LLM prompts across 5 dialects (Phase 1.7)

### Fixed
- ILIKE filter columns not detected (was using `\bLIKE\b` regex)
- USING clause joins producing zero suggestions
- Multi-condition ON clause only scanning the first condition
- Oracle ROWNUM false positive as an indexable column
- Window function ORDER BY triggering a false `order_by_no_limit`
- Quoted identifiers (`"Column Name"`) dropped from extraction
- `schema_info` stale closure in `handleAnalyze`'s `useCallback`
- QueryDiagnosis rendering raw markdown fence characters
- AI Insights rendering raw JSON to users
- Risky assumptions rendering raw JSON objects instead of the note/column fields
- "Sub-5ms heuristics" inaccurate latency claim removed from the UI and README

### Testing
- Grew from ~30 tests to 94 passing tests, 1 intentional xfail (LATERAL join
  correlated-column detection)

## [0.1.0] — 2026-05-01

### Added
- Core heuristic engine: 12 rules across 5 database dialects
- `query_parser.py`: SQL text to structured dict
- `index_recommender.py`: 4-pass index opportunity detection
- `optimizer.py`: 7 SQL rewrite rules (YEAR, LIKE, SELECT *, LOWER)
- `explainer.py`: plain-English diagnosis with maintenance commands
- LLM layer: HuggingFace (primary) + OpenAI (optional)
- Supabase persistence + shareable `/report/:id` URLs
- Enterprise UI shell: Header, Hero, Footer, Toast
- Google Analytics 4: typed event tracking functions
- Two-column responsive layout
- ShareButton with dark theme
- ReportPage: standalone shareable read-only report
- GitHub Actions CI: pytest on every push
- Supabase keep-alive workflow
- pytest suite covering the core heuristic engine and index recommender
