# Changelog

All notable changes to QueryTuner are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
- Phase 4: Authentication + Stripe payments

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

## [0.1.0] — 2026-02-15

### Added
- Core heuristic engine: 12 rules across 5 database dialects
- `query_parser.py`: SQL text to structured dict
- `index_recommender.py`: 4-pass index opportunity detection
- `optimizer.py`: 7 SQL rewrite rules (YEAR, LIKE, SELECT *, LOWER)
- `explainer.py`: plain-English diagnosis with maintenance commands
- `dialect_config.py`: single source of truth for 5 dialects
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
