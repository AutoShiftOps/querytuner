// LLMs frequently wrap JSON in a markdown fence even when asked for raw JSON,
// and sometimes ignore the JSON instruction entirely and reply in prose —
// both are valid responses callers need to handle, not treat as errors.
//
// Mirrors backend/app/llm/hf_client.py's safe_parse_json: an anchored
// ^```...```$ match misses the common case of the model adding a stray
// sentence before/after the fenced block (or the fence not being at the
// very start/end after trimming), which used to fall through to the plain
// text renderer and show raw JSON braces. Stripping fence markers globally
// and falling back to a greedy {...} extraction handles both cases.
export function safeParseAiJson(content) {
  if (!content || typeof content !== 'string') return null;

  const clean = content.replace(/```(?:json)?/gi, '').trim();

  try {
    const parsed = JSON.parse(clean);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    // fall through to brace extraction below
  }

  const match = clean.match(/\{[\s\S]*\}/);
  if (match) {
    try {
      const parsed = JSON.parse(match[0]);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch {
      return null;
    }
  }

  return null;
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
