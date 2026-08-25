/**
 * Quiz Mode — docs/querytuner-quiz-mode-issue.md.
 *
 * Deterministic (non-LLM), pure-frontend transform over an analysis
 * result's own `optimization_suggestions` — no new endpoint, no new
 * schema field. Turns a subset of a query's own real findings into
 * multiple-choice "what's wrong with this query?" questions, revealed as
 * the answer key after the user picks.
 *
 * The load-bearing design constraint (see the doc): a quiz answer key
 * must never come from a suggestion whose evidence_level is
 * "needs-runtime-evidence" — that tier exists because QueryTuner itself
 * isn't certain about the finding. Quizzing a user against a guess the
 * product is only estimating would repeat the exact false-confidence
 * risk #63's cross-referencing was built to prevent, just relocated into
 * a new feature instead of fixed. See generateQuiz's filter below.
 */

import { typeLabel } from '../components/OptimizationSuggestions';

// Mirrors the severity each type is actually assigned in
// backend/app/agents/sql_analyzer.py and backend/app/tools/index_recommender.py
// (index_review_* severities read from their _make() call sites; the two
// plan-native types from _PLAN_NATIVE_SUGGESTION_COPY). This is a
// representative default per TYPE, not a specific finding's actual
// severity (some backend types can vary that per occurrence) — used only
// to pick "similar severity" distractors so a wrong answer isn't
// guessable by tone alone (doc item 2).
export const TYPE_SEVERITY = {
  column_selection: 'medium',
  full_scan_risk: 'medium',
  like_wildcard: 'high',
  function_in_where: 'high',
  order_by_no_limit: 'medium',
  join_complexity: 'high',
  cartesian_join: 'critical',
  subquery_refactor: 'medium',
  implicit_cast: 'high',
  subquery_to_join: 'high',
  high_complexity: 'medium',
  security_best_practice: 'medium',
  not_in_nullable: 'high',
  case_in_predicate: 'high',
  or_expansion: 'medium',
  cte_multiple_references: 'medium',
  index_review_join_key: 'high',
  index_review_where_filter: 'high',
  index_review_order_by_index: 'medium',
  index_review_group_by_index: 'medium',
  index_review_partial_index_candidate: 'medium',
  index_review_composite_index: 'high',
  filesort_detected: 'high',
  temp_table_detected: 'high',
};

const ALL_TYPES = Object.keys(TYPE_SEVERITY);

// Doc item 4 ("Not quizzing on every suggestion returned") and item 2
// ("pick up to 2-3").
export const MAX_QUESTIONS = 3;
const DISTRACTOR_COUNT = 3;

function shuffle(items) {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/**
 * Picks up to `count` distractor types for `correctType` — never a type
 * actually present in this query's own results (that would be a second
 * correct answer, not a wrong one), preferring types sharing the correct
 * answer's representative severity before falling back to any other
 * unused type.
 */
export function pickDistractors(correctType, excludeTypes, count = DISTRACTOR_COUNT) {
  const correctSeverity = TYPE_SEVERITY[correctType];
  const pool = ALL_TYPES.filter((t) => t !== correctType && !excludeTypes.has(t));

  const sameSeverity = shuffle(pool.filter((t) => TYPE_SEVERITY[t] === correctSeverity));
  const otherSeverity = shuffle(pool.filter((t) => TYPE_SEVERITY[t] !== correctSeverity));

  return [...sameSeverity, ...otherSeverity].slice(0, count);
}

/**
 * Builds up to MAX_QUESTIONS multiple-choice questions from a real
 * analysis's suggestions. Returns [] when nothing in the result is
 * confident enough to quiz on — callers should treat that as "skip
 * Quiz Mode entirely," not an error.
 */
export function generateQuiz(suggestions) {
  const list = Array.isArray(suggestions) ? suggestions : [];

  // The confidence guard — see module docstring.
  const eligible = list.filter(
    (s) => s && s.type && s.evidence_level && s.evidence_level !== 'needs-runtime-evidence'
  );
  if (eligible.length === 0) return [];

  // One question per distinct type — suggestions are already deduped by
  // (type, suggestion text) upstream (SQLAnalyzerAgent._dedupe_suggestions),
  // but a quiz with the same type asked twice would just be redundant, so
  // guard here too rather than assume.
  const seenTypes = new Set();
  const candidates = [];
  for (const s of eligible) {
    if (seenTypes.has(s.type)) continue;
    seenTypes.add(s.type);
    candidates.push(s);
  }

  // Every type this query actually triggered (not just the eligible/
  // chosen ones) is off-limits as a distractor — a distractor that's
  // secretly also true of this query isn't a wrong answer.
  const presentTypes = new Set(list.map((s) => s.type));

  const chosen = shuffle(candidates).slice(0, MAX_QUESTIONS);

  return chosen.map((suggestion, idx) => {
    const distractorTypes = pickDistractors(suggestion.type, presentTypes);
    const options = shuffle([
      { text: typeLabel(suggestion.type), isCorrect: true },
      ...distractorTypes.map((t) => ({ text: typeLabel(t), isCorrect: false })),
    ]);

    return {
      id: `${suggestion.type}-${idx}`,
      prompt: 'What do you think is wrong with this query?',
      options,
      correctType: suggestion.type,
      severity: suggestion.severity,
      // Revealed as the answer key regardless of right/wrong — the real
      // reason QueryTuner already computed for this query, not stock copy.
      reason: suggestion.reason || suggestion.suggestion,
    };
  });
}
