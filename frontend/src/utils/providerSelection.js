/**
 * QueryInput.jsx's AI-provider dropdown reconciliation —
 * docs/querytuner-quiz-provider-fixes.md, Bug 2.
 *
 * Resets a provider selection that is no longer allowed (OpenAI after Pro
 * lapses, Claude when the server has no key) so the dropdown never sits on a
 * disabled option. Pure predicates so they are unit-testable without
 * mounting the component.
 */

/** True when an "openai" selection is no longer allowed (Pro lapsed). */
export function shouldResetStaleOpenAiSelection(llmProvider, openaiEnabled) {
  return llmProvider === 'openai' && !openaiEnabled;
}

/** Same reset rule for the Anthropic (Claude) option, when the server has no key. */
export function shouldResetStaleAnthropicSelection(llmProvider, anthropicEnabled) {
  return llmProvider === 'anthropic' && !anthropicEnabled;
}
