import { describe, expect, it, vi } from 'vitest';
import {
  buildUrlWithoutUpgradedParam,
  hasUpgradedParam,
  pollForProStatus,
} from './upgradeRedirect';

describe('hasUpgradedParam', () => {
  it('detects ?upgraded=true', () => {
    expect(hasUpgradedParam('?upgraded=true')).toBe(true);
    expect(hasUpgradedParam('?foo=bar&upgraded=true')).toBe(true);
  });

  it('is false when absent or any other value', () => {
    expect(hasUpgradedParam('')).toBe(false);
    expect(hasUpgradedParam('?foo=bar')).toBe(false);
    expect(hasUpgradedParam('?upgraded=false')).toBe(false);
    expect(hasUpgradedParam('?upgraded=1')).toBe(false);
  });
});

describe('buildUrlWithoutUpgradedParam', () => {
  it('strips upgraded and leaves other params intact', () => {
    const result = buildUrlWithoutUpgradedParam('https://querytuner.com/?upgraded=true&ref=email');
    expect(result).toBe('https://querytuner.com/?ref=email');
  });

  it('leaves the URL otherwise unchanged when upgraded is absent', () => {
    const result = buildUrlWithoutUpgradedParam('https://querytuner.com/');
    expect(result).toBe('https://querytuner.com/');
  });
});

describe('pollForProStatus', () => {
  // No real waiting in any test below — an instant delayFn stands in for
  // the real 1.5s backoff so these run in milliseconds, not seconds.
  const instant = () => Promise.resolve();

  it('immediate success: is_pro already true on the first fetch', async () => {
    const fetchUsage = vi.fn().mockResolvedValue({ count: 3, is_pro: true, limit: 10 });

    const result = await pollForProStatus(fetchUsage, { delayFn: instant });

    expect(result.success).toBe(true);
    expect(result.attempts).toBe(1);
    expect(result.usage).toEqual({ count: 3, is_pro: true, limit: 10 });
    expect(fetchUsage).toHaveBeenCalledTimes(1);
  });

  it('flips true after a couple retries (webhook lands late)', async () => {
    const fetchUsage = vi
      .fn()
      .mockResolvedValueOnce({ count: 3, is_pro: false, limit: 10 })
      .mockResolvedValueOnce({ count: 3, is_pro: false, limit: 10 })
      .mockResolvedValueOnce({ count: 3, is_pro: true, limit: 10 });

    const result = await pollForProStatus(fetchUsage, { delayFn: instant });

    expect(result.success).toBe(true);
    expect(result.attempts).toBe(3);
    expect(result.usage.is_pro).toBe(true);
    expect(fetchUsage).toHaveBeenCalledTimes(3);
  });

  it('gives up after exhausting attempts if it never flips', async () => {
    const fetchUsage = vi.fn().mockResolvedValue({ count: 3, is_pro: false, limit: 10 });

    const result = await pollForProStatus(fetchUsage, { attempts: 5, delayFn: instant });

    expect(result.success).toBe(false);
    expect(result.usage).toBeNull();
    expect(result.attempts).toBe(5);
    expect(fetchUsage).toHaveBeenCalledTimes(5);
  });

  it('treats a failed fetch as "not yet pro" for that attempt rather than aborting the poll', async () => {
    const fetchUsage = vi
      .fn()
      .mockRejectedValueOnce(new Error('network blip'))
      .mockResolvedValueOnce({ count: 3, is_pro: true, limit: 10 });

    const result = await pollForProStatus(fetchUsage, { delayFn: instant });

    expect(result.success).toBe(true);
    expect(result.attempts).toBe(2);
  });

  it('respects a custom attempts count', async () => {
    const fetchUsage = vi.fn().mockResolvedValue({ count: 0, is_pro: false, limit: 10 });

    const result = await pollForProStatus(fetchUsage, { attempts: 2, delayFn: instant });

    expect(result.success).toBe(false);
    expect(fetchUsage).toHaveBeenCalledTimes(2);
  });
});
