/**
 * ReportPage.jsx — Enterprise-grade shareable analysis report
 * Issue #41 (redesign): Dark theme, matching QueryTuner's #0f172a palette
 *
 * Drop-in replacement for frontend/src/components/ReportPage.jsx
 * All logic is identical — only the visual layer has changed.
 *
 * Fonts loaded via <link> injected on mount:
 *   - IBM Plex Sans (UI text — technical, professional)
 *   - JetBrains Mono (code blocks — developer-native)
 */

import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { trackPageView, trackReportViewed } from '../utils/analytics';
import QueryDiagnosis from './QueryDiagnosis';

const API_URL =
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api');

// ── Design tokens (mirror #0f172a main app palette) ─────────────────────────
const T = {
  bg: '#0f172a', // page background — matches main app
  surface: '#1e293b', // card surface
  surfaceHigh: '#263347', // elevated card / hover
  border: '#2d3f55', // subtle border
  borderBright: '#3b5268', // active / hover border
  text: '#e2e8f0', // primary text
  textMuted: '#7fa3c4', // secondary text
  textDim: '#4a6480', // tertiary / labels
  accent: '#38bdf8', // sky blue — primary accent
  accentDim: '#0ea5e9', // accent hover
  green: '#34d399', // low severity / success
  yellow: '#fbbf24', // medium severity
  orange: '#f97316', // high severity
  red: '#f87171', // critical severity
};

const SEV = {
  critical: { bar: T.red, badge: '#3d1515', badgeText: T.red, label: 'Critical' },
  high: { bar: T.orange, badge: '#3d2210', badgeText: T.orange, label: 'High' },
  medium: { bar: T.yellow, badge: '#3a2c0a', badgeText: T.yellow, label: 'Medium' },
  low: { bar: T.green, badge: '#0d3328', badgeText: T.green, label: 'Low' },
};

// Internal heuristic identifiers -> human-readable titles.
// Mirrors OptimizationSuggestions.jsx so the shared report reads the same
// as the main analysis view instead of leaking raw finding type codes.
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

// Three-tier evidence labels — same tiers/colors as OptimizationSuggestions.jsx.
const EVIDENCE_CONFIG = {
  deterministic: {
    background: 'rgba(56,189,248,0.1)',
    color: '#38bdf8',
    border: '1px solid rgba(56,189,248,0.2)',
    text: 'Deterministic',
  },
  'schema-verified': {
    background: 'rgba(52,211,153,0.1)',
    color: '#34d399',
    border: '1px solid rgba(52,211,153,0.2)',
    text: 'Schema Verified',
  },
  'needs-runtime-evidence': {
    background: 'rgba(251,191,36,0.08)',
    color: '#fbbf24',
    border: '1px solid rgba(251,191,36,0.2)',
    text: 'Estimated',
  },
};

function EvidenceBadge({ level }) {
  const cfg = EVIDENCE_CONFIG[level];
  if (!cfg) return null;
  return (
    <span
      className="qt-chip"
      style={{ background: cfg.background, color: cfg.color, border: cfg.border, fontSize: 10 }}
    >
      {cfg.text}
    </span>
  );
}

// Collapsed by default — rollback DDL is a "break glass" action, not
// something to surface at the same visual weight as the suggestion itself.
function RollbackToggle({ ddl }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          fontSize: 11,
          fontWeight: 500,
          color: T.red,
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
          style={{
            marginTop: 6,
            background: '#0f172a',
            color: T.red,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 12,
            padding: 12,
            borderRadius: 8,
            overflowX: 'auto',
          }}
        >
          {`To undo this index: ${ddl}`}
        </pre>
      )}
    </div>
  );
}

// ── Inject fonts once ────────────────────────────────────────────────────────
function injectFonts() {
  if (document.getElementById('qt-report-fonts')) return;
  const link = document.createElement('link');
  link.id = 'qt-report-fonts';
  link.rel = 'stylesheet';
  link.href =
    'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap';
  document.head.appendChild(link);
}

