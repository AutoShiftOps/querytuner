# QueryTuner — Known Limitations

This document exists so users understand what the tool can and cannot do, and so
contributors know what's genuinely in scope vs out of scope. Documenting limitations
honestly is part of the engineering discipline behind this project.

## Heuristic analysis

- All suggestions have `confirmed: false` unless schema DDL is provided. Heuristics
  analyse query syntax only — they do not connect to a live database and cannot verify
  actual table sizes, row counts, or existing index usage.
- The LATERAL join gap: correlated columns inside `LATERAL` joins are not detected
  (tracked as `xfail` via `test_lateral_join_correlated_column_detected` in
  `test_comprehensive.py`).
- Composite index confirmation: multi-column `confirmed: true` requires all columns
  to match the schema individually. The alias resolver uses prefix matching, which may
  not resolve all alias patterns.
- Implicit cast detection covers PostgreSQL `::`, `CONVERT()`, and common ID column
  patterns. Dialect-specific cast functions beyond these are not detected.

## Schema parsing

- `parse_schema_ddl()` supports PostgreSQL, MySQL, Oracle, SQL Server, and SQLite DDL
  syntax.
- Complex constraint expressions (`CHECK` with subqueries, computed columns) are
  skipped.
- Schema inference from the query alone (without DDL) is not supported. Users must
  paste `CREATE TABLE` statements explicitly.

## Optimized query output

- The optimized query is a suggestion for developer review, not an automatically
  verified rewrite.
- Re-analyzing an optimized query will produce new findings because QueryTuner has no
  memory of prior runs — each analysis is stateless.
- CTE refactor hints are structural templates, not semantically-verified rewrites.

## LLM layer

- AI providers: Anthropic Claude (default; free signed-in users get 3 AI analyses per
  rolling 24h on FREE_AI_MODEL) and OpenAI gpt-4o-mini (Pro). Hugging Face was removed in
  Oct 2026 after repeated 402 (out of credits) failures; "huggingface" in API requests is
  treated as "anthropic".
- The free-tier AI cap and the Pro daily ceiling are in-memory: they reset when the API
  restarts and are per instance.
- LLM output structure (JSON) is not guaranteed — the fallback renders plain text
  when JSON parsing fails.
- The LLM does not have access to the database schema unless `schema_info` is
  provided in the request.

## Performance

- Analysis time includes LLM latency when AI is enabled. Heuristic-only analysis is
  typically under 200ms.
- Rate limit: 10 requests per IP per minute, plus 5 analyses/day/IP for
  anonymous (signed-out) callers. Both are in-memory (`defaultdict` state in
  `app/main.py`) — they reset on every deploy/restart and are per-process, so
  they would stop working correctly (each instance would enforce its own
  separate quota instead of one shared one) if this service is ever scaled to
  more than one Render instance. Acceptable for the current single-instance
  Starter deployment; revisit with a shared store (e.g. Redis) before scaling
  horizontally.
- Query size: the heuristic engine analyses queries up to 32,000 characters
  (`MAX_QUERY_CHARS`). Queries over that limit are rejected with a `400
  query_too_large` response rather than a raw error. Queries over 8,000 characters
  are truncated for the AI call only (with a note appended so the LLM knows the
  query was shortened) — the full query is still analysed by the heuristic engine
  regardless of AI truncation.
- Supabase free tier pauses after 7 days of inactivity. A GitHub Actions keep-alive
  workflow (`.github/workflows/keep-supabase-alive.yml`) pings it every 3 days.

## What is not supported (yet)

- Live database connections (Phase 5)
- Query history and trend analysis (Phase 4+)
- Multi-statement SQL (only single SELECT/DML statements)
- Stored procedures and functions
- DDL statements (`CREATE`, `ALTER`, `DROP`) as the analysed query
- Authentication and user accounts (Phase 4)

## Privacy and data handling

- Query text is sent to the backend for analysis and stored in Supabase when a
  shareable URL is generated.
- Use the client-side sanitizer to replace proprietary table and column names before
  analysis if your organisation has policies against sending schema information to
  third-party services.
- The sanitizer substitution map is stored in browser memory only and is lost on page
  refresh — this is intentional.
- Shareable report URLs store the sanitized version of the query — original names are
  never recoverable from the report URL.
- If a query was sanitized using the client-side sanitizer before analysis, the shared
  report URL will display dummy table and column names (table_a, col_b etc). This is
  correct and intentional — original names are never stored anywhere and cannot be
  recovered from the report URL. The substitution map exists only in the browser
  session that ran the analysis.
