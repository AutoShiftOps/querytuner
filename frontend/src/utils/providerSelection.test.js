import { describe, expect, it } from 'vitest';
import { shouldResetStaleOpenAiSelection, shouldAutoSelectOpenAiForPro } from './providerSelection';

describe('shouldResetStaleOpenAiSelection — Bug 2(a) (docs/querytuner-quiz-provider-fixes.md)', () => {
  it('resets a stale "openai" selection once it is no longer allowed', () => {
    expect(shouldResetStaleOpenAiSelection('openai', false)).toBe(true);
  });

  it('does not reset when openai is still allowed', () => {
    expect(shouldResetStaleOpenAiSelection('openai', true)).toBe(false);
  });

  it('does not touch a huggingface selection either way', () => {
    expect(shouldResetStaleOpenAiSelection('huggingface', false)).toBe(false);
    expect(shouldResetStaleOpenAiSelection('huggingface', true)).toBe(false);
  });
});

describe('shouldAutoSelectOpenAiForPro — Bug 2(b)/(c)', () => {
  it('(b) auto-selects OpenAI for a fresh Pro session still on the default', () => {
    expect(shouldAutoSelectOpenAiForPro('huggingface', true, false)).toBe(true);
  });

  it('does not auto-select when OpenAI is not enabled', () => {
    expect(shouldAutoSelectOpenAiForPro('huggingface', false, false)).toBe(false);
  });

  it('does not auto-select when the dropdown is already on openai', () => {
    expect(shouldAutoSelectOpenAiForPro('openai', true, false)).toBe(false);
  });

  it('(c) does not fight a manual re-selection back to huggingface after already auto-selecting once', () => {
    // The user manually switched back to huggingface after the initial
    // auto-select already fired once (alreadySelected latched true) —
    // must not flip them back to openai against their own choice.
    expect(shouldAutoSelectOpenAiForPro('huggingface', true, true)).toBe(false);
  });
});
