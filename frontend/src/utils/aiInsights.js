// LLMs frequently wrap JSON in a markdown fence even when asked for raw JSON,
// and sometimes ignore the JSON instruction entirely and reply in prose —
// both are valid responses callers need to handle, not treat as errors.
export function safeParseAiJson(content) {
  if (!content || typeof content !== 'string') return null;
  let text = content.trim();
  const fenceMatch = text.match(/^```(?:json)?\s*\n?([\s\S]*?)\n?```$/);
  if (fenceMatch) text = fenceMatch[1].trim();
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

// Types that appear in both the heuristic suggestions and the AI's
// most_impactful_improvements — these get a "confirmed by AI" badge on the
// heuristic card instead of being shown again in the AI panel.
export function getAiConfirmedTypes(heuristicSuggestions, aiInsightsContent) {
  const heuristicTypes = new Set(
    (Array.isArray(heuristicSuggestions) ? heuristicSuggestions : [])
      .map((s) => s?.type)
      .filter(Boolean)
  );
  const parsed = safeParseAiJson(aiInsightsContent);
  const improvements = Array.isArray(parsed?.most_impactful_improvements)
    ? parsed.most_impactful_improvements
    : [];

  return new Set(improvements.map((i) => i?.type).filter((t) => t && heuristicTypes.has(t)));
}
