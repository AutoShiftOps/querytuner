import { describe, it, expect } from 'vitest';
import {
  extractIdentifiers,
  buildSubstitutionMap,
  sanitize,
  desanitize,
  buildDiff,
} from './sanitizer';

const QUERY = `
  SELECT customer_id, balance
  FROM pinacle
  JOIN transactions ON pinacle.customer_id = transactions.customer_id
  WHERE balance > 100
`;

function mapFor(sql) {
  return buildSubstitutionMap(extractIdentifiers(sql));
}

describe('extractIdentifiers', () => {
  it('extracts table names after FROM/JOIN', () => {
    const names = extractIdentifiers(QUERY)
      .filter((i) => i.type === 'table')
      .map((i) => i.name.toLowerCase());
    expect(names).toContain('pinacle');
    expect(names).toContain('transactions');
  });

  it('extracts column names from SELECT/WHERE', () => {
    const names = extractIdentifiers(QUERY)
      .filter((i) => i.type === 'column')
      .map((i) => i.name.toLowerCase());
    expect(names).toContain('customer_id');
    expect(names).toContain('balance');
  });

  it('excludes single-letter aliases', () => {
    const sql = 'SELECT p.customer_id FROM pinacle p WHERE p.customer_id = 1';
    const names = extractIdentifiers(sql).map((i) => i.name.toLowerCase());
    expect(names).not.toContain('p');
  });

  it('excludes SQL keywords', () => {
    const sql =
      'SELECT customer_id FROM pinacle WHERE customer_id IS NOT NULL ORDER BY customer_id ASC';
    const names = extractIdentifiers(sql).map((i) => i.name.toUpperCase());
    for (const kw of ['SELECT', 'FROM', 'WHERE', 'IS', 'NOT', 'NULL', 'ORDER', 'BY', 'ASC']) {
      expect(names).not.toContain(kw);
    }
  });

  it('resolves schema-qualified names to the local segment only', () => {
    const names = extractIdentifiers('SELECT customer_id FROM public.pinacle').map((i) =>
      i.name.toLowerCase()
    );
    expect(names).toContain('pinacle');
    expect(names).not.toContain('public');
  });
});

describe('buildSubstitutionMap', () => {
  it('assigns deterministic, alphabetically-ordered table_x / col_x names', () => {
    const map = mapFor(QUERY);
    expect(map.pinacle).toBe('table_a');
    expect(map.transactions).toBe('table_b');
    expect(map.balance).toBe('col_a');
    expect(map.customer_id).toBe('col_b');
  });

  it('is stable across repeated calls for the same query', () => {
    expect(mapFor(QUERY)).toEqual(mapFor(QUERY));
  });
});

describe('sanitize', () => {
  it('replaces table and column names in the query', () => {
    const map = mapFor(QUERY);
    const sanitized = sanitize(QUERY, map);
    expect(sanitized).not.toMatch(/\bpinacle\b/i);
    expect(sanitized).not.toMatch(/\btransactions\b/i);
    expect(sanitized).toContain('table_a');
    expect(sanitized).toContain('table_b');
  });

  it('preserves schema prefixes while substituting the local name', () => {
    const map = { pinacle: 'table_a', transactions: 'table_b' };
    expect(sanitize('SELECT * FROM public.pinacle', map)).toBe('SELECT * FROM public.table_a');
    expect(sanitize('SELECT * FROM dbo.transactions', map)).toBe('SELECT * FROM dbo.table_b');
  });

  it('replaces "pinacle_id" (prefix match) when "pinacle" is in the map', () => {
    const map = { pinacle: 'table_a' };
    expect(sanitize('SELECT pinacle_id FROM x', map)).toBe('SELECT table_a_id FROM x');
  });

  it('does not replace "pinnacle" (a different word) when "pinacle" is in the map', () => {
    const map = { pinacle: 'table_a' };
    expect(sanitize('SELECT pinnacle_score FROM x', map)).toBe('SELECT pinnacle_score FROM x');
  });

  it('applies the same map to EXPLAIN plan text', () => {
    const map = { pinacle: 'table_a' };
    const plan = 'Seq Scan on pinacle  (cost=0.00..431.00 rows=10000 width=244)';
    expect(sanitize(plan, map)).toBe(
      'Seq Scan on table_a  (cost=0.00..431.00 rows=10000 width=244)'
    );
  });
});

describe('desanitize', () => {
  it('restores all original names from a sanitized string', () => {
    const map = mapFor(QUERY);
    const sanitized = sanitize(QUERY, map);
    const restored = desanitize(sanitized, map);
    expect(restored).toContain('pinacle');
    expect(restored).toContain('transactions');
    expect(restored).not.toMatch(/table_a|table_b/);
  });

  it('round-trips: sanitize -> desanitize === original', () => {
    const map = mapFor(QUERY);
    expect(desanitize(sanitize(QUERY, map), map)).toBe(QUERY);
  });
});

describe('buildDiff', () => {
  it('returns changed terms sorted by first occurrence in the query', () => {
    const map = mapFor(QUERY);
    const diff = buildDiff(QUERY, map);
    const order = diff.map((d) => d.original.toLowerCase());
    // "customer_id" (in SELECT) appears before "pinacle" (in FROM) in QUERY
    expect(order.indexOf('customer_id')).toBeLessThan(order.indexOf('pinacle'));
    expect(diff).toContainEqual({ original: 'pinacle', sanitized: 'table_a' });
  });
});
