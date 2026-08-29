/**
 * BatchAnalysisPage.jsx — Phase 5 (#115/#120): the frontend half of batch
 * workload analysis that #115/#120's original build deliberately shipped
 * backend-only (docs/querytuner-batch-analysis-issue.md: "Not built in
 * this pass, deliberately... this was a backend-first scope call"). The
 * pricing page has advertised this to Pro users since PR #167's caveat
 * note; this is what removes the need for that caveat.
 *
 * Backend: POST /analyze/batch (backend/app/main.py) — Pro-gated the same
 * way GET /history is (401 sign_in_required, 403 pro_required). Accepts a
 * pasted export from one of three named production sources (SQL Server
 * Query Store / PostgreSQL pg_stat_statements / MySQL performance_schema)
 * and returns per-query index suggestions plus a reconciled, cross-query
 * recommendation set — collapsing suggestions redundant once a wider
 * composite exists on the same table, and flagging (not silently
 * resolving) suggestions that disagree on column order.
 *
 * Self-contained styles (own T tokens / injected <style> block) rather
 * than importing HistoryPage.jsx's or OptimizationSuggestions.jsx's —
 * same reasoning HistoryPage.jsx's own docstring already gives for this
 * codebase: this page has its own identity and a shared theme module
 * isn't worth the risk of a regression elsewhere for the duplication
 * saved. typeLabel() is the one exception — a pure lookup function with
 * no styling dependencies, already reused by utils/quiz.js for exactly
 * this reason.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth, useUser, SignInButton } from '@clerk/clerk-react';
import axios from 'axios';
import { typeLabel } from './OptimizationSuggestions';
import UpgradeModal from './UpgradeModal';

const API_URL =
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api');

// ── Design tokens (mirrors HistoryPage.jsx / PricingPage.jsx's #0f172a palette) ──
const T = {
  bg: '#0f172a',
  surface: '#1e293b',
  surfaceHigh: '#263347',
  border: '#2d3f55',
  borderBright: '#3b5268',
  text: '#e2e8f0',
  textMuted: '#7fa3c4',
  textDim: '#4a6480',
  accent: '#38bdf8',
  green: '#34d399',
  yellow: '#fbbf24',
  orange: '#f97316',
  red: '#f87171',
};

const SEV = {
  critical: { badge: '#3d1515', text: T.red, label: 'Critical' },
  high: { badge: '#3d2210', text: T.orange, label: 'High' },
  medium: { badge: '#3a2c0a', text: T.yellow, label: 'Medium' },
  low: { badge: '#0d3328', text: T.green, label: 'Low' },
};

// Same three-tier evidence system as OptimizationSuggestions.jsx's
// EVIDENCE_CONFIG — duplicated rather than imported since that module's
// version is styled with inline rgba() values tuned for Tailwind's
// slate-800 card background, not this page's own T tokens. Values/labels
// must stay in sync with backend/app/schemas/models.py's evidence_level
// docstring if that three-tier system ever changes.
const EVIDENCE = {
  deterministic: { color: T.accent, text: 'Deterministic' },
  'schema-verified': { color: T.green, text: 'Schema Verified' },
  'needs-runtime-evidence': { color: T.yellow, text: 'Estimated' },
};

// One realistic sample per source, matching each parser's own documented
// export query (backend/app/tools/batch_parsers.py) — lets a visitor try
// this without having a real production export on hand.
export const SOURCES = {
  pg_stat_statements: {
    label: 'PostgreSQL — pg_stat_statements',
    exportQuery:
      'SELECT query, calls, total_exec_time, mean_exec_time\n' +
      'FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 50;',
    sample: JSON.stringify(
      [
        {
          query: 'SELECT * FROM orders WHERE customer_id = $1',
          calls: 4200,
          total_exec_time: 58800,
        },
        {
          query: 'SELECT * FROM orders WHERE customer_id = $1 AND status = $2',
          calls: 1800,
          total_exec_time: 41400,
        },
        {
          query:
            'SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.status = $1',
          calls: 950,
          total_exec_time: 22800,
        },
      ],
      null,
      2
    ),
  },
  performance_schema: {
    label: 'MySQL — performance_schema',
    exportQuery:
      'SELECT digest_text, count_star, sum_timer_wait\n' +
      'FROM performance_schema.events_statements_summary_by_digest\n' +
      'ORDER BY sum_timer_wait DESC LIMIT 50;',
    sample: JSON.stringify(
      [
        {
          digest_text: 'SELECT * FROM `orders` WHERE `customer_id` = ?',
          count_star: 3900,
          sum_timer_wait: 52_000_000_000_000,
        },
        {
          digest_text: 'SELECT * FROM `orders` WHERE `customer_id` = ? AND `status` = ?',
          count_star: 1500,
          sum_timer_wait: 34_000_000_000_000,
        },
      ],
      null,
      2
    ),
  },
  query_store: {
    label: 'SQL Server — Query Store',
    exportQuery:
      'SELECT qt.query_sql_text, rs.count_executions, rs.avg_duration\n' +
      'FROM sys.query_store_query_text qt\n' +
      'JOIN sys.query_store_query q ON qt.query_text_id = q.query_text_id\n' +
      'JOIN sys.query_store_plan p ON q.query_id = p.query_id\n' +
      'JOIN sys.query_store_runtime_stats rs ON p.plan_id = rs.plan_id\n' +
      'ORDER BY rs.avg_duration DESC;',
    sample: JSON.stringify(
      [
        {
          query_sql_text: 'SELECT * FROM orders WHERE customer_id = @id',
          count_executions: 5100,
          avg_duration: 14000,
        },
        {
          query_sql_text: 'SELECT * FROM orders WHERE customer_id = @id AND status = @status',
          count_executions: 2200,
          avg_duration: 19000,
        },
      ],
      null,
      2
    ),
  },
};

function injectStyles() {
  if (document.getElementById('qt-batch-styles')) return;
  const style = document.createElement('style');
  style.id = 'qt-batch-styles';
  style.textContent = `
    :where(.qt-batch *) { box-sizing: border-box; }
    .qt-batch {
      font-family: 'IBM Plex Sans', system-ui, sans-serif;
      background: ${T.bg};
      min-height: 100vh;
      color: ${T.text};
    }
    .qt-batch-shell { max-width: 860px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    .qt-batch-nav {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 1.75rem; margin-bottom: 1.75rem;
      border-bottom: 1px solid ${T.border};
    }
    .qt-batch-brand { display: flex; align-items: center; gap: 8px; text-decoration: none; }
    .qt-batch-brand-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: ${T.accent}; box-shadow: 0 0 8px ${T.accent};
    }
    .qt-batch-brand-name {
      font-size: 13px; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; color: ${T.accent};
    }
    .qt-batch-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 6px; font-size: 12px;
      font-weight: 500; cursor: pointer; transition: all 0.15s;
      font-family: inherit; border: none; text-decoration: none;
    }
    .qt-batch-btn-primary { background: ${T.accent}; color: #0f172a; font-weight: 600; }
    .qt-batch-btn-primary:hover { background: #7dd3fc; }
    .qt-batch-btn-primary:disabled { opacity: 0.5; cursor: default; }
    .qt-batch-btn-ghost { background: transparent; border: 1px solid ${T.border}; color: ${T.textMuted}; }
    .qt-batch-btn-ghost:hover { border-color: ${T.borderBright}; color: ${T.text}; }
    .qt-batch-title { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 6px; }
    .qt-batch-subtitle { font-size: 13px; color: ${T.textMuted}; margin-bottom: 1.75rem; }

    .qt-batch-field { margin-bottom: 1.1rem; }
    .qt-batch-label { display: block; font-size: 12px; font-weight: 600; color: ${T.textMuted}; margin-bottom: 6px; }
    .qt-batch-select, .qt-batch-input {
      width: 100%; background: ${T.bg}; border: 1px solid ${T.border}; border-radius: 8px;
      color: ${T.text}; font-family: inherit; font-size: 13px; padding: 9px 12px;
    }
    .qt-batch-select:focus, .qt-batch-input:focus, .qt-batch-textarea:focus {
      outline: none; border-color: ${T.accent};
    }
    .qt-batch-textarea {
      width: 100%; background: ${T.bg}; border: 1px solid ${T.border}; border-radius: 8px;
      color: ${T.text}; font-family: 'JetBrains Mono', monospace; font-size: 12px;
      padding: 12px; min-height: 160px; resize: vertical;
    }
    .qt-batch-hint { font-size: 11px; color: ${T.textDim}; margin-top: 6px; }
    .qt-batch-row { display: flex; gap: 12px; flex-wrap: wrap; }
    .qt-batch-row > * { flex: 1; min-width: 140px; }

    .qt-batch-card {
      background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 10px;
      padding: 14px 16px; margin-bottom: 10px;
    }
    .qt-batch-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
    .qt-batch-chip {
      display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 20px;
      font-size: 10px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .qt-batch-ddl {
      margin-top: 8px; padding: 8px 10px; border-radius: 6px; overflow-x: auto;
      background: ${T.bg}; color: #7dd3fc; font-family: 'JetBrains Mono', monospace; font-size: 11px;
    }
    .qt-batch-section-title {
      font-size: 15px; font-weight: 600; margin: 1.75rem 0 0.75rem;
      display: flex; align-items: center; gap: 8px;
    }
    .qt-batch-summary-bar {
      display: flex; gap: 16px; flex-wrap: wrap; padding: 12px 16px;
      background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 10px;
      margin-bottom: 1.25rem; font-size: 12px; color: ${T.textMuted};
    }
    .qt-batch-summary-stat strong { color: ${T.text}; }
    .qt-batch-query-row {
      background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 8px;
      margin-bottom: 6px; overflow: hidden;
    }
    .qt-batch-query-head {
      display: flex; align-items: center; gap: 10px; padding: 10px 14px;
      cursor: pointer; user-select: none;
    }
    .qt-batch-query-head:hover { background: ${T.surfaceHigh}; }
    .qt-batch-query-text {
      flex: 1; min-width: 0; font-family: 'JetBrains Mono', monospace; font-size: 11.5px;
      color: ${T.textMuted}; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .qt-batch-query-body { padding: 0 14px 14px; border-top: 1px solid ${T.border}; }
    .qt-batch-warning {
      background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.25);
      color: ${T.yellow}; border-radius: 8px; padding: 10px 14px; font-size: 12px; margin-bottom: 1rem;
    }
    .qt-batch-error {
      background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.25);
      color: ${T.red}; border-radius: 8px; padding: 10px 14px; font-size: 12px; margin-bottom: 1rem;
    }
    .qt-batch-state-center {
      display: flex; flex-direction: column; align-items: center; text-align: center;
      justify-content: center; min-height: 50vh; gap: 14px; padding: 2rem 1rem;
    }
    .qt-batch-spinner {
      width: 32px; height: 32px; border-radius: 50%;
      border: 2px solid ${T.border}; border-top-color: ${T.accent};
      animation: qt-batch-spin 0.7s linear infinite;
    }
    @keyframes qt-batch-spin { to { transform: rotate(360deg); } }
    .qt-batch-load-sample {
      background: none; border: none; color: ${T.accent}; font-size: 11px; cursor: pointer;
      font-family: inherit; padding: 0; text-decoration: underline;
    }
  `;
  document.head.appendChild(style);
}

function Nav() {
  return (
    <nav className="qt-batch-nav">
      <Link to="/" className="qt-batch-brand">
        <div className="qt-batch-brand-dot" />
        <span className="qt-batch-brand-name">QueryTuner</span>
      </Link>
      <Link to="/" className="qt-batch-btn qt-batch-btn-ghost">
        ← Back
      </Link>
    </nav>
  );
}

function EvidenceBadge({ level }) {
  const cfg = EVIDENCE[level];
  if (!cfg) return null;
  return (
    <span
      className="qt-batch-chip"
      style={{ background: 'transparent', border: `1px solid ${cfg.color}`, color: cfg.color }}
    >
      {cfg.text}
    </span>
  );
}

function SuggestionCard({ s, footer }) {
  const sevKey = (s.severity || 'low').toLowerCase();
  const sevCfg = SEV[sevKey] || SEV.low;
  return (
    <div className="qt-batch-card">
      <div className="qt-batch-card-top">
        <strong style={{ fontSize: 13 }}>{typeLabel(s.type)}</strong>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <EvidenceBadge level={s.evidence_level} />
          <span className="qt-batch-chip" style={{ background: sevCfg.badge, color: sevCfg.text }}>
            {sevCfg.label}
          </span>
        </div>
      </div>
      <p style={{ fontSize: 13, marginTop: 8 }}>{s.suggestion}</p>
      {s.reason && <p style={{ fontSize: 12, color: T.textMuted, marginTop: 6 }}>{s.reason}</p>}
      {s.cost_estimate && (
        <p style={{ fontSize: 12, color: T.textDim, marginTop: 4 }}>Cost: {s.cost_estimate}</p>
      )}
      {s.ddl_hint && <pre className="qt-batch-ddl">{s.ddl_hint}</pre>}
      {footer}
    </div>
  );
}

export default function BatchAnalysisPage() {
  const { isSignedIn } = useUser();
  const { getToken } = useAuth();

  const [checkingPro, setCheckingPro] = useState(true);
  const [isPro, setIsPro] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  const [source, setSource] = useState('pg_stat_statements');
  const [exportText, setExportText] = useState('');
  const [topN, setTopN] = useState(20);
  const [schemaInfo, setSchemaInfo] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [expandedQuery, setExpandedQuery] = useState(null);

  useEffect(() => {
    injectStyles();
  }, []);

  // Same GET /usage authoritative-Pro-status pattern PricingPage.jsx and
  // HistoryPage.jsx already use — locks the form immediately instead of
  // letting someone type a whole export just to be told "not Pro" on submit.
  useEffect(() => {
    if (isSignedIn === undefined) return;
    if (!isSignedIn) {
      setCheckingPro(false);
      return;
    }
    (async () => {
      try {
        const token = await getToken();
        const r = await axios.get(`${API_URL}/usage`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        setIsPro(!!r.data?.is_pro);
      } catch {
        // Fall back to locked — the actual POST below is still the real
        // gate server-side either way.
      } finally {
        setCheckingPro(false);
      }
    })();
  }, [isSignedIn, getToken]);

  const handleLoadSample = () => {
    setExportText(SOURCES[source].sample);
  };

  const handleAnalyze = async () => {
    if (!exportText.trim()) {
      setError('Paste an export first.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const token = await getToken();
      const r = await axios.post(
        `${API_URL}/analyze/batch`,
        { source, export_text: exportText, top_n: topN, schema_info: schemaInfo || null },
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      setResult(r.data);
    } catch (err) {
      if (err.response?.data?.error === 'pro_required') {
        setIsPro(false);
        setShowUpgradeModal(true);
      } else {
        setError(
          err.response?.data?.detail ||
            err.response?.data?.message ||
            'Failed to analyze this batch. Check the export format and try again.'
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Loading (includes Clerk auth still resolving) ──
  if (checkingPro || isSignedIn === undefined) {
    return (
      <div className="qt-batch">
        <div className="qt-batch-shell">
          <div className="qt-batch-state-center">
            <div className="qt-batch-spinner" />
            <span>Loading…</span>
          </div>
        </div>
      </div>
    );
  }

  // ── Not signed in ──
  if (!isSignedIn) {
    return (
      <div className="qt-batch">
        <div className="qt-batch-shell">
          <Nav />
          <div className="qt-batch-state-center">
            <h1 className="qt-batch-title">Sign in for batch workload analysis</h1>
            <p style={{ color: T.textMuted, fontSize: 13 }}>
              Batch workload analysis is available to signed-in Pro users.
            </p>
            <SignInButton mode="modal">
              <button className="qt-batch-btn qt-batch-btn-primary">Sign in</button>
            </SignInButton>
          </div>
        </div>
      </div>
    );
  }

  // ── Signed in but not Pro — locked state + reusable UpgradeModal pitch ──
  if (!isPro) {
    return (
      <div className="qt-batch">
        <UpgradeModal
          isOpen={showUpgradeModal}
          onClose={() => setShowUpgradeModal(false)}
          title="Batch workload analysis is a Pro feature"
          subtitle="Upgrade to QueryTuner Pro to analyze production query exports."
        />
        <div className="qt-batch-shell">
          <Nav />
          <div className="qt-batch-state-center">
            <span style={{ fontSize: 32 }}>🔒</span>
            <h1 className="qt-batch-title">Batch workload analysis is a Pro feature</h1>
            <p style={{ color: T.textMuted, fontSize: 13, maxWidth: 420 }}>
              Paste a production export (pg_stat_statements, performance_schema, or Query Store) and
              get one reconciled index recommendation set across every query in it — instead of N
              conflicting single-query results.
            </p>
            <button
              className="qt-batch-btn qt-batch-btn-primary"
              onClick={() => setShowUpgradeModal(true)}
            >
              Upgrade to Pro →
            </button>
          </div>
        </div>
      </div>
    );
  }

  const cfg = SOURCES[source];

  return (
    <div className="qt-batch">
      <div className="qt-batch-shell">
        <Nav />
        <h1 className="qt-batch-title">Batch workload analysis</h1>
        <p className="qt-batch-subtitle">
          Paste a production export and get one reconciled index recommendation set across every
          query in it.
        </p>

        <div className="qt-batch-field">
          <label className="qt-batch-label" htmlFor="qt-batch-source">
            Export source
          </label>
          <select
            id="qt-batch-source"
            className="qt-batch-select"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {Object.entries(SOURCES).map(([key, s]) => (
              <option key={key} value={key}>
                {s.label}
              </option>
            ))}
          </select>
          <p className="qt-batch-hint">
            Standard export query for this source:
            <pre className="qt-batch-ddl" style={{ marginTop: 6 }}>
              {cfg.exportQuery}
            </pre>
          </p>
        </div>

        <div className="qt-batch-field">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <label className="qt-batch-label" htmlFor="qt-batch-export" style={{ marginBottom: 0 }}>
              Pasted export (JSON array, CSV, TSV, or a psql/mysql-cli table — auto-detected)
            </label>
            <button type="button" className="qt-batch-load-sample" onClick={handleLoadSample}>
              Load a sample
            </button>
          </div>
          <textarea
            id="qt-batch-export"
            className="qt-batch-textarea"
            style={{ marginTop: 6 }}
            value={exportText}
            onChange={(e) => setExportText(e.target.value)}
            placeholder={`Paste your ${cfg.label} export here…`}
          />
        </div>

        <div className="qt-batch-row">
          <div className="qt-batch-field">
            <label className="qt-batch-label" htmlFor="qt-batch-topn">
              Analyze top N by total time
            </label>
            <input
              id="qt-batch-topn"
              type="number"
              min={1}
              max={100}
              className="qt-batch-input"
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value) || 20)}
            />
          </div>
        </div>

        <div className="qt-batch-field">
          <label className="qt-batch-label" htmlFor="qt-batch-schema">
            Schema DDL (optional — improves reconciled results)
          </label>
          <textarea
            id="qt-batch-schema"
            className="qt-batch-textarea"
            style={{ minHeight: 80 }}
            value={schemaInfo}
            onChange={(e) => setSchemaInfo(e.target.value)}
            placeholder="CREATE TABLE orders (...);"
          />
        </div>

        {error && <div className="qt-batch-error">{error}</div>}

        <button
          className="qt-batch-btn qt-batch-btn-primary"
          onClick={handleAnalyze}
          disabled={submitting}
        >
          {submitting ? 'Analyzing…' : 'Analyze batch'}
        </button>

        {result && (
          <>
            <div className="qt-batch-summary-bar" style={{ marginTop: '2rem' }}>
              <span className="qt-batch-summary-stat">
                Source: <strong>{SOURCES[result.source]?.label || result.source}</strong>
              </span>
              <span className="qt-batch-summary-stat">
                Dialect: <strong>{result.db_type}</strong>
              </span>
              <span className="qt-batch-summary-stat">
                Analyzed: <strong>{result.analyzed_count}</strong> of {result.total_parsed} parsed
              </span>
              <span className="qt-batch-summary-stat">
                Time: <strong>{result.analysis_time_ms.toFixed(0)}ms</strong>
              </span>
            </div>

            {result.warnings?.length > 0 &&
              result.warnings.map((w, i) => (
                <div key={i} className="qt-batch-warning">
                  ⚠ {w}
                </div>
              ))}

            <h2 className="qt-batch-section-title">
              Reconciled index recommendations ({result.reconciled_index_suggestions.length})
            </h2>
            {result.reconciled_index_suggestions.length === 0 ? (
              <p style={{ color: T.textMuted, fontSize: 13 }}>
                No index recommendations across this batch.
              </p>
            ) : (
              result.reconciled_index_suggestions.map((s, i) => (
                <SuggestionCard
                  key={i}
                  s={s}
                  footer={
                    <p style={{ fontSize: 11, color: T.textDim, marginTop: 8 }}>
                      {s.table && <>Table: {s.table} · </>}
                      Applies to quer{s.satisfies_queries?.length === 1 ? 'y' : 'ies'} #
                      {s.satisfies_queries?.map((q) => q + 1).join(', #')}
                    </p>
                  }
                />
              ))
            )}

            {result.dropped_suggestions.length > 0 && (
              <>
                <h2 className="qt-batch-section-title">
                  Redundant suggestions dropped ({result.dropped_suggestions.length})
                </h2>
                {result.dropped_suggestions.map((d, i) => (
                  <div key={i} className="qt-batch-card">
                    <p style={{ fontSize: 13 }}>{d.suggestion}</p>
                    <p style={{ fontSize: 12, color: T.textMuted, marginTop: 6 }}>{d.reason}</p>
                    <p style={{ fontSize: 11, color: T.textDim, marginTop: 6 }}>
                      Superseded by: {d.superseded_by_columns?.join(', ')}
                    </p>
                  </div>
                ))}
              </>
            )}

            {result.column_order_conflicts.length > 0 && (
              <>
                <h2 className="qt-batch-section-title">
                  Column order conflicts ({result.column_order_conflicts.length})
                </h2>
                {result.column_order_conflicts.map((c, i) => (
                  <div key={i} className="qt-batch-card">
                    <p style={{ fontSize: 13 }}>
                      {c.table ? `${c.table}: ` : ''}
                      {c.columns?.join(', ')}
                    </p>
                    {c.variants?.map((v, vi) => (
                      <p key={vi} style={{ fontSize: 12, color: T.textMuted, marginTop: 4 }}>
                        Order ({v.order.join(', ')}) — quer{v.queries.length === 1 ? 'y' : 'ies'} #
                        {v.queries.map((q) => q + 1).join(', #')}
                      </p>
                    ))}
                  </div>
                ))}
              </>
            )}

            <h2 className="qt-batch-section-title">
              Per-query breakdown ({result.queries.length})
            </h2>
            {result.queries.map((q) => {
              const isOpen = expandedQuery === q.index;
              return (
                <div key={q.index} className="qt-batch-query-row">
                  <div
                    className="qt-batch-query-head"
                    onClick={() => setExpandedQuery(isOpen ? null : q.index)}
                  >
                    <span style={{ fontSize: 11, color: T.textDim }}>#{q.index + 1}</span>
                    <span className="qt-batch-query-text">{q.query}</span>
                    {q.calls != null && (
                      <span style={{ fontSize: 11, color: T.textMuted, flexShrink: 0 }}>
                        {q.calls.toLocaleString()} calls
                      </span>
                    )}
                    {q.total_time_ms != null && (
                      <span style={{ fontSize: 11, color: T.textMuted, flexShrink: 0 }}>
                        {q.total_time_ms.toFixed(0)}ms total
                      </span>
                    )}
                    <span style={{ fontSize: 11, color: T.textDim, flexShrink: 0 }}>
                      {q.index_suggestions.length} suggestion
                      {q.index_suggestions.length !== 1 ? 's' : ''}
                    </span>
                    <span style={{ fontSize: 11, color: T.textMuted, flexShrink: 0 }}>
                      {isOpen ? '▲' : '▼'}
                    </span>
                  </div>
                  {isOpen && (
                    <div className="qt-batch-query-body">
                      <pre className="qt-batch-ddl" style={{ marginTop: 10 }}>
                        {q.query}
                      </pre>
                      {q.index_suggestions.length === 0 ? (
                        <p style={{ color: T.textMuted, fontSize: 12, marginTop: 8 }}>
                          No index suggestions for this query.
                        </p>
                      ) : (
                        q.index_suggestions.map((s, i) => <SuggestionCard key={i} s={s} />)
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
