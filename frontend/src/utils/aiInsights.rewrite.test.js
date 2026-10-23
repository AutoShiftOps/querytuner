import { describe, it, expect } from 'vitest';
import { getAiRewrittenQuery, normalizeSql } from './aiInsights';

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
