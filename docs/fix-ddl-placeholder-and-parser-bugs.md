# Backend fixes: DDL placeholder bug, GROUP BY overrun, table-name truncation

Fixes bugs #1, #2, #3 from the QA findings doc (report ID
`8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e`). All three trace back to
`backend/app/tools/query_parser.py`, which the file's own docstring admits
is built only for "common single-statement SELECT queries" — these fixes
make its clause-extraction and table-ref parsing safe for the
multi-statement, bracket-quoted T-SQL batches real users actually submit,
without a full rewrite.

---

## Tracking — create these two GitHub Issues first

**Issue A — title:** `Index/WHERE DDL hints fall back to unresolved <alias_table> placeholder`

```
Every finding's single-column DDL suggestion (join-key, WHERE-column)
resolves the real table name only from user-pasted `schema_info` DDL. Since
almost no real user pastes a schema, `_resolve_real_table()` in
index_recommender.py returns None for virtually every real report, and the
DDL hint falls back to a literal, non-executable `<alias_table>` placeholder
— e.g. `CREATE NONCLUSTERED INDEX idx_SH_No_ ON <SH_table>(No_) ...`.

This is the default behavior, not an edge case: it fires whenever
schema_info isn't supplied, i.e. on nearly every report. Found via report
8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e.

Fix: fall back to the alias→table map already derivable from the query's own
FROM/JOIN clauses when no schema_info is pasted.
```

**Issue B — title:** `GROUP BY / table-name extraction breaks on multi-statement T-SQL batches`

```
query_parser.py is documented as built for single-statement SELECT queries
only. Two concrete failures on a real multi-statement batch (DECLARE/temp
table/INSERT/SELECT script, report 8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e):

1. "Grouped by" in the Query Summary panel shows the entire rest of the
   script (hundreds of lines) instead of the real GROUP BY column. Root
   cause: _extract_clause() has no statement-boundary (semicolon) awareness
   — when no top-level stop keyword exists later in the script, it captures
   everything to the end of the text.

2. "Tables accessed" truncates mid-identifier, e.g.
   "[dbo].[Metropolitan$Sales" instead of the full bracketed name. Root
   cause: _clean_table_ref() splits on plain whitespace to strip a table
   alias, which breaks SQL Server bracket-quoted identifiers that legally
   contain spaces, e.g. [Metropolitan$Sales Header].

Fix: bound clause extraction at top-level semicolons; make alias-stripping
bracket-aware.
```

---

## 1. Fix `_clean_table_ref` — bracket-quoted identifiers with spaces (bug #3)

In `backend/app/tools/query_parser.py`, near the top-level helpers (after
`_find_top_level_keyword_pos`, before the `_extract_clause` docstring —
exact placement doesn't matter, just keep it with the other module-level
helpers):

```diff
+# A table/column reference's qualified-name portion: one or more
+# dot-separated segments, each either a bracket-quoted identifier
+# ([Metropolitan$Sales Header] — SQL Server lets these contain spaces),
+# a double-quoted identifier, or a plain identifier. Used to find where a
+# qualified name ends and a trailing alias begins without breaking on
+# whitespace *inside* a bracketed segment (Issue: "Tables accessed"
+# truncating mid-identifier, e.g. "[dbo].[Metropolitan$Sales" — plain
+# str.split() cut the bracketed name itself, not just the alias).
+_QUALIFIED_NAME_RE = re.compile(
+    r"^((?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z0-9_]+)"
+    r"(?:\.(?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z0-9_]+))*)"
+)
```

Then replace `_clean_table_ref`:

```diff
     def _clean_table_ref(self, t: str) -> str:
         """
         Turn 'orders o' or 'schema.orders AS o' into 'orders' or 'schema.orders'
         without being too smart.
+
+        Bracket-aware (Issue: see _QUALIFIED_NAME_RE above) — a plain
+        whitespace split breaks on SQL Server identifiers like
+        [Metropolitan$Sales Header] that contain a space inside the
+        brackets. Try the qualified-name match first; fall back to the
+        original whitespace-split behavior for anything it doesn't
+        recognize (double safety net, doesn't regress non-bracketed input).
         """
         tt = t.strip()
+        m = _QUALIFIED_NAME_RE.match(tt)
+        if m:
+            return m.group(1)
         # remove trailing alias
         # split on whitespace at top-level (no parens expected here usually)
         parts = tt.split()
         if not parts:
             return tt
         # handle "schema.table"
         return parts[0].strip().strip('"')
```

## 2. Fix `_extract_clause` — bound clause extraction at top-level `;` (bug #2)

Still in `query_parser.py`:

