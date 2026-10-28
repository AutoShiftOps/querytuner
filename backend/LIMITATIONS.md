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

## Rewritten query / targeted fixes / annotated query output

QueryTuner shows up to three different "fixed query" outputs, and they are not
interchangeable:

- **Rewritten Query** (AI) — a full AI-generated rewrite, shown for smaller,
  single-statement queries. Passed through `rewrite_check.py` before reaching the UI:
  a rewrite that would drop a table, drop an output column, or has unbalanced
  parentheses/a stray comma is discarded and replaced with an explicit "AI rewrite not
  shown — it would change your results" note, rather than being shown unverified.
- **Targeted Fixes** (AI) — for queries over 3,000 characters or multi-statement
  batches, the model is asked for up to 6 individually-verifiable before/after
  snippets instead of one monolithic rewrite (safer for a query shape where a single
  AI-rewritten block risks silently changing results — correlated subqueries, temp
  tables, heavy CASE logic). Each fix is kept only if its "before" text is actually
  present in the query and it doesn't change paren balance.
- **Annotated Query** (deterministic, `optimizer.py`) — always available, no AI
  required. Adds safe inline comments only (e.g. flagging a `SELECT *` or a
  function-wrapped WHERE column) — it never restructures or rewrites the query. This
  used to be labeled "Optimized Query," which read as a genuine rewrite; it was
  relabeled specifically to avoid that confusion.

None of the three are automatically verified against a live database — `rewrite_check.py`
checks structural safety (table/column set, paren balance), not actual query semantics
or output equivalence under real data.

Re-analyzing a rewritten/fixed/annotated query as a new input will produce its own,
independent findings — QueryTuner does not track "this is a rewrite of that earlier
query" across analyses; each `/analyze` call is evaluated on its own.

## Accounts and billing

- Sign-in is handled by Clerk (JWT, verified server-side against Clerk's own JWKS). User
  accounts and auth are live, not a future phase.
- Stripe is integrated on the backend (webhook at `/webhook/stripe`, billing-portal
  session creation) and the Pro upgrade UI exists (`PricingPage.jsx`, `UpgradeModal.jsx`),
  but live checkout is intentionally disabled by default — gated behind the
  `VITE_PRO_CHECKOUT_ENABLED` frontend flag, which defaults to off. Until that's
  explicitly turned on, every upgrade CTA shows a "Pro is coming soon — request free
  early access" flow instead (a `mailto:` link, handled manually, not an automated
  grant). See `docs/pro-checkout-coming-soon.md` for why and how to re-enable it.

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
- Trend analysis across query history (basic persisted history is supported — see
  `GET /history`, Pro-only — but there's no trend/comparison view over it yet)
- Stored procedures and functions as the analysed query itself (a multi-statement
  batch that merely *contains* DML against temp tables/table variables, like a real
  SQL Server report-generation script, is supported — see below)
- DDL statements (`CREATE`, `ALTER`, `DROP`) as the sole analysed query, outside of
  one inside a larger supported multi-statement batch (e.g. `CREATE TABLE #temp`
  followed by `INSERT`/`SELECT` against it)
- Cross-database execution plan risk normalization (Phase 5)

### Multi-statement SQL: supported, with one narrower scope limit

Multi-statement T-SQL batches (`DECLARE`/temp-table/`INSERT`/`SELECT` scripts) **are**
supported — this was a real gap that was found and fixed via real customer report data
in October 2026 (clause extraction now stops at the next top-level statement-starting
keyword or set operator, not just a semicolon, since real-world batches often omit
semicolons between statements entirely). "Tables accessed," "Grouped by," and
"WHERE clause" all reflect the whole batch, not just the first statement, and queries
over 3,000 characters or spanning multiple statements get the "Targeted Fixes" AI
treatment described above specifically because of this.

The one remaining scope limit: `query_parser.py`'s `_extract_table_aliases()` (used
only internally, for resolving a table alias in generated DDL hints when no
`schema_info` was pasted) is still first-statement-scoped by design, per its own
docstring. A DDL hint referencing a table only introduced in a later statement of the
batch may still fall back to a placeholder rather than resolving the real name.

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
