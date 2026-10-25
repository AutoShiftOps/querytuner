/**
 * ResultsPanel.test.jsx — covers the "Most Impactful Improvements" silent
 * empty-state bug found via a real public report
 * (8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e): when every AI-returned
 * improvement overlaps an already-badged heuristic finding, the section
 * previously rendered nothing at all, indistinguishable from the AI call
 * having failed outright.
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Zap } from 'lucide-react';
import ResultsPanel from './ResultsPanel';

describe('ResultsPanel — AI Insights empty-state copy', () => {
  it('shows explicit "confirmed, nothing additional" copy when every improvement dedupes away', () => {
    const content = JSON.stringify({
      most_impactful_improvements: [{ type: 'select_star', suggestion: 'Avoid SELECT *' }],
      recommended_indexes: [],
      rewritten_query: '',
      risky_assumptions: [],
    });

    render(
      <ResultsPanel
        title="AI Insights (openai / gpt-4o-mini)"
        content={content}
        icon={Zap}
        aiConfirmedTypes={new Set(['select_star'])}
      />
    );

    expect(
      screen.getByText(/AI analysis agrees with the Findings tab/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Most Impactful Improvements/i)).not.toBeInTheDocument();
  });

  it('does not show the "confirmed" copy when the AI genuinely returned no improvements at all', () => {
    const content = JSON.stringify({
      most_impactful_improvements: [],
      recommended_indexes: [{ suggestion: 'Add an index on foo.bar' }],
      rewritten_query: '',
      risky_assumptions: [],
    });

    render(
      <ResultsPanel
        title="AI Insights (openai / gpt-4o-mini)"
        content={content}
        icon={Zap}
        aiConfirmedTypes={new Set()}
      />
    );

    // Nothing was deduped away (the AI simply didn't return any
    // improvements), so the "confirmed the findings above" message would
    // be misleading here — it should not appear.
    expect(
      screen.queryByText(/AI analysis agrees with the Findings tab/i)
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Recommended Indexes/i)).toBeInTheDocument();
  });

  it('still renders the normal improvements list when nothing was deduped', () => {
    const content = JSON.stringify({
      most_impactful_improvements: [{ type: 'missing_join_index', suggestion: 'Add a join index' }],
    });

    render(
      <ResultsPanel
        title="AI Insights (openai / gpt-4o-mini)"
        content={content}
        icon={Zap}
        aiConfirmedTypes={new Set()}
      />
    );

    expect(screen.getByText(/Most Impactful Improvements/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/AI analysis agrees with the Findings tab/i)
    ).not.toBeInTheDocument();
  });
});
