import { afterEach, describe, expect, it } from 'vitest';
import { readAiPreference, writeAiPreference, shouldDefaultAiOn } from './aiPreference';

afterEach(() => window.localStorage.clear());

describe('aiPreference', () => {
  it('returns null when nothing is stored or the value is unknown', () => {
    expect(readAiPreference()).toBeNull();
    window.localStorage.setItem('qt_ai_insights', 'maybe');
    expect(readAiPreference()).toBeNull();
  });

  it('round-trips an explicit choice', () => {
    writeAiPreference(false);
    expect(readAiPreference()).toBe('off');
    writeAiPreference(true);
    expect(readAiPreference()).toBe('on');
  });

  it('defaults AI on only for signed-in visitors with AI available who did not opt out', () => {
    const base = { isSignedIn: true, aiAvailable: true, preference: null };
    expect(shouldDefaultAiOn(base)).toBe(true);
    expect(shouldDefaultAiOn({ ...base, preference: 'on' })).toBe(true);
    expect(shouldDefaultAiOn({ ...base, preference: 'off' })).toBe(false);
    expect(shouldDefaultAiOn({ ...base, isSignedIn: false })).toBe(false);
    expect(shouldDefaultAiOn({ ...base, aiAvailable: false })).toBe(false);
  });
});