```diff
 def _extract_clause(sql: str, start_kw: str, end_kws: list[str]) -> str:
     """
     Extract clause body appearing after start_kw up to the earliest of end_kws, all at top-level.
     Example: start_kw=" where ", end_kws=[" group by ", " order by ", " limit ", " fetch "]
+
+    Issue: on a multi-statement batch (DECLARE/INSERT/SELECT script), a
+    clause near the end of one statement could previously run past that
+    statement's own semicolon and swallow everything up to the next
+    matching end keyword found anywhere later in the WHOLE script — or, if
+    none exists at top level later on, to the literal end of the text. A
+    top-level `;` is now always an implicit stop boundary, same as any of
+    end_kws, since no clause can legitimately span past its own statement.
     """
     sql = re.sub(r"\s+", " ", sql).strip()
     start = _find_top_level_keyword_pos(sql, start_kw, 0)
     if start == -1:
         return ""

     body_start = start + len(start_kw)
     end_positions = []
     for ek in end_kws:
         p = _find_top_level_keyword_pos(sql, ek, body_start)
         if p != -1:
             end_positions.append(p)
+    semi_pos = _find_top_level_keyword_pos(sql, ";", body_start)
+    if semi_pos != -1:
+        end_positions.append(semi_pos)

     body_end = min(end_positions) if end_positions else len(sql)
     return _strip_trailing_semicolon(sql[body_start:body_end].strip())
```

This one change protects every caller of `_extract_clause` — `_extract_where`,
`_extract_group_by`, `_extract_having`, `_extract_order_by`, and the FROM-body
extraction inside `_extract_tables` — from running past a statement boundary.
It cannot make any currently-correct single-statement extraction worse (a
semicolon never appears before a query's existing end keywords in a
single-statement query), so this is safe for every query the parser already
handles correctly today.

## 3. Add a bracket-aware alias→table map, use it as a DDL-hint fallback (bug #1)

### 3a. New function in `query_parser.py`

Add near `_extract_tables`/`_extract_joins`:

```python
def _extract_table_aliases(self, query: str) -> dict[str, str]:
    """
    Best-effort alias -> real table name map, built directly from this
    query's own FROM/JOIN clauses — not from pasted schema_info DDL.

    Used as a fallback in index_recommender.py's DDL-hint templating: when
    no schema_info is supplied (the common case for real users), there was
    previously no way to resolve e.g. `SH` -> `[dbo].[Metropolitan$Sales
    Header]`, so generated DDL fell back to a literal `<SH_table>`
    placeholder (Issue: non-executable DDL in finding cards).

    Scope: covers the query's base FROM table(s) and every JOIN target,
    using the same bracket-aware qualified-name matching as
    _clean_table_ref (see _QUALIFIED_NAME_RE). Like the rest of this
    parser, this is single-statement-scoped — on a multi-statement batch it
    reflects the first statement's FROM/JOIN only, which is the statement
    index_recommender's findings are generated against anyway.
    """
    q = _strip_trailing_semicolon(query)
    aliases: dict[str, str] = {}

    from_body = _extract_clause(q, " from ", [" where ", " group by ", " order by ", " limit ", " fetch "])
    if from_body:
        cut = len(from_body)
        for kw in [" join ", " left join ", " right join ", " inner join ", " full join ", " cross join "]:
            p = from_body.lower().find(kw)
            if p != -1:
                cut = min(cut, p)
        base = from_body[:cut].strip()
        for ref in _split_top_level_commas(base):
            self._collect_alias(ref, aliases)

    join_pattern = re.compile(
        r"\b(?:left|right|inner|full|cross)?\s*join\s+"
        r"((?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z0-9_]+)(?:\.(?:\[[^\]]+\]|\"[^\"]+\"|[A-Za-z0-9_]+))*)"
        r"(\s+(?:as\s+)?[A-Za-z_][A-Za-z0-9_]*)?",
        re.IGNORECASE,
    )
    for m in join_pattern.finditer(q):
        table = m.group(1).strip()
        alias_part = (m.group(2) or "").strip()
        alias = re.sub(r"(?i)^as\s+", "", alias_part).strip()
        if alias and alias.lower() not in {"with", "on"}:
            aliases[alias] = table

    return aliases

def _collect_alias(self, ref: str, aliases: dict[str, str]) -> None:
    """Helper for _extract_table_aliases: split one FROM-clause table
    reference (e.g. '[dbo].[Metropolitan$Sales Header] SH with(nolock)')
    into (table, alias) using the same bracket-aware qualified-name match
    _clean_table_ref uses, and record it if an alias is present."""
    tt = ref.strip()
    m = _QUALIFIED_NAME_RE.match(tt)
    if not m:
        return
    table = m.group(1)
    rest = tt[m.end():].strip()
    rest = re.sub(r"(?i)\s*with\s*\([^)]*\)\s*$", "", rest).strip()
    rest = re.sub(r"(?i)^as\s+", "", rest).strip()
    if rest and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rest):
        aliases[rest] = table
```

