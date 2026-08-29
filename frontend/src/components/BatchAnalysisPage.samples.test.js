import { describe, expect, it } from 'vitest';
import { SOURCES } from './BatchAnalysisPage';

// Guards the "Load a sample" button (BatchAnalysisPage.jsx) against a
// typo silently breaking it — each sample must parse as valid JSON and
// use column names batch_parsers.py's own _first_present() actually
// recognizes for that source (backend/app/tools/batch_parsers.py), or a
// visitor clicking "Load a sample" then "Analyze batch" would hit the
// same "could not parse any queries" error real malformed input does.

const EXPECTED_QUERY_KEYS = {
  pg_stat_statements: ['query', 'query_text', 'sql', 'sql_text'],
  performance_schema: ['digest_text', 'sql_text', 'query', 'query_text'],
  query_store: ['query_sql_text', 'query_text', 'sql_text', 'query'],
};

describe('BatchAnalysisPage sample export data', () => {
  it.each(Object.keys(SOURCES))('%s sample parses as valid JSON', (source) => {
    expect(() => JSON.parse(SOURCES[source].sample)).not.toThrow();
  });

  it.each(Object.keys(SOURCES))('%s sample is a non-empty array of rows', (source) => {
    const rows = JSON.parse(SOURCES[source].sample);
    expect(Array.isArray(rows)).toBe(true);
    expect(rows.length).toBeGreaterThan(0);
  });

  it.each(Object.keys(SOURCES))(
    '%s sample rows use a query-text column the parser recognizes',
    (source) => {
      const rows = JSON.parse(SOURCES[source].sample);
      const acceptedKeys = EXPECTED_QUERY_KEYS[source];
      for (const row of rows) {
        const hasRecognizedKey = acceptedKeys.some((key) => key in row && String(row[key]).trim());
        expect(hasRecognizedKey).toBe(true);
      }
    }
  );
});
