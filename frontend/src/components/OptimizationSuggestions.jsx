import React from 'react';

function severityColor(sev) {
  const s = (sev || '').toLowerCase();
  if (s === 'critical') return 'border-red-500 bg-red-900/20 text-red-200';
  if (s === 'high') return 'border-orange-500 bg-orange-900/20 text-orange-200';
  if (s === 'medium') return 'border-yellow-500 bg-yellow-900/20 text-yellow-200';
  return 'border-slate-600 bg-slate-800 text-slate-200';
}

// Internal heuristic identifiers -> human-readable titles.
const TYPE_LABELS = {
  column_selection: 'Select Specific Columns',
  full_scan_risk: 'Full Table Scan Risk',
  like_wildcard: 'Index-Blocking LIKE Pattern',
  function_in_where: 'Function Blocking Index',
  order_by_no_limit: 'Missing Pagination',
  join_complexity: 'High JOIN Complexity',
  cartesian_join: 'Cartesian JOIN Detected',
  subquery_refactor: 'Subquery Refactor Opportunity',
  implicit_cast: 'Implicit Type Cast',
  subquery_to_join: 'Correlated Subquery in SELECT',
  high_complexity: 'High Query Complexity',
  security_best_practice: 'Security Best Practice',
  index_review_join_key: 'Missing JOIN Index',
  index_review_where_filter: 'Missing WHERE Index',
  index_review_order_by_index: 'Missing ORDER BY Index',
  index_review_group_by_index: 'Missing GROUP BY Index',
  index_review_partial_index_candidate: 'Partial Index Opportunity',
  index_review_composite_index: 'Composite Index Opportunity',
};

function typeLabel(type) {
  const t = type || 'issue';
  return (
    TYPE_LABELS[t] ||
    t
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export default function OptimizationSuggestions({ suggestions }) {
  const items = Array.isArray(suggestions) ? suggestions : [];

  if (items.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h3 className="text-lg font-bold text-white">Suggestions</h3>
        <p className="text-slate-400 text-sm mt-2">No suggestions found.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h3 className="text-lg font-bold text-white mb-4">Suggestions</h3>

      <div className="space-y-3">
        {items.map((s, idx) => (
          <div key={idx} className={`p-4 rounded border ${severityColor(s.severity)}`}>
            <div className="flex items-center justify-between gap-3">
              <p className="font-semibold">{typeLabel(s.type)}</p>
              <span className="text-xs opacity-90">{(s.severity || 'low').toUpperCase()}</span>
            </div>

            <p className="mt-2">{s.suggestion}</p>

            {s.reason ? <p className="mt-2 text-sm opacity-90">Reason: {s.reason}</p> : null}

            {s.estimated_improvement ? (
              <p className="mt-2 text-sm opacity-90">Estimate: {s.estimated_improvement}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