Wire it into `parse()`'s return dict:

```diff
         parsed = {
             "query_type": self._get_query_type(stmt),
             "tables": self._extract_tables(q),
+            "table_aliases": self._extract_table_aliases(q),
             "columns": self._dedupe_keep_order(columns),
```

And into `_empty()`'s fallback dict:

```diff
         return {
             "query_type": "UNKNOWN",
             "tables": [],
+            "table_aliases": {},
             "columns": [],
```

### 3b. Thread it through `index_recommender.py` as a fallback

`recommend()` already receives the full `parsed` dict (sql_analyzer.py's
call site passes `parsed=parsed`), so pull `table_aliases` out there:

```diff
     def recommend(
         self,
         query: str,
         parsed: dict[str, Any],
         db_type: str = "postgresql",
         schema_info: str | None = None,
     ) -> list[dict[str, Any]]:
         suggestions: list[dict[str, Any]] = []

         # Issue #8: parse schema DDL (if provided) to confirm/suppress recommendations
         schema = parse_schema_ddl(schema_info) if schema_info else {}
         already_indexed = get_indexed_columns(schema_info) if schema_info else {}
+
+        # Fallback source for table-name resolution when no schema_info was
+        # pasted — derived directly from the query's own FROM/JOIN clauses
+        # (query_parser.py's _extract_table_aliases). Fixes DDL hints
+        # falling back to a literal <alias_table> placeholder on the common
+        # case where a user doesn't paste a schema.
+        table_aliases = (parsed or {}).get("table_aliases") or {}
```

Update `_real_table` to accept and use it:

```diff
-    def _real_table(self, alias: str | None, schema: dict[str, dict[str, str]]) -> str | None:
-        return _resolve_real_table(alias, schema)
+    def _real_table(
+        self,
+        alias: str | None,
+        schema: dict[str, dict[str, str]],
+        table_aliases: dict[str, str] | None = None,
+    ) -> str | None:
+        resolved = _resolve_real_table(alias, schema)
+        if resolved:
+            return resolved
+        if alias and table_aliases:
+            return table_aliases.get(alias)
+        return None
```

Update every call site in `recommend()` (and in `_detect_composite_opportunity`,
and `_ddl_hint`/`_ddl_partial_hint`) to pass `table_aliases` through — same
mechanical change at each of these line numbers (as of commit `02722d4`):

- line 283 (`real_table = _resolve_real_table(alias, schema)` inside
  `_detect_composite_opportunity`) — this one is a module-level function, not
  a method, so give it a new `table_aliases: dict[str, str] | None = None`
  parameter (mirroring its existing `schema` parameter) and have
  `recommend()` pass `table_aliases=table_aliases` at its call site (line
  ~243).
- line 427, 480, 512 (`self._ddl_hint(alias, col, db_type, schema)`) → add
  `table_aliases` as a trailing arg: `self._ddl_hint(alias, col, db_type,
  schema, table_aliases)`.
- line 564 (`real_table = self._real_table(alias, schema)` for the
  composite-suggestion loop) → `self._real_table(alias, schema,
  table_aliases)`.
- `_ddl_hint` / `_ddl_partial_hint` (~line 588, 604) → add `table_aliases:
  dict[str, str] | None = None` param, pass through to `self._real_table(alias,
  schema, table_aliases)`.

Note: `schema_verified` should stay tied to the schema_info path only
(`real_table is not None and col in schema.get(real_table, {})` — keep this
checking the *schema* dict specifically, not the new fallback) so a
table name resolved only via `table_aliases` is never mislabeled as
"schema-verified" in the UI — it's query-derived, not confirmed against an
actual column list.

## 4. Suggested tests to add

`backend/tests/test_query_parser.py` (or wherever existing parser tests live):

- `_clean_table_ref("[dbo].[Metropolitan$Sales Header] SH with(nolock)")` →
  `"[dbo].[Metropolitan$Sales Header]"` (not truncated at the first space).
- A multi-statement fixture (`DECLARE @t TABLE (id int); INSERT INTO @t
  SELECT id FROM foo GROUP BY id; SELECT * FROM bar`) — `_extract_group_by`
  on the first statement's query text should return exactly `["id"]`, not
  spill into `bar`.
- `_extract_table_aliases("... FROM [dbo].[Sales Header] SH WITH(NOLOCK)
  INNER JOIN [dbo].[Sales Linkup] SL WITH(NOLOCK) ON SH.No_ = SL.[Document
  No] ...")` → `{"SH": "[dbo].[Sales Header]", "SL": "[dbo].[Sales
  Linkup]"}`.
- End-to-end: run `index_recommender.py`'s `recommend()` on the real
  multi-table query from report `8f05a5fc-...` with `schema_info=None` and
  assert no suggestion's `ddl_hint` contains a literal `<` character.
