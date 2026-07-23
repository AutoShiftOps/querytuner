import React, { useState } from 'react';
import { Zap } from 'lucide-react';

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

// Three-tier evidence labels — how confident QueryTuner actually is about a
// finding, instead of a binary confirmed/estimated flag. See backend
// app/schemas/models.py OptimizationSuggestion.evidence_level.
const EVIDENCE_CONFIG = {
  deterministic: {
    background: 'rgba(56,189,248,0.1)',
    color: '#38bdf8',
    border: '1px solid rgba(56,189,248,0.2)',
    text: 'Deterministic',
    subtitle: 'Always applies regardless of data distribution',
  },
  'schema-verified': {
    background: 'rgba(52,211,153,0.1)',
    color: '#34d399',
    border: '1px solid rgba(52,211,153,0.2)',
    text: 'Schema Verified',
    subtitle: 'Verified against your provided DDL',
  },
  'needs-runtime-evidence': {
    background: 'rgba(251,191,36,0.08)',
    color: '#fbbf24',
    border: '1px solid rgba(251,191,36,0.2)',
    text: 'Estimated',
    subtitle: 'Likely applies — verify with EXPLAIN before creating',
  },
};

function EvidenceBadge({ level }) {
  const cfg = EVIDENCE_CONFIG[level];
  if (!cfg) return null;
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.background, color: cfg.color, border: cfg.border }}
      title={cfg.subtitle}
    >
      {cfg.text}
    </span>
  );
}

// Frames this panel as "fast, deterministic, always-on" — the complement to
// the AI panel's "deeper, additive reasoning" framing — so the two panels
// read as two layers of analysis rather than duplicated findings.
// Collapsed by default — rollback DDL is a "break glass" action, not
// something to surface at the same visual weight as the suggestion itself.
function RollbackToggle({ ddl }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium"
        style={{
          color: '#f87171',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
        }}
      >
        {open ? '▾' : '▸'} Rollback
      </button>
      {open && (
        <pre
          className="mt-1 text-xs rounded p-2 overflow-x-auto"
          style={{
            background: '#0f172a',
            color: '#f87171',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {`To undo this index: ${ddl}`}
        </pre>
      )}
    </div>
  );
}

function HeuristicHeader() {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <Zap className="w-3.5 h-3.5" style={{ color: '#38bdf8' }} />
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: '#38bdf8',
          }}
        >
          Heuristic Analysis
        </span>
      </div>
      <p className="text-xs mt-1" style={{ color: '#4a6480' }}>
        Deterministic rules — sub-second, always available
      </p>
    </div>
  );
}

export default function OptimizationSuggestions({ suggestions, aiConfirmedTypes }) {
  const items = Array.isArray(suggestions) ? suggestions : [];

  if (items.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <HeuristicHeader />
        <h3 className="text-lg font-bold text-white">Suggestions</h3>
        <p className="text-slate-400 text-sm mt-2">No suggestions found.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <HeuristicHeader />
      <h3 className="text-lg font-bold text-white mb-4">Suggestions</h3>

      <div className="space-y-3">
        {items.map((s, idx) => {
          const confirmedByAi = Boolean(aiConfirmedTypes?.has?.(s.type));
          const evidenceCfg = EVIDENCE_CONFIG[s.evidence_level];
          return (
            <div key={idx} className={`p-4 rounded border ${severityColor(s.severity)}`}>
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold">{typeLabel(s.type)}</p>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {confirmedByAi && (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full whitespace-nowrap"
                      style={{
                        color: '#7fa3c4',
                        background: 'rgba(127,163,196,0.1)',
                        border: '1px solid rgba(127,163,196,0.3)',
                      }}
                    >
                      ✓ Confirmed by AI
                    </span>
                  )}
                  <EvidenceBadge level={s.evidence_level} />
                  <span className="text-xs opacity-90">{(s.severity || 'low').toUpperCase()}</span>
                </div>
              </div>

              {evidenceCfg && (
                <p className="mt-1 text-xs" style={{ color: '#64748b' }}>
                  {evidenceCfg.subtitle}
                </p>
              )}

              <p className="mt-2">{s.suggestion}</p>

              {s.reason ? <p className="mt-2 text-sm opacity-90">Reason: {s.reason}</p> : null}

              {s.estimated_improvement ? (
                <p className="mt-2 text-sm opacity-90">Estimate: {s.estimated_improvement}</p>
              ) : null}

              {s.ddl_hint ? (
                <pre
                  className="mt-2 text-xs rounded p-2 overflow-x-auto"
                  style={{
                    background: '#0f172a',
                    color: '#7dd3fc',
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {s.ddl_hint}
                </pre>
              ) : null}

              {s.rollback_ddl ? <RollbackToggle ddl={s.rollback_ddl} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
