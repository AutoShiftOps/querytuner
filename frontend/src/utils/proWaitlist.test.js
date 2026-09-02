import { describe, it, expect } from 'vitest';
import { buildProRequestMailto } from './proWaitlist';

describe('buildProRequestMailto', () => {
  it('includes the fixed subject prefix for Gmail filtering', () => {
    const url = buildProRequestMailto({ email: 'a@b.com', userId: 'user_123' });
    expect(url).toContain('mailto:admin%40autoshiftops.com'.replace('%40', '@')); // recipient present
    expect(decodeURIComponent(url)).toContain('subject=[QueryTuner Pro Request] a@b.com');
  });

  it('falls back gracefully for signed-out visitors', () => {
    const url = buildProRequestMailto({});
    const decoded = decodeURIComponent(url);
    expect(decoded).toContain('[QueryTuner Pro Request] signed-out visitor');
    expect(decoded).toContain('(not signed in)');
  });
});
