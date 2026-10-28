/**
 * The follow-up card shows the "try your own query" nudge immediately and
 * holds the survey back until the visitor has had time to read the findings.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import ResultFollowUp from './ResultFollowUp';

describe('ResultFollowUp — staggered prompts', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('shows the own-query nudge first and the survey only after a delay', () => {
    render(<ResultFollowUp onTryOwn={() => {}} />);
    expect(screen.getByText(/Now try your own slowest query/i)).toBeTruthy();
    expect(screen.queryByText(/what would stop you/i)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(15000);
    });
    expect(screen.getByText(/what would stop you/i)).toBeTruthy();
  });
});