// ── Global styles injected once ──────────────────────────────────────────────
function injectStyles() {
  if (document.getElementById('qt-report-styles')) return;
  const style = document.createElement('style');
  style.id = 'qt-report-styles';
  style.textContent = `
    .qt-report * { box-sizing: border-box; margin: 0; padding: 0; }
    .qt-report {
      font-family: 'IBM Plex Sans', system-ui, sans-serif;
      background: ${T.bg};
      min-height: 100vh;
      color: ${T.text};
      background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(56,189,248,0.07) 0%, transparent 60%),
        linear-gradient(rgba(56,189,248,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(56,189,248,0.03) 1px, transparent 1px);
      background-size: 100% 100%, 40px 40px, 40px 40px;
    }
    .qt-shell { max-width: 860px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }

    /* Nav bar */
    .qt-nav {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 1.75rem; margin-bottom: 1.75rem;
      border-bottom: 1px solid ${T.border};
    }
    .qt-nav-brand { display: flex; align-items: center; gap: 8px; text-decoration: none; }
    .qt-nav-brand-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: ${T.accent}; box-shadow: 0 0 8px ${T.accent};
    }
    .qt-nav-brand-name {
      font-size: 13px; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; color: ${T.accent};
    }
    .qt-nav-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

    /* Buttons */
    .qt-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 6px; font-size: 12px;
      font-weight: 500; cursor: pointer; transition: all 0.15s;
      font-family: 'IBM Plex Sans', sans-serif; border: none;
      text-decoration: none; white-space: nowrap;
    }
    .qt-btn-ghost {
      background: transparent; border: 1px solid ${T.border};
      color: ${T.textMuted};
    }
    .qt-btn-ghost:hover { border-color: ${T.borderBright}; color: ${T.text}; background: ${T.surfaceHigh}; }
    .qt-btn-ghost.copied { border-color: ${T.green}; color: ${T.green}; }
    .qt-btn-primary {
      background: ${T.accent}; color: #0f172a; font-weight: 600;
    }
    .qt-btn-primary:hover { background: #7dd3fc; }

    /* Header block */
    .qt-header { margin-bottom: 2rem; }
    .qt-header-meta {
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 10px; flex-wrap: wrap;
    }
    .qt-title {
      font-size: 22px; font-weight: 600; color: ${T.text};
      letter-spacing: -0.02em; line-height: 1.3;
    }
    .qt-subtitle { font-size: 13px; color: ${T.textMuted}; margin-top: 4px; }
    .qt-chip {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 3px 10px; border-radius: 20px; font-size: 11px;
      font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .qt-chip-db {
      background: rgba(56,189,248,0.1); color: ${T.accent};
      border: 1px solid rgba(56,189,248,0.2);
    }
    .qt-chip-sev { border: 1px solid transparent; }

    /* Stat strip */
    .qt-stats {
      display: grid; grid-template-columns: repeat(4, 1fr);
      gap: 1px; background: ${T.border};
      border: 1px solid ${T.border}; border-radius: 10px;
      overflow: hidden; margin-bottom: 1.75rem;
    }
    @media(max-width: 600px) { .qt-stats { grid-template-columns: repeat(2,1fr); } }
    .qt-stat {
      background: ${T.surface}; padding: 14px 16px;
      display: flex; flex-direction: column; gap: 4px;
    }
    .qt-stat-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
      color: ${T.textDim}; font-weight: 500;
    }
    .qt-stat-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 14px; font-weight: 500; color: ${T.text};
    }
    .qt-stat-value.accent { color: ${T.accent}; }

    /* Sections */
    .qt-section { margin-bottom: 1.5rem; }
    .qt-section-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;
      color: ${T.textDim}; font-weight: 600; margin-bottom: 8px;
      display: flex; align-items: center; gap: 8px;
    }
    .qt-section-label::after {
      content: ''; flex: 1; height: 1px; background: ${T.border};
    }
    .qt-card {
      background: ${T.surface}; border: 1px solid ${T.border};
      border-radius: 10px; overflow: hidden;
    }

    /* Code blocks */
    .qt-code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px; line-height: 1.7; padding: 16px 20px;
      overflow-x: auto; white-space: pre-wrap; word-break: break-all;
    }
    .qt-code-original { color: #7dd3fc; }
    .qt-code-optimized { color: ${T.green}; }
    .qt-code-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 16px; border-bottom: 1px solid ${T.border};
      background: rgba(0,0,0,0.2);
    }
    .qt-code-lang {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px; color: ${T.textDim}; text-transform: uppercase; letter-spacing: 0.06em;
    }
    .qt-code-dot { width: 6px; height: 6px; border-radius: 50%; }

    /* Findings */
    .qt-findings { display: flex; flex-direction: column; gap: 1px; }
    .qt-finding {
      display: flex; gap: 0;
      background: ${T.surface};
      transition: background 0.12s;
    }
    .qt-finding:first-child { border-radius: 10px 10px 0 0; overflow: hidden; }
    .qt-finding:last-child { border-radius: 0 0 10px 10px; overflow: hidden; }
    .qt-finding:only-child { border-radius: 10px; overflow: hidden; }
    .qt-finding:hover { background: ${T.surfaceHigh}; }
    .qt-finding-bar { width: 3px; flex-shrink: 0; }
    .qt-finding-body { padding: 14px 16px; flex: 1; min-width: 0; }
    .qt-finding-top {
      display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap;
    }
    .qt-finding-type {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em;
      color: ${T.textDim}; font-weight: 500;
      font-family: 'JetBrains Mono', monospace;
    }
    .qt-finding-suggestion { font-size: 13px; color: ${T.text}; font-weight: 500; line-height: 1.5; }
    .qt-finding-reason { font-size: 12px; color: ${T.textMuted}; margin-top: 4px; line-height: 1.5; }
    .qt-finding-impact {
      display: inline-flex; align-items: center; gap-4px;
      margin-top: 6px; font-size: 11px; font-weight: 500;
      font-family: 'JetBrains Mono', monospace; color: ${T.accent};
    }

    /* Footer */
    .qt-footer {
      margin-top: 3rem; padding-top: 1.5rem;
      border-top: 1px solid ${T.border};
      display: flex; align-items: center; justify-content: space-between;
      flex-wrap: wrap; gap: 12px;
    }
    .qt-footer-brand { font-size: 12px; color: ${T.textDim}; }
    .qt-footer-brand a { color: ${T.accent}; text-decoration: none; font-weight: 500; }
    .qt-footer-brand a:hover { text-decoration: underline; }
    .qt-footer-id {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px; color: ${T.textDim}; letter-spacing: 0.04em;
    }

    /* States */
    .qt-spinner {
      width: 32px; height: 32px; border-radius: 50%;
      border: 2px solid ${T.border};
      border-top-color: ${T.accent};
      animation: qt-spin 0.7s linear infinite;
    }
    @keyframes qt-spin { to { transform: rotate(360deg); } }
    .qt-state-center {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; min-height: 60vh; gap: 16px;
    }
    .qt-state-label { font-size: 13px; color: ${T.textMuted}; }

    /* Finding entrance animation */
    @keyframes qt-fadein {
      from { opacity: 0; transform: translateY(6px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .qt-finding { animation: qt-fadein 0.25s ease both; }
  `;
  document.head.appendChild(style);
}

