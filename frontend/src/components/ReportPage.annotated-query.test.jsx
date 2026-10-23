/**
 * ReportPage.annotated-query.test.jsx — covers the misleading "Optimized
 * Query" label found via a real public report
 * (8f05a5fc-7f7b-4103-b24a-eb8afc6e7f1e): backend/app/agents/optimizer.py
 * only ever inserts comments/annotations, it never actually restructures
 * the query, so labeling it "Optimized Query" with a "✓ optimized" badge
 * right next to AI Insights' genuinely-rewritten "Rewritten Query" read as
 * contradictory.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import axios from 'axios';
import ReportPage from './ReportPage';
import { clerkState } from '../test/setup';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

function renderReportPage(id = 'abc123') {
  return render(
    <MemoryRouter initialEntries={[`/report/${id}`]}>
      <Routes>
        <Route path="/report/:id" element={<ReportPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  clerkState.isSignedIn = false;
  clerkState.user = null;
  vi.clearAllMocks();
});

describe('ReportPage — Annotated Query section', () => {
  it('labels the comment-annotated query "Annotated Query", not "Optimized Query"', async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        db_type: 'sqlserver',
        severity: 'high',
        readability_score: 60,
        optimization_suggestions: [],
        optimized_query:
          '-- QueryTuner: Suggested optimized SQL\nSELECT /* TODO: list required columns */ * FROM foo',
      },
    });

    renderReportPage();

    await waitFor(() => expect(screen.getByText(/Annotated Query/i)).toBeInTheDocument());
    expect(screen.queryByText(/^Optimized Query$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/✓ optimized/i)).not.toBeInTheDocument();
    expect(screen.getByText(/inline hints only/i)).toBeInTheDocument();
    expect(
      screen.getByText(/For an actual AI-suggested rewrite, see Rewritten Query/i)
    ).toBeInTheDocument();
  });
});
