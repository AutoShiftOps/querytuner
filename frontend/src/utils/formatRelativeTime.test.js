import { describe, expect, it } from 'vitest';
import { formatRelativeTime } from './formatRelativeTime';

describe('formatRelativeTime', () => {
  const now = new Date('2026-08-20T12:00:00.000Z');

  it('returns — for missing or invalid input', () => {
    expect(formatRelativeTime(null, now)).toBe('—');
    expect(formatRelativeTime(undefined, now)).toBe('—');
    expect(formatRelativeTime('not-a-date', now)).toBe('—');
  });

  it('handles seconds', () => {
    expect(formatRelativeTime(new Date('2026-08-20T11:59:58.000Z').toISOString(), now)).toBe(
      'just now'
    );
    expect(formatRelativeTime(new Date('2026-08-20T11:59:30.000Z').toISOString(), now)).toBe(
      '30s ago'
    );
  });

  it('handles minutes', () => {
    expect(formatRelativeTime(new Date('2026-08-20T11:55:00.000Z').toISOString(), now)).toBe(
      '5m ago'
    );
  });

  it('handles hours', () => {
    expect(formatRelativeTime(new Date('2026-08-20T09:00:00.000Z').toISOString(), now)).toBe(
      '3h ago'
    );
  });

  it('handles days', () => {
    expect(formatRelativeTime(new Date('2026-08-17T12:00:00.000Z').toISOString(), now)).toBe(
      '3d ago'
    );
  });

  it('handles months', () => {
    expect(formatRelativeTime(new Date('2026-06-01T12:00:00.000Z').toISOString(), now)).toBe(
      '3mo ago'
    );
  });

  it('handles years', () => {
    expect(formatRelativeTime(new Date('2024-08-20T12:00:00.000Z').toISOString(), now)).toBe(
      '2y ago'
    );
  });
});
