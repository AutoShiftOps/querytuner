import { describe, expect, it } from 'vitest';
import {
  shouldResetStaleAnthropicSelection,
  shouldResetStaleOpenAiSelection,
} from './providerSelection';

describe('shouldResetStaleOpenAiSelection — Bug 2(a) (docs/querytuner-quiz-provider-fixes.md)', () => {
  it('resets a stale "openai" selection once it is no longer allowed', () => {
    expect(shouldResetStaleOpenAiSelection('openai', false)).toBe(true);
  });

  it('does not reset when openai is still allowed', () => {
    expect(shouldResetStaleOpenAiSelection('openai', true)).toBe(false);
  });

  it('does not touch an anthropic selection either way', () => {
    expect(shouldResetStaleOpenAiSelection('anthropic', false)).toBe(false);
    expect(shouldResetStaleOpenAiSelection('anthropic', true)).toBe(false);
  });
});

describe('shouldResetStaleAnthropicSelection', () => {
  it('resets anthropic when it is no longer allowed, and nothing else', () => {
    expect(shouldResetStaleAnthropicSelection('anthropic', false)).toBe(true);
    expect(shouldResetStaleAnthropicSelection('anthropic', true)).toBe(false);
    expect(shouldResetStaleAnthropicSelection('openai', false)).toBe(false);
  });
});
