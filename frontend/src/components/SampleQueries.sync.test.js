// @vitest-environment node
/**
 * The backend caches AI output only for the sample queries listed in
 * backend/app/data/sample_queries.json. If a sample is added or edited here
 * without updating that file, it silently stops being cached — this test
 * fails instead.
 */
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SAMPLE_QUERIES } from './SampleQueries';

const norm = (s) => s.trim().replace(/\s+/g, ' ');

describe('sample queries match the backend AI cache list', () => {
  it('every sample here is in backend/app/data/sample_queries.json, and nothing extra is there', () => {
    const file = fileURLToPath(
      new URL('../../../backend/app/data/sample_queries.json', import.meta.url)
    );
    const backend = JSON.parse(fs.readFileSync(file, 'utf8')).map(
      (q) => `${q.db_type}|${norm(q.sql)}`
    );
    const frontend = SAMPLE_QUERIES.flatMap((c) => c.queries).map((q) => `${q.db}|${norm(q.sql)}`);
    expect([...frontend].sort()).toEqual([...backend].sort());
  });
});
