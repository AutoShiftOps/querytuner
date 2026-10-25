import { describe, it, expect } from 'vitest';
import {
  getAiFixCutOff,
  getAiRewriteRejected,
  getAiRewrittenQuery,
  getAiTargetedFixes,
  isAiRewriteTruncated,
  normalizeSql,
} from './aiInsights';

describe('getAiRewrittenQuery', () => {
  it('reads rewritten_query from a JSON string', () => {
    const c = JSON.stringify({ rewritten_query: ' SELECT 1; ' });
    expect(getAiRewrittenQuery(c)).toBe('SELECT 1;');
  });
  it('returns empty string for missing or unparseable content', () => {
    expect(getAiRewrittenQuery(null)).toBe('');
    expect(getAiRewrittenQuery('not json')).toBe('');
    expect(getAiRewrittenQuery(JSON.stringify({ other: 1 }))).toBe('');
  });
});

describe('normalizeSql', () => {
  it('ignores comments, whitespace, case and trailing semicolons', () => {
    expect(normalizeSql('SELECT a -- hi\nFROM t;')).toBe(normalizeSql('select a from t'));
  });
  it('detects real changes', () => {
    expect(normalizeSql('SELECT a FROM t')).not.toBe(normalizeSql('SELECT a FROM t LIMIT 10'));
  });
});

describe('isAiRewriteTruncated', () => {
  it('is false for a complete reply', () => {
    const c = JSON.stringify({ rewritten_query: 'SELECT 1', risky_assumptions: [] });
    expect(isAiRewriteTruncated(c)).toBe(false);
  });
  it('is true when the reply stops inside the rewritten query', () => {
    const c =
      '{"most_impactful_improvements": [{"type": "x"}], "rewritten_query": "SELECT ISNULL(CASE WHEN (';
    expect(isAiRewriteTruncated(c)).toBe(true);
  });
  it('is false when only a later field was cut off', () => {
    const c = '{"rewritten_query": "SELECT 1", "risky_assumptions": ["unknown card';
    expect(isAiRewriteTruncated(c)).toBe(false);
  });
  it('is false for empty or non-JSON content', () => {
    expect(isAiRewriteTruncated('')).toBe(false);
    expect(isAiRewriteTruncated('plain prose')).toBe(false);
  });
});

describe('targeted fixes and rejected rewrites', () => {
  it('reads targeted fixes and skips malformed entries', () => {
    const c = JSON.stringify({
      rewritten_query: '',
      targeted_fixes: [{ title: 't', before: 'a', after: 'b', why: 'w' }, { title: 'bad' }],
    });
    expect(getAiTargetedFixes(c)).toEqual([{ title: 't', before: 'a', after: 'b', why: 'w' }]);
    expect(getAiTargetedFixes('nope')).toEqual([]);
  });
  it('reads the rejection reason', () => {
    const c = JSON.stringify({ rewritten_query: '', rewrite_rejected: 'it drops table x' });
    expect(getAiRewriteRejected(c)).toBe('it drops table x');
    expect(getAiRewriteRejected(JSON.stringify({ rewritten_query: 'SELECT 1' }))).toBe('');
  });
});

describe('backend-repaired cut-off replies', () => {
  it('treats a backend-flagged cut-off rewrite as truncated', () => {
    const c = JSON.stringify({
      rewritten_query: '',
      rewrite_cut_off: true,
      output_truncated: true,
    });
    expect(isAiRewriteTruncated(c)).toBe(true);
    expect(getAiFixCutOff(c)).toBe(false);
  });
  it('reports a dropped unfinished fix', () => {
    const c = JSON.stringify({
      targeted_fixes: [{ before: 'a', after: 'b' }],
      output_truncated: true,
    });
    expect(getAiFixCutOff(c)).toBe(true);
    expect(isAiRewriteTruncated(c)).toBe(false);
  });
});
