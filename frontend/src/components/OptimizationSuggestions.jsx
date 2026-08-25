import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import { desanitize } from '../utils/sanitizer';

function severityColor(sev) {
  const s = (sev || '').toLowerCase();
  if (s === 'critical') return 'border-red-500 bg-red-900/20 text-red-200';
  if (s === 'high') return 'border-orange-500 bg-orange-900/20 text-orange-200';
  if (s === 'medium') return 'border-yellow-500 bg-yellow-900/20 text-yellow-200';
  return 'border-slate-600 bg-slate-800 text-slate-200';
}

// Internal heuristic identifiers -> human-readable titles.
// Exported for reuse by utils/quiz.js (Quiz Mode's distractor labels need
// the exact same wording a real analysis would show, not a second,
// possibly-drifting copy of this map — docs/querytuner-quiz-mode-issue.md).
export const TYPE_LABELS = {
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
  not_in_nullable: 'NOT IN Nullable Subquery',
  case_in_predicate: 'CASE Expression in WHERE',
  or_expansion: 'OR Expansion Risk',
  cte_multiple_references: 'CTE Referenced Multiple Times',
  // Gap-followup (querytuner-explain-parser-gap-followup.md, #63 item 4):
  // plan-only, MySQL-specific — surfaced straight from a pasted EXPLAIN's
  // Extra field, so unlike everything else in this table these only ever
  // appear already evidence_level "schema-verified".
  filesort_detected: 'Filesort Detected',
  temp_table_detected: 'Temporary Table Detected',
};

export function typeLabel(type) {
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

// Shown only when the query was sanitized before analysis — restores the
// original table/column names into the sanitized ddl_hint so the user gets
// copy-pasteable production DDL rather than the table_a/col_a placeholders.
function RestoreNamesToggle({ ddl, substitutionMap }) {
  const [open, setOpen] = useState(false);
  const restored = desanitize(ddl, substitutionMap);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium"
        style={{
          color: '#38bdf8',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
        }}
      >
        {open ? '▾' : '▸'} Restore original names
      </button>
      {open && (
        <div className="mt-2">
          <p className="text-xs" style={{ color: '#64748b' }}>
            Original (sanitized):
          </p>
          <pre
            className="mt-1 text-xs rounded p-2 overflow-x-auto"
            style={{
              background: '#0f172a',
              color: '#7dd3fc',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {ddl}
          </pre>
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs" style={{ color: '#64748b' }}>
              ↓ Restored names:
            </p>
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(restored)}
              className="text-xs text-slate-400 hover:text-white border border-slate-600
                         hover:border-slate-400 px-3 py-1 rounded transition-colors"
            >
              Copy
            </button>
          </div>
          <pre
            className="mt-1 text-xs rounded p-2 overflow-x-auto"
            style={{
              background: '#0f172a',
              color: '#34d399',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {restored}
          </pre>
        </div>
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

export default function OptimizationSuggestions({
  suggestions,
  aiConfirmedTypes,
  substitutionMap,
}) {
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

              {/* Issue #118: the write/storage cost counterpart to the read-side
                  estimate above — rendered right under it so the trade-off reads
                  together, not just the upside. Index suggestions only
                  (cost_estimate is None for every other suggestion type). */}
              {s.cost_estimate ? (
                <p className="mt-1 text-sm opacity-90">Cost: {s.cost_estimate}</p>
              ) : null}

              {/* Issue #63: your pasted EXPLAIN plan shows an index already
                  covering this exact column — this suggestion (which assumes
                  it's unindexed) is likely stale or based on incomplete
                  information. Surfaced explicitly rather than silently
                  upgrading evidence, so a wrong suggestion doesn't ship with
                  false confidence. The confirmation case (plan_verified)
                  needs no equivalent UI — it just reads as evidence_level
                  "schema-verified" via the existing EvidenceBadge, identical
                  to a schema-DDL confirmation, per the same UI copy's
                  existing promise. */}
              {s.plan_contradicts ? (
                <div
                  className="mt-2 text-xs rounded px-2 py-1.5 flex items-start gap-1.5"
                  style={{
                    background: 'rgba(248,113,113,0.1)',
                    color: '#f87171',
                    border: '1px solid rgba(248,113,113,0.3)',
                  }}
                  title="Your pasted EXPLAIN plan contradicts this suggestion"
                >
                  <span aria-hidden="true">⚠</span>
                  <span>
                    Your pasted EXPLAIN plan shows an index already covering this column — this
                    suggestion may be outdated. Verify before applying it.
                  </span>
                </div>
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

              {s.ddl_hint && substitutionMap ? (
                <RestoreNamesToggle ddl={s.ddl_hint} substitutionMap={substitutionMap} />
              ) : null}

              {s.rollback_ddl ? <RollbackToggle ddl={s.rollback_ddl} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
