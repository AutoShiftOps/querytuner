# Phase 5/6 — Quiz Mode: test-yourself questions from a real analyzed query

**Status:** Proposed — new idea, not yet on ROADMAP.md, no GitHub issue filed yet.
**Depends on:** Nothing new to build first — reuses the existing `OptimizationSuggestion` shape and `evidence_level` system already shipped.
**Goal:** Before revealing the analysis, ask the user 2–3 interview-style questions generated from findings QueryTuner already computed for their own query — then reveal the real findings as the answer key.

## Why this shape, not a static question bank

The prompting idea (a blog post of generic SQL interview questions) is a content-marketing pattern: someone writes and maintains a growing bank of stock questions, unrelated to what any given visitor is actually working on. That's a real ongoing editorial commitment, and it doesn't differentiate from the blog post it's imitating — a visitor can already read that for free.

What QueryTuner already has that a blog can't: every analysis produces real, structured findings *about the specific query the user pasted* — not stock content. Turning "paste your query" into "paste your query, then tell us what you think is wrong with it before we show you" makes the required first step of using the product into a moment that demonstrates expertise, rather than adding a disconnected new section. This is also a genuinely defensible feature for the acquirer-facing story this session has been keeping honest — "we test whether you'd have caught it" is a real product claim, not marketing copy, as long as the questions come from real findings (see the confidence guard below).

## What exists today (confirmed by reading the repo)

- `OptimizationSuggestion` (`schemas/models.py:55`) already has everything a question needs: `suggestion` (the finding, could be the "correct answer" text), `reason` (the explanation to reveal), `severity`, `evidence_level`.
- **24 distinct suggestion types already exist** across `sql_analyzer.py` (16 heuristic types: `cartesian_join`, `case_in_predicate`, `column_selection`, `cte_multiple_references`, `full_scan_risk`, `function_in_where`, `high_complexity`, `implicit_cast`, `join_complexity`, `like_wildcard`, `not_in_nullable`, `or_expansion`, `order_by_no_limit`, `security_best_practice`, `subquery_refactor`, `subquery_to_join`) and `index_recommender.py` (6 `index_review_*` types, prefixed at `index_recommender.py:644`) plus the two new plan-native types from this session's EXPLAIN gap-closure (`filesort_detected`, `temp_table_detected`) — plenty of variety to draw multiple-choice distractors from types *not* present in the current query.
- `evidence_level` already has the exact tiering a quiz needs to avoid a wrong "correct answer": `"deterministic"`, `"schema-verified"`, `"needs-runtime-evidence"`. **This is the load-bearing design constraint**: a quiz question's answer key must never come from a `"needs-runtime-evidence"` suggestion — that tier exists precisely because QueryTuner itself isn't certain about it. Quizzing a user against an answer the product itself is only guessing at would be worse than not having the feature (repeats exactly the false-confidence risk `#63`'s design doc was written to prevent, just relocated into a new feature instead of fixed).
- `App.jsx` (`~line 504`) renders `OptimizationSuggestions` immediately and fully after `handleAnalyze()` resolves — there's no existing "reveal" gate or staged-disclosure UI anywhere in the current flow to build on; this is genuinely new frontend state, not an extension of something already staged.
- `isPro` is already threaded through `App.jsx`'s state and passed to child components — the existing pattern for gating a feature behind Pro (same as the "Use AI insights" checkbox being gated on `isSignedIn`).
- `ReportPage.jsx` (the shareable `/report/:id` view) is a distinct, already-shipped read-only surface for a link recipient who didn't run the analysis themselves — a quiz doesn't fit there naturally (they didn't write or paste the query, so "test yourself before we reveal" doesn't make sense for a viewer, only for the person who ran it). Scope this to the live analyzer flow (`App.jsx`) only.

## Proposed scope

1. **Backend: nothing new required for v1** — this can be a pure frontend transform over `result.optimization_suggestions`, the response the API already returns in full. No new endpoint, no new schema field.
2. **Question generation (frontend, deterministic)**: from the suggestions actually returned for this query, filter to `evidence_level !== "needs-runtime-evidence"` (per the confidence guard above), pick up to 2–3, and for each build a multiple-choice question: the `suggestion` text (or a paraphrase of it) as the correct answer, plus 3 distractors — other suggestion *types'* human-readable labels that are NOT present in this query's results (pull from the 24-type taxonomy above, filtered to plausible-sounding wrong answers of similar severity so it's not trivially guessable by tone alone).
3. **UI flow**: after `handleAnalyze()` returns a result with suggestions, show the quiz *before* `OptimizationSuggestions` renders — a "What do you think is wrong with this query?" card per selected finding, multiple choice, immediate right/wrong feedback with the real `reason` text shown either way, then a "Show full analysis" action that reveals the existing `OptimizationSuggestions` panel underneath (which already has everything, including the findings the quiz just asked about). Don't block access to the real analysis behind answering — this is meant to be an engagement layer, not friction; someone in a hurry should be able to skip straight through.
4. **Skip path**: a visible "Skip quiz, show me the analysis" control from the first render — respect that a lot of real usage is "I need this answer now," not "I want to be tested."
5. **Gating**: recommend this as a **free-tier feature**, not Pro-gated — unlike query history or PDF export, this isn't withholding analysis output, it's an engagement layer on output every tier already gets; gating it would blunt its own purpose (getting more people to actually engage with findings, including the free users you're trying to convert). Revisit this call if adoption data later suggests otherwise.
6. **No new LLM calls for v1** — question/distractor generation is templated from existing data, matching how this codebase already separates deterministic logic from optional LLM-additive content (`used_ai`/`ai_insights` stay a separate, optional layer). An LLM-generated distractor pool is a plausible v2 enhancement, not needed to ship v1.

## Explicit non-goals for v1

- Not building on `ReportPage.jsx` — live analyzer flow only, per the reasoning above.
- Not persisting quiz results anywhere (no score history, no leaderboard) — this is a single-session engagement moment, not a new data model. If it proves popular, a "your quiz accuracy" stat tied to `#54`'s query history is a reasonable v2, not v1.
- Not LLM-generating questions or distractors in v1 — templated from existing structured data only, for the same reason the rest of this session has favored deterministic-first: an LLM-authored quiz question could itself be wrong in a way nothing catches.
- Not quizzing on every suggestion returned — cap at 2–3 per analysis; a query with 8 findings shouldn't turn into an 8-question test before someone can see their results.
- Not attempting difficulty tiers or adaptive question selection — pick from whatever high-confidence findings exist for this query; no scoring system to calibrate against yet.

## Suggested sequencing

Small enough to build as one piece rather than a chain — no dependency chain like the EXPLAIN parser issues had. The confidence-tier filter (item 2 above) is the one part worth the most test care, for the same reason `#63`'s cross-referencing was: a quiz "correct answer" that's actually wrong is worse than no quiz at all.
