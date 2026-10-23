# Frontend fixes: silent-empty AI Insights section, misleading "Optimized Query" label

Fixes bugs #4 and #5 from the QA findings doc (report ID
`8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e`).

---

## Tracking — create these two GitHub Issues first

**Issue C — title:** `"Most Impactful Improvements" silently disappears when every item is already AI-confirmed`

```
ResultsPanel.jsx's StructuredInsights() dedupes the AI's
most_impactful_improvements against already-badged heuristic findings
("✓ CONFIRMED BY AI"). When every AI-returned item overlaps a heuristic
finding (which is exactly what happened on report
8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e — several findings carry that badge),
`improvements` filters down to [] and the whole section renders nothing,
with no fallback copy. Combined with a PDF export page-break landing mid-
card, this makes a working AI Insights panel look completely broken.

Fix: when the AI call succeeded but post-dedup `improvements`/`risky` are
both empty, show explicit copy instead of silently rendering nothing.
```

**Issue D — title:** `"Optimized Query" label is misleading — it's a comment-annotated copy of the original, not a rewrite`

```
backend/app/agents/optimizer.py's QueryRewriter only inserts /* TODO */
comments and inline annotations via regex substitution (SELECT * stays
SELECT *, leading-wildcard LIKE stays as-is, etc.) — it never actually
restructures the query. Rendered under the "Optimized Query" label with a
"✓ optimized" badge, right next to the AI's genuinely-rewritten CTE-based
"Rewritten Query" section, this reads as contradictory and undersells both
the honest deterministic annotator and the real AI rewrite.

Fix: relabel to make clear this is annotation, not optimization.
```

---

## 1. `frontend/src/components/ResultsPanel.jsx` — explicit empty-state copy (bug #4)

In `StructuredInsights()`, after the existing `indexes`/`rewritten`/`risky`
derivations:

```diff
   const riskyRaw = findKey(data, RISKY_ASSUMPTIONS_KEYS);
   const risky = Array.isArray(riskyRaw) ? riskyRaw : [];
+
+  // Issue: when every AI-returned improvement/risk item already matches a
+  // heuristic finding shown above (dedup via aiConfirmedTypes), both
+  // sections below render nothing — which looks identical to the AI call
+  // having failed, even though it succeeded and genuinely had nothing new
+  // to add. Show that explicitly instead of a silent gap.
+  const hadAiImprovements = allImprovements.length > 0;
+  const dedupedAllAway = hadAiImprovements && improvements.length === 0;
```

Then wrap the "Most Impactful Improvements" block with an explicit
else-branch:

```diff
-      {improvements.length > 0 && (
+      {improvements.length > 0 ? (
         <div>
           <SectionTitle>
             Most Impactful Improvements
             <span
               style={{
                 textTransform: 'none',
                 fontWeight: 400,
                 letterSpacing: 'normal',
                 color: '#4a6480',
               }}
             >
               (complements heuristic findings above)
             </span>
           </SectionTitle>
           {improvements.map((item, idx) => (
             <SuggestionCard key={idx} item={item} />
           ))}
         </div>
+      ) : (
+        dedupedAllAway && (
+          <p style={{ fontSize: 13, color: '#7fa3c4', margin: 0 }}>
+            AI analysis confirmed the heuristic findings above — no
+            additional improvements identified.
+          </p>
+        )
       )}
```

This only renders the new message when the AI genuinely returned
improvements that all got deduped away (`dedupedAllAway`), not when the AI
returned nothing at all (that's a separate, already-distinct state —
`hasStructuredContent` would be false and `PlainTextInsights`/an error state
handles it instead).

## 2. `frontend/src/components/ReportPage.jsx` — relabel "Optimized Query" (bug #5)

```diff
         {/* ── Optimized query ── */}
         {report.optimized_query && (
           <div className="qt-section">
-            <div className="qt-section-label">Optimized Query</div>
+            <div className="qt-section-label">Annotated Query</div>
             <div className="qt-card">
               <div className="qt-code-header">
-                <span className="qt-code-lang">sql · rewritten</span>
+                <span className="qt-code-lang">sql · annotated</span>
                 <span
                   style={{
                     fontSize: 10,
                     color: T.green,
                     fontFamily: "'JetBrains Mono', monospace",
                     fontWeight: 500,
                   }}
                 >
-                  ✓ optimized
+                  inline hints only
                 </span>
               </div>
+              <p
+                style={{
+                  fontSize: 11,
+                  color: '#7fa3c4',
+                  margin: '0 0 8px',
+                }}
+              >
+                Deterministic, safe edits only — flags issues inline as
+                comments rather than restructuring the query. For an actual
+                AI-suggested rewrite, see Rewritten Query in AI Insights
+                above.
+              </p>
               <pre className="qt-code qt-code-optimized">{report.optimized_query}</pre>
             </div>
           </div>
         )}
```

(`T.green` import/usage is unchanged — only the badge text changes, not its
color, so no other styling touch-ups needed.)

Also check `frontend/src/components/ResultsPanel.jsx` line 25
(`REWRITTEN_QUERY_KEYS = ['rewritten_query', 'optimized_query', 'rewrite']`)
— leave this as-is. It's matching keys in the *AI's own JSON response*
(a different, unrelated field from `report.optimized_query`), and the AI
prompt only ever asks for `rewritten_query`, so `'optimized_query'` there is
just defensive key-matching, not part of this bug.

## 3. Suggested tests to add

`frontend/src/components/ResultsPanel.test.jsx` (or wherever existing tests
for this component live):

- Render `ResultsPanel` with AI content where `most_impactful_improvements`
  has one item whose `type` is in `aiConfirmedTypes` (so it fully dedupes
  away) and `risky_assumptions` is `[]` — assert the "no additional
  improvements identified" copy renders, and the section doesn't just
  vanish.
- Render with AI content where `most_impactful_improvements` is `[]` from
  the start (AI genuinely found nothing, not a dedup situation) — assert no
  confusing "confirmed" message appears (since there's nothing to have
  confirmed).
- Render `ReportPage` with a `report.optimized_query` present — assert the
  "Annotated Query" label and new explanatory note both appear, and the old
  "✓ optimized" text no longer does.
