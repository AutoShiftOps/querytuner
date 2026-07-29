# Changelog

All notable changes to QueryTuner are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

These changes will become v0.3.0 when Phase 4 ships.

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

### Fixed
- `schema_verified` terminology replaces "confirmed" — more accurate, does not imply planner
  will use the index
- CSS wildcard reset specificity conflict on report page — was zeroing Tailwind utility
  classes, fixed with `:where()` wrapper
- Markdown fence regex anchoring in AI JSON parser — trailing LLM prose after closing fence
  was causing raw JSON display
- QueryInput help text updated to schema-verified

### Tests
- 102 passing tests (up from 94)
- `test_comprehensive.py` — 22 tests covering 6 edge case categories
- `test_schema_parser.py` — 43 tests; covers PostgreSQL, MySQL, Oracle, and SQL Server DDL
  parsing (SQLite schema parsing not yet covered)

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
