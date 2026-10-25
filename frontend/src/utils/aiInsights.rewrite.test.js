import { describe, it, expect } from 'vitest';
import { getAiRewrittenQuery, isAiRewriteTruncated, normalizeSql } from './aiInsights';

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
    const c = '{"most_impactful_improvements": [{"type": "x"}], "rewritten_query": "SELECT ISNULL(CASE WHEN (';
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
