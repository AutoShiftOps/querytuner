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

- AI insights depend on HuggingFace free tier availability. Cold starts (model
  loading) can add 20-30 seconds of latency.
- LLM output structure (JSON) is not guaranteed — the fallback renders plain text
  when JSON parsing fails.
- The LLM does not have access to the database schema unless `schema_info` is
  provided in the request.

## Performance

- Analysis time includes LLM latency when AI is enabled. Heuristic-only analysis is
  typically under 200ms.
- Rate limit: 10 requests per IP per minute (in-memory, resets on server restart).
- Supabase free tier pauses after 7 days of inactivity. A GitHub Actions keep-alive
  workflow (`.github/workflows/keep-supabase-alive.yml`) pings it every 3 days.

## What is not supported (yet)

- Live database connections (Phase 5)
- Query history and trend analysis (Phase 4+)
- Multi-statement SQL (only single SELECT/DML statements)
- Stored procedures and functions
- DDL statements (`CREATE`, `ALTER`, `DROP`) as the analysed query
- Authentication and user accounts (Phase 4)
