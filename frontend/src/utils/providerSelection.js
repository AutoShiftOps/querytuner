/**
 * QueryInput.jsx's AI-provider dropdown reconciliation —
 * docs/querytuner-quiz-provider-fixes.md, Bug 2.
 *
 * Before this, nothing reconciled `llmProvider` against `openaiEnabled`:
 * a stale "openai" selection (made before the #53 Pro-gate shipped, or
 * after Pro status lapsed) stayed selected forever, showing a disabled
 * option as the dropdown's current value with no way back — and a
 * genuinely Pro account still defaulted to "huggingface" and had to
 * manually switch every single analysis despite OpenAI being the
 * recommended, already-paid-for option.
 *
 * These two pure predicates are QueryInput.jsx's actual decision logic,
 * extracted so it's unit-testable — this project has no
 * component-mounting test setup, same reason utils/quiz.js's
 * generateQuiz/pickDistractors are tested directly instead of via a
 * rendered component. QueryInput.jsx calls these from two separate
 * useEffects (kept separate, not merged into one, so each keeps its own
 * narrow dependency list — the reset reacts to llmProvider changes, the
 * auto-select deliberately only reacts to openaiEnabled turning on).
 */

/** True when the current selection is no longer allowed and must fall
 * back to the always-available option (Pro lapsed, or a stale
 * pre-Pro-gate selection). */
export function shouldResetStaleOpenAiSelection(llmProvider, openaiEnabled) {
  return llmProvider === 'openai' && !openaiEnabled;
}

/** True exactly once per Pro session: openaiEnabled just became available,
 * the dropdown is still on the default, and this hasn't already fired —
 * `alreadyAutoSelected` is the caller's latch (a useRef in QueryInput.jsx)
 * that prevents fighting a deliberate manual switch back to Hugging Face
 * made after the auto-select already happened. */
export function shouldAutoSelectOpenAiForPro(llmProvider, openaiEnabled, alreadyAutoSelected) {
  return openaiEnabled && llmProvider === 'huggingface' && !alreadyAutoSelected;
}
