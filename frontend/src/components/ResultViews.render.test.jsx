import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ResultTabs, RewriteView } from './ResultViews';

describe('ResultTabs', () => {
  it('shows counts, hides hidden tabs and reports clicks', () => {
    const seen = [];
    render(
      <ResultTabs
        active="findings"
        onChange={(id) => seen.push(id)}
        tabs={[
          { id: 'findings', label: 'Findings', count: 8 },
          { id: 'indexes', label: 'Indexes', count: 0, hidden: true },
          { id: 'rewrite', label: 'Rewrite' },
        ]}
      />
    );
    expect(screen.getByRole('tab', { name: /Findings/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Indexes/ })).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: /Rewrite/ }));
    expect(seen).toEqual(['rewrite']);
  });
});

describe('RewriteView', () => {
  const base = { original: 'SELECT 1', rewrite: 'SELECT 2', isAi: true, changed: true };

  it('shows the rewrite and reveals the original on demand', () => {
    render(<RewriteView {...base} />);
    expect(screen.getByText('SELECT 2')).toBeInTheDocument();
    expect(screen.queryByText('SELECT 1')).toBeNull();
    fireEvent.click(screen.getByText(/Compare with original query/));
    expect(screen.getByText('SELECT 1')).toBeInTheDocument();
  });

  it('explains when the AI rewrite was cut off', () => {
    render(<RewriteView {...base} isAi={false} changed={false} aiCutOff />);
    expect(screen.getByText(/AI rewrite incomplete/)).toBeInTheDocument();
  });

  it('handles a missing rewrite', () => {
    render(<RewriteView {...base} rewrite="" />);
    expect(screen.getByText(/No safe automatic rewrite/)).toBeInTheDocument();
    expect(screen.getByText(/Enable "Use AI insights"/)).toBeInTheDocument();
  });
});

describe('RewriteView with AI fixes', () => {
  it('shows targeted fixes and the rejection note', () => {
    render(
      <RewriteView
        original="SELECT 1"
        rewrite=""
        aiRejected="it drops table #ScanSummary"
        aiFixes={[
          {
            title: 'Use a #temp table',
            before: 'DECLARE @t TABLE',
            after: 'CREATE TABLE #t',
            why: 'stats',
          },
        ]}
        aiEnabled
      />
    );
    expect(screen.getByText(/AI rewrite not shown/)).toBeInTheDocument();
    expect(screen.getByText(/drops table #ScanSummary/)).toBeInTheDocument();
    expect(screen.getByText(/1\. Use a #temp table/)).toBeInTheDocument();
    expect(screen.getByText('CREATE TABLE #t')).toBeInTheDocument();
    expect(screen.queryByText(/No safe automatic rewrite/)).toBeNull();
  });
});
