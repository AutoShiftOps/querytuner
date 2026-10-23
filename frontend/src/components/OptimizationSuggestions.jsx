import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import { desanitize } from '../utils/sanitizer';

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
  count_star_existence_check: 'COUNT(*) Existence Check',
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
function RollbackToggle({ ddl, substitutionMap }) {
  const [open, setOpen] = useState(false);
  // Show the user's real names when the query was sanitized before analysis.
  const shown = substitutionMap ? desanitize(ddl, substitutionMap) : ddl;
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
          {`To undo this index: ${shown}`}
        </pre>
      )}
    </div>
  );
}

function sevKey(sev) {
  const k = (sev || 'low').toLowerCase();
  return k in SEVERITY_ORDER ? k : 'low';
}

// One finding per rule type: five "Missing JOIN Index" cards for one query is
// noise, so same-type suggestions collapse into a single row (their DDL still
// appears individually in the Optimization Suggestions card below).
export function groupFindings(items) {
  const groups = new Map();
  for (const s of items) {
    const key = s.type || 'issue';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  return [...groups.entries()]
    .map(([type, list]) => ({
      type,
      list,
      severity: list.reduce(
        (worst, s) =>
          SEVERITY_ORDER[sevKey(s.severity)] < SEVERITY_ORDER[worst] ? sevKey(s.severity) : worst,
        'low'
      ),
    }))
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

function Chip({ children, title }) {
  return (
    <span
      title={title}
      className="text-xs px-2.5 py-1 rounded-md"
      style={{ background: 'rgba(148,163,184,0.12)', color: '#94a3b8' }}
    >
      {children}
    </span>
  );
}

function CardShell({ icon, title, subtitle, children }) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
    >
      <div
        className="flex items-center gap-2 px-5 py-3"
        style={{ borderBottom: '1px solid #2d3f55' }}
      >
        {icon}
        <span className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>
          {title}
        </span>
        {subtitle && (
          <span className="text-xs ml-1" style={{ color: '#4a6480' }}>
            {subtitle}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

function FindingRow({ group, aiConfirmedTypes, substitutionMap }) {
  const { type, list, severity } = group;
  // Findings are generated from the sanitized query; show the user's own names.
  const d = (t) => (substitutionMap ? desanitize(String(t ?? ''), substitutionMap) : t);
  const first = list[0];
  const st = SEVERITY_STYLE[severity];
  const many = list.length > 1;
  const confirmedByAi = Boolean(aiConfirmedTypes?.has?.(type));
  const evidenceCfg = EVIDENCE_CONFIG[first.evidence_level];
  return (
    <div
      className="px-5 py-4"
      style={{ borderLeft: `4px solid ${st.color}`, borderTop: '1px solid #2d3f55' }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="text-xs font-bold px-2 py-0.5 rounded"
          style={{ color: st.color, background: st.bg, letterSpacing: '0.04em' }}
        >
          {severity.toUpperCase()}
        </span>
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
        <EvidenceBadge level={first.evidence_level} />
      </div>
      <p className="mt-2 font-semibold text-white">
        {typeLabel(type)}
        {many ? ` ×${list.length}` : ''}
      </p>
      {many ? (
        <ul className="mt-1 text-sm space-y-0.5" style={{ color: '#94a3b8' }}>
          {list.map((s, i) => (
            <li key={i}>• {d(String(s.suggestion || '').split(' — ')[0])}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm" style={{ color: '#94a3b8' }}>
          {d(first.suggestion)}
        </p>
      )}
      {first.reason ? (
        <p className="mt-1 text-sm" style={{ color: '#7f93ab' }}>
          {d(first.reason)}
        </p>
      ) : null}
      {(first.cost_estimate ||
        (first.estimated_improvement &&
          !/^varies\.?$/i.test(first.estimated_improvement.trim()))) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {first.estimated_improvement &&
            !/^varies\.?$/i.test(first.estimated_improvement.trim()) && (
              <Chip>Impact: {first.estimated_improvement}</Chip>
            )}
          {first.cost_estimate && <Chip>Cost: {first.cost_estimate}</Chip>}
        </div>
      )}
      {evidenceCfg && (
        <p className="mt-2 text-xs" style={{ color: '#64748b' }}>
          {evidenceCfg.subtitle}
        </p>
      )}
      {/* Issue #63: pasted EXPLAIN plan already shows an index on this column —
          surfaced explicitly so a stale suggestion doesn't ship with false
          confidence. */}
      {list.some((s) => s.plan_contradicts) ? (
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
            Your pasted EXPLAIN plan shows an index already covering this column — this suggestion
            may be outdated. Verify before applying it.
          </span>
        </div>
      ) : null}
    </div>
  );
}

function DdlBlock({ s, substitutionMap }) {
  // The backend only saw sanitized names; show (and copy) the user's own.
  const ddl = substitutionMap ? desanitize(s.ddl_hint, substitutionMap) : s.ddl_hint;
  return (
    <div className="px-5 py-3" style={{ borderTop: '1px solid #2d3f55' }}>
      <div className="flex items-start justify-between gap-3">
        <pre
          className="text-xs rounded p-3 flex-1 min-w-0 whitespace-pre-wrap break-words"
          style={{
            background: '#0f172a',
            color: '#7dd3fc',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {ddl}
        </pre>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(ddl)}
          className="text-xs text-slate-400 hover:text-white border border-slate-600 hover:border-slate-400 px-3 py-1 rounded transition-colors"
        >
          Copy
        </button>
      </div>
      {s.rollback_ddl ? (
        <RollbackToggle ddl={s.rollback_ddl} substitutionMap={substitutionMap} />
      ) : null}
    </div>
  );
}

export default function OptimizationSuggestions({
  suggestions,
  aiConfirmedTypes,
  substitutionMap,
}) {
  const items = Array.isArray(suggestions) ? suggestions : [];
  const bolt = <Zap className="w-4 h-4" style={{ color: '#f97316' }} />;

  if (items.length === 0) {
    return (
      <CardShell icon={bolt} title="Findings" subtitle="Deterministic rules — always available">
        <p className="text-slate-400 text-sm px-5 py-4">No suggestions found.</p>
      </CardShell>
    );
  }

  const groups = groupFindings(items);
  const seen = new Set();
  const ddlItems = items.filter((s) => {
    if (!s.ddl_hint || seen.has(s.ddl_hint)) return false;
    seen.add(s.ddl_hint);
    return true;
  });

  return (
    <div className="space-y-4">
      <CardShell
        icon={bolt}
        title="Findings"
        subtitle="Deterministic rules — sub-second, always available"
      >
        {groups.map((g) => (
          <FindingRow
            key={g.type}
            group={g}
            aiConfirmedTypes={aiConfirmedTypes}
            substitutionMap={substitutionMap}
          />
        ))}
      </CardShell>

      {ddlItems.length > 0 && (
        <CardShell
          icon={<span aria-hidden="true">📈</span>}
          title="Optimization Suggestions"
          subtitle="Review before applying"
        >
          {ddlItems.map((s, i) => (
            <DdlBlock key={i} s={s} substitutionMap={substitutionMap} />
          ))}
        </CardShell>
      )}
    </div>
  );
}
