import { describe, expect, it } from 'vitest';
import { isServiceUnavailable, UNAVAILABLE_MESSAGE } from './serviceStatus';

describe('isServiceUnavailable', () => {
  it('treats a missing response (network/CORS failure) as unavailable', () => {
    expect(isServiceUnavailable(new Error('Network Error'))).toBe(true);
  });

  it('treats gateway errors as unavailable', () => {
    for (const status of [502, 503, 504]) {
      expect(isServiceUnavailable({ response: { status } })).toBe(true);
    }
  });

  it('does not hide real API rejections', () => {
    for (const status of [400, 401, 403, 429, 500]) {
      expect(isServiceUnavailable({ response: { status } })).toBe(false);
    }
    expect(isServiceUnavailable(null)).toBe(false);
  });

  it('has a friendly message', () => {
    expect(UNAVAILABLE_MESSAGE).toMatch(/temporarily unavailable/i);
  });
});
