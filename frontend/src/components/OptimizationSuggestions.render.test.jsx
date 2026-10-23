import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import OptimizationSuggestions from './OptimizationSuggestions';

const suggestions = [
  {
    type: 'function_in_where',
    severity: 'critical',
    evidence_level: 'needs-runtime-evidence',
    suggestion: 'YEAR(col_b) wraps the column.',
    reason: 'Cannot use an index.',
    estimated_improvement: 'Up to 92% faster',
  },
  {
    type: 'index_review_join_key',
    severity: 'high',
    suggestion: 'JOIN key `a.col_b` may lack an index — lookups',
    ddl_hint: 'CREATE INDEX idx_a_col_b ON <a_table>(col_b);',
    rollback_ddl: 'DROP INDEX idx_a_col_b;',
  },
  {
    type: 'index_review_join_key',
    severity: 'high',
    suggestion: 'JOIN key `a.col_c` may lack an index — lookups',
    ddl_hint: 'CREATE INDEX idx_a_col_c ON <a_table>(col_c);',
  },
];

describe('OptimizationSuggestions', () => {
  it('renders findings (grouped by type) and the DDL card', () => {
    render(<OptimizationSuggestions suggestions={suggestions} />);
    expect(screen.getByText('Findings')).toBeTruthy();
    expect(screen.getByText(/Missing JOIN Index ×2/)).toBeTruthy();
    expect(screen.getByText('Optimization Suggestions')).toBeTruthy();
    expect(screen.getByText(/idx_a_col_c/)).toBeTruthy();
  });

  it('shows original names in findings and DDL when a substitution map is given', () => {
    render(
      <OptimizationSuggestions suggestions={suggestions} substitutionMap={{ category: 'col_b' }} />
    );
    expect(screen.getByText(/YEAR\(category\) wraps the column/)).toBeTruthy();
    expect(screen.getByText(/idx_a_category ON/)).toBeTruthy();
    expect(screen.queryByText(/Restore original names/)).toBeNull();
  });
});
