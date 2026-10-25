// LLMs frequently wrap JSON in a markdown fence even when asked for raw JSON,
// and sometimes ignore the JSON instruction entirely and reply in prose —
// both are valid responses callers need to handle, not treat as errors.
//
// Mirrors backend/app/llm/json_utils.py's safe_parse_json: an anchored
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

// The AI's rewritten query as a plain string ('' when absent or unparseable).
// Mirrors ResultsPanel's key lookup so both read the same field.
const AI_REWRITE_KEYS = ['rewritten_query', 'optimized_query', 'rewrite'];
export function getAiRewrittenQuery(content) {
  const parsed = content && typeof content === 'object' ? content : safeParseAiJson(content);
  if (!parsed) return '';
  for (const key of AI_REWRITE_KEYS) {
    if (typeof parsed[key] === 'string') return parsed[key].trim();
  }
  return '';
}

// True when the AI reply was cut off (token limit) while it was still writing
// the rewritten query. safeParseAiJson recovers truncated JSON, so without
// this check a half-written rewrite would be shown as if it were complete.
export function isAiRewriteTruncated(content) {
  if (!content || typeof content !== 'string') return false;
  const clean = content.replace(/```(?:json)?/gi, '').trim();
  try {
    JSON.parse(clean);
    return false;
  } catch {
    // not strictly valid — check the brace-extracted slice next
  }
  const match = clean.match(/\{[\s\S]*\}/);
  if (match) {
    try {
      JSON.parse(match[0]);
      return false;
    } catch {
      // still invalid — the repair path was needed
    }
  }
  const parsed = safeParseAiJson(content);
  if (!parsed) return false;
  const rewriteKey = AI_REWRITE_KEYS.find((k) => typeof parsed[k] === 'string');
  const keys = Object.keys(parsed);
  return Boolean(rewriteKey) && keys[keys.length - 1] === rewriteKey;
}

// Before -> after snippets the AI proposed for a long query or batch. The
// backend already dropped any fix whose "before" text is not in the query.
export function getAiTargetedFixes(content) {
  const parsed = content && typeof content === 'object' ? content : safeParseAiJson(content);
  const fixes = Array.isArray(parsed?.targeted_fixes) ? parsed.targeted_fixes : [];
  return fixes
    .filter((f) => f && typeof f.before === 'string' && typeof f.after === 'string')
    .map((f) => ({
      title: String(f.title || '').trim(),
      before: f.before.trim(),
      after: f.after.trim(),
      why: String(f.why || '').trim(),
    }));
}

// Why the backend refused to pass on the AI's full rewrite ('' if it didn't).
export function getAiRewriteRejected(content) {
  const parsed = content && typeof content === 'object' ? content : safeParseAiJson(content);
  return typeof parsed?.rewrite_rejected === 'string' ? parsed.rewrite_rejected : '';
}

// SQL with comments/whitespace/case stripped, for "did the rewrite change
// anything?" comparisons.
export function normalizeSql(sql) {
  return String(sql || '')
    .replace(/--[^\n]*/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/[\s;]+/g, ' ')
    .trim()
    .toLowerCase();
}
