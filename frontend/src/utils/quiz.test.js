import { afterEach, describe, expect, it, vi } from 'vitest';
import { generateQuiz, pickDistractors, TYPE_SEVERITY, MAX_QUESTIONS } from './quiz';
import { TYPE_LABELS, typeLabel } from '../components/OptimizationSuggestions';

function suggestion(type, evidenceLevel = 'schema-verified', overrides = {}) {
  return {
    type,
    severity: TYPE_SEVERITY[type] || 'medium',
    suggestion: `${type} suggestion text`,
    reason: `${type} reason text`,
    estimated_improvement: '...',
    evidence_level: evidenceLevel,
    ...overrides,
  };
}

describe('generateQuiz — the confidence-tier filter (highest test priority per the doc)', () => {
  it('never builds a question from a needs-runtime-evidence suggestion', () => {
    const suggestions = [
      suggestion('or_expansion', 'needs-runtime-evidence'),
      suggestion('cte_multiple_references', 'needs-runtime-evidence'),
    ];

    expect(generateQuiz(suggestions)).toEqual([]);
  });

  it('only questions eligible (non-needs-runtime-evidence) suggestions, even when mixed', () => {
    const suggestions = [
      suggestion('cartesian_join', 'deterministic'),
      suggestion('or_expansion', 'needs-runtime-evidence'),
      suggestion('index_review_where_filter', 'schema-verified'),
    ];

    const quiz = generateQuiz(suggestions);
    const questionedTypes = quiz.map((q) => q.correctType);

    expect(questionedTypes).not.toContain('or_expansion');
    expect(
      questionedTypes.every((t) => ['cartesian_join', 'index_review_where_filter'].includes(t))
    ).toBe(true);
  });

  it('every question option set contains exactly one correct answer', () => {
    const suggestions = [
      suggestion('cartesian_join'),
      suggestion('function_in_where'),
      suggestion('index_review_where_filter'),
    ];

    const quiz = generateQuiz(suggestions);
    for (const q of quiz) {
      const correctCount = q.options.filter((o) => o.isCorrect).length;
      expect(correctCount).toBe(1);
      expect(q.options.find((o) => o.isCorrect).text).toBe(typeLabel(q.correctType));
    }
  });

  it('the reason shown as the answer key is the real, per-query reason text', () => {
    const suggestions = [
      suggestion('cartesian_join', 'deterministic', { reason: 'Specific to this query' }),
    ];

    const quiz = generateQuiz(suggestions);
    expect(quiz[0].reason).toBe('Specific to this query');
  });
});

describe('generateQuiz — question count and dedup', () => {
  it('returns [] for an empty or missing suggestions list', () => {
    expect(generateQuiz([])).toEqual([]);
    expect(generateQuiz(undefined)).toEqual([]);
    expect(generateQuiz(null)).toEqual([]);
  });

  it('caps at MAX_QUESTIONS even when more eligible findings exist', () => {
    const suggestions = [
      suggestion('cartesian_join'),
      suggestion('like_wildcard'),
      suggestion('function_in_where'),
      suggestion('implicit_cast'),
      suggestion('not_in_nullable'),
    ];

    expect(generateQuiz(suggestions).length).toBe(MAX_QUESTIONS);
  });

  it('never asks about the same type twice', () => {
    // Same type, e.g. two index_review_where_filter suggestions for two
    // different columns — shouldn't happen post-backend-dedup, but the
    // generator doesn't assume that.
    const suggestions = [
      suggestion('index_review_where_filter'),
      suggestion('index_review_where_filter', 'schema-verified', { columns: ['other_col'] }),
    ];

    const quiz = generateQuiz(suggestions);
    expect(quiz.length).toBe(1);
  });
});

describe('generateQuiz — distractors never repeat a type present in the query', () => {
  it('excludes every type actually returned for this query, not just questioned ones', () => {
    const suggestions = [
      suggestion('cartesian_join'),
      suggestion('like_wildcard'), // present, but not chosen as a question necessarily
      suggestion('function_in_where'),
      suggestion('implicit_cast'),
    ];
    const presentTypes = new Set(suggestions.map((s) => s.type));

    const quiz = generateQuiz(suggestions);
    for (const q of quiz) {
      for (const opt of q.options) {
        if (opt.isCorrect) continue;
        const distractorType = Object.keys(TYPE_LABELS).find((t) => typeLabel(t) === opt.text);
        if (distractorType) {
          expect(presentTypes.has(distractorType)).toBe(false);
        }
      }
    }
  });

  it('produces 4 options per question (1 correct + 3 distractors) when enough types exist', () => {
    const suggestions = [suggestion('cartesian_join')];
    const quiz = generateQuiz(suggestions);
    expect(quiz[0].options.length).toBe(4);
  });
});

describe('pickDistractors', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('never returns the correct type itself or an excluded type', () => {
    const excluded = new Set(['cartesian_join', 'like_wildcard']);
    const distractors = pickDistractors('cartesian_join', excluded, 5);

    expect(distractors).not.toContain('cartesian_join');
    expect(distractors).not.toContain('like_wildcard');
  });

  it('prefers same-severity types before falling back to other severities', () => {
    // Force shuffle to be a no-op (identity) so ordering is deterministic
    // for this assertion — real usage doesn't care about order, only that
    // same-severity distractors are exhausted first.
    vi.spyOn(Math, 'random').mockReturnValue(0);

    // cartesian_join is the only "critical" type — its same-severity pool
    // is empty, so every distractor must come from the "other severity"
    // fallback. Assert none of them accidentally equal a "critical" type
    // (there are none besides itself, so this mostly documents intent),
    // and that the full requested count is still returned from the pool.
    const distractors = pickDistractors('cartesian_join', new Set(), 3);
    expect(distractors.length).toBe(3);
    expect(distractors.every((t) => TYPE_SEVERITY[t] !== 'critical')).toBe(true);
  });

  it('same-severity distractors come before other-severity ones when both exist', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);

    // "high" has several types (like_wildcard, function_in_where, ...) —
    // with shuffle neutralized, the same-severity slice should fill
    // before any "medium"/other type appears.
    const distractors = pickDistractors('like_wildcard', new Set(), 3);
    expect(distractors.every((t) => TYPE_SEVERITY[t] === 'high')).toBe(true);
  });
});
