/**
 * BatchAnalysisPage.render.test.jsx — the interactive click-through this
 * page never got locally before this pass (see PR #170's own testing
 * notes: no component-render harness existed, so the form/results UI
 * could only be verified against a real Clerk session). Exercises all
 * three Pro-gating states plus the "Load a sample" -> "Analyze batch" ->
 * reconciled-results path end to end against a mocked API response.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import BatchAnalysisPage, { SOURCES } from './BatchAnalysisPage';
import { clerkState } from '../test/setup';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <BatchAnalysisPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  clerkState.isSignedIn = false;
  clerkState.user = null;
  vi.clearAllMocks();
});

describe('BatchAnalysisPage — signed out', () => {
  it('prompts sign-in rather than showing the form', async () => {
    renderPage();
    expect(await screen.findByText(/sign in for batch workload analysis/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /analyze batch/i })).not.toBeInTheDocument();
  });
});

describe('BatchAnalysisPage — signed in, free tier', () => {
  beforeEach(() => {
    clerkState.isSignedIn = true;
    axios.get.mockResolvedValue({ data: { is_pro: false, count: 0, limit: 10 } });
  });

  it('shows the locked Pro-feature state, not the form', async () => {
    renderPage();
    expect(
      await screen.findByText(/batch workload analysis is a pro feature/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upgrade to pro/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /analyze batch/i })).not.toBeInTheDocument();
  });
});

describe('BatchAnalysisPage — signed in, Pro', () => {
  beforeEach(() => {
    clerkState.isSignedIn = true;
    axios.get.mockResolvedValue({ data: { is_pro: true, count: 0, limit: -1 } });
  });

  it('shows the real form', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /analyze batch/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/export source/i)).toBeInTheDocument();
  });

  it('"Load a sample" populates the textarea with that source\'s sample', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('button', { name: /analyze batch/i });

    await user.click(screen.getByRole('button', { name: /load a sample/i }));

    const textarea = screen.getByPlaceholderText(/paste your/i);
    expect(textarea).toHaveValue(SOURCES.pg_stat_statements.sample);
  });

  it('shows an inline error instead of submitting an empty export', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('button', { name: /analyze batch/i });

    await user.click(screen.getByRole('button', { name: /analyze batch/i }));

    expect(await screen.findByText(/paste an export first/i)).toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('renders reconciled suggestions, dropped suggestions, and the per-query breakdown after a successful analysis', async () => {
    const user = userEvent.setup();
    axios.post.mockResolvedValue({
      data: {
        source: 'pg_stat_statements',
        db_type: 'postgresql',
        total_parsed: 2,
        analyzed_count: 2,
        queries: [
          {
            index: 0,
            query: 'SELECT * FROM orders WHERE customer_id = $1',
            calls: 4200,
            total_time_ms: 58800,
            index_suggestions: [
              {
                type: 'index_review_where_filter',
                severity: 'high',
                suggestion: 'WHERE column `customer_id` may lack an index',
                reason: 'Used as a filter condition',
                evidence_level: 'needs-runtime-evidence',
              },
            ],
          },
          {
            index: 1,
            query: 'SELECT * FROM orders WHERE customer_id = $1 AND status = $2',
            calls: 1800,
            total_time_ms: 41400,
            index_suggestions: [],
          },
        ],
        reconciled_index_suggestions: [
          {
            type: 'index_review_composite_index',
            severity: 'high',
            suggestion: 'Consider a composite index on (customer_id, status)',
            reason: 'Both columns filtered together across queries',
            evidence_level: 'needs-runtime-evidence',
            table: 'orders',
            satisfies_queries: [0, 1],
          },
        ],
        dropped_suggestions: [
          {
            table: 'orders',
            columns: ['customer_id'],
            suggestion: 'Single-column index on customer_id',
            source_query_indices: [0],
            reason: 'Subsumed by the composite index above',
            superseded_by_columns: ['customer_id', 'status'],
          },
        ],
        column_order_conflicts: [],
        warnings: [
          'Some suggestions were grouped by alias rather than a schema-resolved real table name.',
        ],
        analysis_time_ms: 12.5,
      },
    });

    renderPage();
    await screen.findByRole('button', { name: /analyze batch/i });

    await user.click(screen.getByRole('button', { name: /load a sample/i }));
    await user.click(screen.getByRole('button', { name: /analyze batch/i }));

    expect(await screen.findByText(/reconciled index recommendations \(1\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(/consider a composite index on \(customer_id, status\)/i)
    ).toBeInTheDocument();

    expect(screen.getByText(/redundant suggestions dropped \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/subsumed by the composite index above/i)).toBeInTheDocument();

    expect(screen.getByText(/per-query breakdown \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText(/some suggestions were grouped by alias/i)).toBeInTheDocument();

    // axios.post called with the sample export text and the default source/top_n.
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/analyze/batch'),
      expect.objectContaining({ source: 'pg_stat_statements', top_n: 20 }),
      expect.anything()
    );
  });

  it('surfaces a pro_required response by locking the page instead of silently failing', async () => {
    const user = userEvent.setup();
    axios.post.mockRejectedValue({ response: { data: { error: 'pro_required' } } });

    renderPage();
    await screen.findByRole('button', { name: /analyze batch/i });
    await user.click(screen.getByRole('button', { name: /load a sample/i }));
    await user.click(screen.getByRole('button', { name: /analyze batch/i }));

    // The locked state's own <h1> AND the UpgradeModal it opens (isOpen
    // becomes true on this error) both render the same title text — the
    // modal's is an <h2> (UpgradeModal.jsx), so target the <h1>
    // specifically rather than a plain getByText, which would find both
    // and throw "multiple elements".
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: /batch workload analysis is a pro feature/i })
      ).toBeInTheDocument();
    });
  });
});
