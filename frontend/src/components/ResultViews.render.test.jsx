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
    expect(screen.getByText(/rewrite was cut off/)).toBeInTheDocument();
  });

  it('handles a missing rewrite', () => {
    render(<RewriteView {...base} rewrite="" />);
    expect(screen.getByText(/No safe automatic rewrite/)).toBeInTheDocument();
    expect(screen.getByText(/Enable "Use AI insights"/)).toBeInTheDocument();
  });
});
