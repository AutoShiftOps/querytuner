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
// Closes an unterminated string and any still-open arrays/objects so JSON
// that was cut off mid-generation (e.g. the LLM response hit its token
// limit before finishing) can still parse — recovering whatever fields did
// finish generating instead of showing raw JSON text. Never invents data,
// only closes what the model had already opened; a trailing dangling comma
// (the common shape: `"key": [\n  "item",` with nothing after) is stripped
// so the appended closers produce valid JSON rather than a trailing-comma
// syntax error.
function repairTruncatedJson(text) {
  const stack = [];
  let inString = false;
  let escaped = false;

  for (const ch of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '{' || ch === '[') stack.push(ch);
    else if (ch === '}' || ch === ']') stack.pop();
  }

  let repaired = text;
  if (inString) repaired += '"';
  repaired = repaired.replace(/,\s*$/, '');
  for (let i = stack.length - 1; i >= 0; i--) {
    repaired += stack[i] === '{' ? '}' : ']';
  }
  return repaired;
}

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
      // fall through to truncation repair below — this slice may itself be
      // the truncated content (no closing brace exists yet, so the greedy
      // match grabbed everything from the first `{` to end of string).
    }
  }

  // No match above means there's no closing `}` anywhere — the response
  // was cut off mid-generation. Try to recover the fields that did finish.
  const openIdx = clean.indexOf('{');
  if (openIdx !== -1) {
    try {
      const parsed = JSON.parse(repairTruncatedJson(clean.slice(openIdx)));
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
