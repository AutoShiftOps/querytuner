/**
 * QuizMode is opt-in and sits under the findings: collapsed by default,
 * and `onOpen` fires once when a visitor expands it.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import QuizMode from './QuizMode';

const questions = [
  {
    id: 'q1',
    prompt: 'What do you think is wrong with this query?',
    reason: 'SELECT * reads every column.',
    options: [
      { text: 'Select Specific Columns', isCorrect: true },
      { text: 'High Query Complexity', isCorrect: false },
    ],
  },
];

describe('QuizMode — opt-in', () => {
  it('is collapsed by default and does not show questions', () => {
    render(<QuizMode questions={questions} onOpen={() => {}} />);
    expect(screen.getByText(/Test yourself/i)).toBeTruthy();
    expect(screen.queryByText(/What do you think is wrong/i)).toBeNull();
  });

  it('expands on click and reports the open once', () => {
    const onOpen = vi.fn();
    render(<QuizMode questions={questions} onOpen={onOpen} />);
    fireEvent.click(screen.getByText(/Test yourself/i));
    expect(screen.getAllByText(/What do you think is wrong/i).length).toBeGreaterThan(0);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when there are no questions', () => {
    const { container } = render(<QuizMode questions={[]} onOpen={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});
