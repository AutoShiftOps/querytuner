# Two real bugs found live-testing on querytuner.com — Quiz Mode answer-leak + stale/no-default AI provider

**Context:** confirmed `27721727` (the docs sync for #153–#156) is on `master`, ROADMAP/CHANGELOG verified current. These two are new findings from live-testing the deployed site just now, not from a code audit — both confirmed against the actual source on `master` below. Neither is filed as a GitHub issue yet.

---

## Bug 1 — AI Insights panel leaks the quiz answer before reveal

**Symptom (screenshot):** Quiz Mode card shows one unanswered question ("What do you think is wrong with this query?"), and directly underneath it — still before answering or clicking "Show full analysis" — the AI Insights panel is already rendered in full, including the recommended index DDL that answers the question.

**Root cause, confirmed in `frontend/src/App.jsx`:** the quiz gate only wraps `OptimizationSuggestions` (line 531):
```js
{quizQuestions.length > 0 && !quizRevealed ? (
  <QuizMode questions={quizQuestions} onReveal={() => setQuizRevealed(true)} />
) : (
  <OptimizationSuggestions ... />
)}

{/* AI Insights — only show when AI was actually used and returned content */}
{result.used_ai && result.ai_insights && !result.ai_error && (
  <ResultsPanel title="AI Insights" content={result.ai_insights} ... />
)}
```
The `ResultsPanel` (AI Insights) condition has no reference to `quizQuestions`/`quizRevealed` at all — it renders unconditionally whenever `use_llm` was checked. This defeats Quiz Mode's entire premise ("test yourself before we reveal") any time a user has AI insights turned on, which is presumably a meaningful share of usage since it's the flagship feature.

**Fix:** gate the AI Insights block behind the same condition as `OptimizationSuggestions`:
```js
{(!quizQuestions.length || quizRevealed) && result.used_ai && result.ai_insights && !result.ai_error && (
  <ResultsPanel ... />
)}
```

**Test to add** (`frontend/src/**/*.test.jsx`, wherever `App.jsx`'s render logic is currently covered): analysis result with both quiz-eligible suggestions *and* `used_ai: true, ai_insights: "..."` → assert the AI Insights panel is absent while `quizRevealed` is false, and present after `onReveal` fires. Nothing in the current 45-test suite exercises quiz-mode + AI-insights together, which is why this shipped unnoticed.

---

## Bug 2 — AI provider dropdown gets stuck on a disabled "OpenAI (Pro only)" selection with no way back, and Pro users aren't defaulted to OpenAI at all

**Symptom (screenshot):** a signed-in account (avatar visible, so not anonymous) loads the analyzer with **"OpenAI (recommended) (Pro only)"** showing as the *selected* value in the AI Provider dropdown — despite `llmProvider` defaulting to `'huggingface'` in code (`App.jsx:49`) and OpenAI being disabled for this account.

**Root cause, confirmed in `frontend/src/App.jsx` and `QueryInput.jsx`:** `llmProvider` state has no effect anywhere that reconciles it against `openaiEnabled`. Two independent gaps:
1. **No reset:** if `llmProvider` was ever set to `'openai'` (e.g., selected before the `#53` Pro-gate shipped, or before this account's Pro status lapsed) it stays `'openai'` forever — the `<select>` then shows a disabled option as selected, with no way for the user to tell why or switch back via a sensible default. Confirmed no `useEffect` touches `llmProvider` based on `openaiEnabled` anywhere in either file.
2. **No smart default for actual Pro users either:** the flip side of the same gap — a genuinely Pro account still loads with `llmProvider = 'huggingface'` by default and has to manually switch to OpenAI every single analysis, even though it's marked "(recommended)" and they're already paying for it.

**Fix, in `QueryInput.jsx`** (has `isPro`/`openaiEnabled` already computed at line ~38):
```js
const didAutoSelectOpenAi = useRef(false);

// Reset: if the current selection is no longer allowed (Pro lapsed, or a
// stale selection from before the #53 Pro-gate), fall back to the always-
// available option rather than leaving a disabled value stuck as "selected".
useEffect(() => {
  if (llmProvider === 'openai' && !openaiEnabled) {
    setLlmProvider('huggingface');
  }
}, [openaiEnabled, llmProvider, setLlmProvider]);

// Default confirmed Pro users to the recommended provider once, without
// overriding a deliberate manual choice made afterward.
useEffect(() => {
  if (openaiEnabled && llmProvider === 'huggingface' && !didAutoSelectOpenAi.current) {
    didAutoSelectOpenAi.current = true;
    setLlmProvider('openai');
  }
}, [openaiEnabled]);
```
(`useEffect`/`useRef` need importing into `QueryInput.jsx` — currently only imports `useState`.)

This also answers the funnel question raised alongside these bugs: **no change needed to the default for anonymous/free visitors** — `llmProvider` already starts on `'huggingface'`, and showing OpenAI visibly-but-disabled with "(Pro only)" is a reasonable soft upsell rather than something to hide. The actual gap was only on the Pro side (no auto-default) and the stale-selection side (no reset) — both closed by the effects above.

**Test to add:** (a) render with `isPro: false` after previously being `isPro: true` (or a stale `openai` selection) → dropdown falls back to Hugging Face, not stuck disabled-selected. (b) render with `isPro: true` fresh → dropdown auto-selects OpenAI without user interaction. (c) render with `isPro: true`, user manually re-selects Hugging Face → later re-renders don't fight that choice back to OpenAI.

---

## Also noticed while re-reading ROADMAP.md post-sync (minor, your call)

`#116` now appears as a full row in **both** the new Phase 4 table and the pre-existing Phase 5 table — the Phase 4 audit doc pulled it in only because `#124`'s issue text references it, not because it's actually a monetization issue; it's always been a Phase 5 (report-sharing) item. Recommend dropping the Phase 4 table's `#116` row (keep the "References `#116`" line already in the `#124` row instead) and leaving the Phase 5 row as the single source of truth — but this is cosmetic, not a correctness issue, so only worth doing next time either file gets touched anyway.
