import { describe, it, expect } from 'vitest';
import { desanitize } from './sanitizer';

describe('rollback DDL desanitize', () => {
  it('restores original names inside index names', () => {
    const map = { category: 'col_b' };
    expect(desanitize('DROP INDEX CONCURRENTLY idx_p_col_b;', map)).toBe(
      'DROP INDEX CONCURRENTLY idx_p_category;'
    );
  });
});