// ── Component ────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    injectFonts();
    injectStyles();
  }, []);

  useEffect(() => {
    if (!id) return;
    const fetchReport = async () => {
      try {
        const { data } = await axios.get(`${API_URL}/report/${id}`);
        setReport(data);
        trackPageView(
          `/report/${id}`,
          `QueryTuner — ${data.db_type?.toUpperCase()} Analysis Report`
        );
        trackReportViewed(id, data.db_type);
        setMetaTag('og:title', document.title);
        setMetaTag(
          'og:description',
          `${data.optimization_suggestions?.length ?? 0} finding(s) · Severity: ${
            data.severity
          } · Readability: ${data.readability_score ?? 'N/A'}`
        );
        setMetaTag('og:url', window.location.href);
      } catch (err) {
        setError(
          err.response?.status === 404
            ? "This report link has expired or doesn't exist."
            : 'Failed to load the report. Please try again.'
        );
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, [id]);

  const handleCopy = () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  // ── Loading ──
  if (loading)
    return (
      <div className="qt-report">
        <div className="qt-shell">
          <div className="qt-state-center">
            <div className="qt-spinner" />
            <span className="qt-state-label">Loading analysis…</span>
          </div>
        </div>
      </div>
    );

  // ── Error ──
  if (error)
    return (
      <div className="qt-report">
        <div className="qt-shell">
          <div className="qt-state-center">
            <span style={{ fontSize: 36 }}>⚠</span>
            <span className="qt-state-label" style={{ color: T.textMuted }}>
              {error}
            </span>
            <a
              href="https://querytuner.com"
              className="qt-btn qt-btn-primary"
              style={{ marginTop: 8 }}
            >
              Analyze a new query →
            </a>
          </div>
        </div>
      </div>
    );

  if (!report) return null;

  const findings = report.optimization_suggestions ?? [];
  const topSev = (report.severity ?? 'low').toLowerCase();
  const sevConfig = SEV[topSev] ?? SEV.low;
  const dbType = report.db_type?.toUpperCase() ?? 'SQL';
  const createdAt = report.created_at
    ? new Date(report.created_at).toLocaleDateString('en-CA', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '—';

  // ── Main render ──
  return (
    <div className="qt-report">
      <div className="qt-shell">
        {/* ── Nav ── */}
        <nav className="qt-nav">
          <a href="https://querytuner.com" className="qt-nav-brand">
            <div className="qt-nav-brand-dot" />
            <span className="qt-nav-brand-name">QueryTuner</span>
          </a>
          <div className="qt-nav-actions">
            <button
              onClick={handleCopy}
              className={`qt-btn qt-btn-ghost ${copied ? 'copied' : ''}`}
            >
              {copied ? (
                <>
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>{' '}
                  Copied
                </>
              ) : (
                <>
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                  </svg>{' '}
                  Share
                </>
              )}
            </button>
            <a href="https://querytuner.com" className="qt-btn qt-btn-primary">
              Analyze your SQL →
            </a>
          </div>
        </nav>

        {/* ── Header ── */}
        <div className="qt-header">
          <div className="qt-header-meta">
            <span className="qt-chip qt-chip-db">{dbType}</span>
            <span
              className="qt-chip qt-chip-sev"
              style={{
                background: sevConfig.badge,
                color: sevConfig.badgeText,
                borderColor: sevConfig.bar + '44',
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: sevConfig.bar,
                  display: 'inline-block',
                  boxShadow: `0 0 6px ${sevConfig.bar}`,
                }}
              />
              {sevConfig.label} severity
            </span>
          </div>
          <h1 className="qt-title">SQL Analysis Report</h1>
          <p className="qt-subtitle">
            {createdAt} · {findings.length} finding{findings.length !== 1 ? 's' : ''} detected
          </p>
        </div>

        {/* ── Stats strip ── */}
        <div className="qt-stats">
          <div className="qt-stat">
            <span className="qt-stat-label">Readability</span>
            <span className={`qt-stat-value ${report.readability_score != null ? 'accent' : ''}`}>
              {report.readability_score != null ? `${report.readability_score}/100` : '—'}
            </span>
          </div>
          <div className="qt-stat">
            <span className="qt-stat-label">Analysis time</span>
            <span className="qt-stat-value">
              {report.analysis_time_ms != null
                ? `${Number(report.analysis_time_ms).toFixed(1)} ms`
                : '—'}
            </span>
          </div>
          <div className="qt-stat">
            <span className="qt-stat-label">Engine</span>
            <span className="qt-stat-value">
              {report.used_ai ? report.ai_model ?? 'AI' : 'Heuristic'}
            </span>
          </div>
          <div className="qt-stat">
            <span className="qt-stat-label">Dialect</span>
            <span className="qt-stat-value accent">{dbType}</span>
          </div>
        </div>

        {/* ── Original query ── */}
        <div className="qt-section">
          <div className="qt-section-label">Original Query</div>
          <div className="qt-card">
            <div className="qt-code-header">
              <span className="qt-code-lang">sql · {dbType}</span>
              <div style={{ display: 'flex', gap: 5 }}>
                <div className="qt-code-dot" style={{ background: T.red }} />
                <div className="qt-code-dot" style={{ background: T.yellow }} />
                <div className="qt-code-dot" style={{ background: T.green }} />
              </div>
            </div>
            <pre className="qt-code qt-code-original">{report.original_query}</pre>
          </div>
        </div>

        {/* ── Query Diagnosis ── */}
        {report.plain_explanation && (
          <div className="qt-section">
            <QueryDiagnosis content={report.plain_explanation} />
          </div>
        )}

        {/* ── Findings ── */}
        <div className="qt-section">
          <div style={{ marginBottom: 10 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: T.accent,
              }}
            >
              Heuristic Analysis
            </div>
            <p style={{ fontSize: 11, color: T.textDim, marginTop: 2 }}>
              Deterministic rules — sub-second, always available
            </p>
          </div>
          <div className="qt-section-label">Findings ({findings.length})</div>
          {findings.length === 0 ? (
            <div
              className="qt-card"
              style={{ padding: '20px 20px', color: T.textMuted, fontSize: 13 }}
            >
              ✓ No issues detected — this query looks clean.
            </div>
          ) : (
            <div className="qt-findings">
              {findings.map((f, i) => {
                const sev = (f.severity ?? 'low').toLowerCase();
                const cfg = SEV[sev] ?? SEV.low;
                return (
                  <div
                    key={i}
                    className="qt-finding"
                    style={{
                      animationDelay: `${i * 60}ms`,
                      borderTop: i > 0 ? `1px solid ${T.border}` : 'none',
                    }}
                  >
                    <div className="qt-finding-bar" style={{ background: cfg.bar }} />
                    <div className="qt-finding-body">
                      <div className="qt-finding-top">
                        <span
                          className="qt-chip qt-chip-sev"
                          style={{
                            background: cfg.badge,
                            color: cfg.badgeText,
                            borderColor: cfg.bar + '44',
                            padding: '2px 8px',
                            fontSize: 10,
                          }}
                        >
                          {cfg.label}
                        </span>
                        <EvidenceBadge level={f.evidence_level} />
                        {f.type && <span className="qt-finding-type">{typeLabel(f.type)}</span>}
                      </div>
                      <p className="qt-finding-suggestion">{f.suggestion}</p>
                      {f.reason && <p className="qt-finding-reason">{f.reason}</p>}
                      {f.estimated_improvement && (
                        <span className="qt-finding-impact">↑ {f.estimated_improvement}</span>
                      )}
                      {f.ddl_hint && (
                        <pre
                          style={{
                            marginTop: 8,
                            background: '#0f172a',
                            color: '#7dd3fc',
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: 12,
                            padding: 12,
                            borderRadius: 8,
                            overflowX: 'auto',
                          }}
                        >
                          {f.ddl_hint}
                        </pre>
                      )}
                      {f.rollback_ddl && <RollbackToggle ddl={f.rollback_ddl} />}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Optimized query ── */}
        {report.optimized_query && (
          <div className="qt-section">
            <div className="qt-section-label">Optimized Query</div>
            <div className="qt-card">
              <div className="qt-code-header">
                <span className="qt-code-lang">sql · rewritten</span>
                <span
                  style={{
                    fontSize: 10,
                    color: T.green,
                    fontFamily: "'JetBrains Mono', monospace",
                    fontWeight: 500,
                  }}
                >
                  ✓ optimized
                </span>
              </div>
              <pre className="qt-code qt-code-optimized">{report.optimized_query}</pre>
            </div>
          </div>
        )}

        {/* ── Footer ── */}
        <div className="qt-footer">
          <span className="qt-footer-brand">
            Generated by <a href="https://querytuner.com">QueryTuner</a> — AI SQL diagnostics across
            5 dialects
          </span>
          <span className="qt-footer-id">ID: {id}</span>
        </div>
        <p
          style={{
            fontSize: 10,
            color: T.textDim,
            marginTop: 6,
            textAlign: 'center',
          }}
        >
          This report is publicly accessible to anyone with this URL and stored indefinitely. Do not
          share queries containing sensitive or production data.
        </p>
      </div>
    </div>
  );
}

// ── Utility ──────────────────────────────────────────────────────────────────

function setMetaTag(property, content) {
  let el = document.querySelector(`meta[property="${property}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute('property', property);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}
