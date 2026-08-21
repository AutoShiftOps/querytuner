# Comments for #61, #62, #63 — do NOT close any of these

Verified against the actual issue bodies (not just ROADMAP one-liners) that real, specific acceptance criteria are unmet on all three. Post these as comments, leave all three **open**.

---

### #61 — comment
> Partially shipped in `134efda3` — `backend/app/tools/plan_parsers/postgres.py` now parses pasted plain-text and JSON-format Postgres EXPLAIN output (previously only a live DB connection's JSON was parsed, and that path was never wired to what users actually paste).
>
> Checked against this issue's own acceptance criteria and two things are still open: (1) node-type coverage is 7 of the 10 listed — `Merge Join`, `Hash Aggregate`, and `Group Aggregate` aren't detected; (2) `EXPLAIN ANALYZE`'s actual-rows/actual-timing data isn't extracted — only estimated cost/rows from plain `EXPLAIN` are parsed today. See `docs/querytuner-explain-parser-gap-followup.md` for the specific remaining scope. Leaving open against these two criteria.

### #62 — comment
> Partially shipped in `134efda3` — `backend/app/tools/plan_parsers/mysql.py` now parses pasted MySQL `EXPLAIN FORMAT=JSON` output.
>
> Checked against this issue's own acceptance criteria and several are still open: plain tabular `EXPLAIN SELECT ...` output isn't parsed (JSON-only today); `key=NULL` isn't explicitly flagged as a distinct signal from `type=ALL`; and `Using filesort`/`Using temporary` (from MySQL's `Extra` field) aren't detected anywhere yet. See `docs/querytuner-explain-parser-gap-followup.md`. Leaving open.

### #63 — comment
> Partially shipped in `134efda3` — `backend/app/tools/plan_crossref.py` cross-references a parsed EXPLAIN plan against `index_recommender.py`'s suggestions (join-key, WHERE-filter, ORDER BY, GROUP BY, partial-index-candidate types), upgrading confirmed ones and flagging contradicted ones rather than silently trusting either — this is what makes `QueryInput.jsx`'s existing "upgrades findings to schema-verified" claim true for that suggestion family.
>
> Checked against this issue's own acceptance criteria (the six-heuristic upgrade table) and coverage is narrower than what's listed: `full_scan_risk`, `function_in_where`, and `order_by_no_limit` (existing heuristics in `sql_analyzer.py`) aren't cross-referenced at all yet, and `filesort_detected`/`temp_table_detected` (MySQL-`Extra`-field-based) don't exist anywhere in the codebase yet — new detection logic, not just wiring. Field naming also differs from what's specified here (`confirmed`/`evidence` in this issue's ask vs. the shipped `plan_verified`/reused `evidence_level`/`plan_contradicts` — see the follow-up doc for the reasoning; recommend treating the shipped naming as the intended final shape and updating this issue's acceptance criteria to match, rather than adding a second parallel field set). See `docs/querytuner-explain-parser-gap-followup.md` for full remaining scope and suggested sequencing. Leaving open.
