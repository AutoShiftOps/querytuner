/**
 * ReportPage.jsx — Shareable read-only analysis report
 * Issue #41: GET /report/:id frontend route
 *
 * Place at: frontend/src/components/ReportPage.jsx
 *
 * Then add to your router in App.js:
 *   import ReportPage from './components/ReportPage';
 *   // inside your Routes:
 *   <Route path="/report/:id" element={<ReportPage />} />
 *
 * If you're not using React Router yet, install it:
 *   npm install react-router-dom
 * And wrap App.js content in <BrowserRouter> if not already done.
 */

import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const SEVERITY_STYLES = {
  critical: 'bg-red-100 text-red-800 border border-red-200',
  high: 'bg-orange-100 text-orange-800 border border-orange-200',
  medium: 'bg-yellow-100 text-yellow-800 border border-yellow-200',
  low: 'bg-green-100 text-green-800 border border-green-200',
};

const SEVERITY_DOT = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

export default function ReportPage() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  // ── Fetch report ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;

    const fetchReport = async () => {
      try {
        const { data } = await axios.get(`${API_URL}/report/${id}`);
        setReport(data);

        // Set Open Graph meta tags dynamically for link previews
        document.title = `QueryTuner — ${data.db_type?.toUpperCase()} Analysis Report`;
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

  // ── Copy share URL ────────────────────────────────────────────────────────
  const handleCopy = () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // ── States ────────────────────────────────────────────────────────────────
  if (loading)
    return (
      <PageShell>
        <LoadingSpinner />
      </PageShell>
    );
  if (error)
    return (
      <PageShell>
        <ErrorCard message={error} />
      </PageShell>
    );
  if (!report) return null;

  const findings = report.optimization_suggestions ?? [];
  const topSeverity = report.severity ?? 'low';

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <PageShell>
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <img
              src="/logo.svg"
              alt="QueryTuner"
              className="h-6 w-6"
              onError={(e) => (e.target.style.display = 'none')}
            />
            <span className="text-sm font-medium text-gray-500">QueryTuner</span>
          </div>
          <h1 className="text-xl font-semibold text-gray-900">SQL Analysis Report</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {report.db_type?.toUpperCase()} ·{' '}
            {new Date(report.created_at).toLocaleDateString('en-CA', {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              SEVERITY_STYLES[topSeverity] ?? SEVERITY_STYLES.low
            }`}
          >
            {topSeverity.charAt(0).toUpperCase() + topSeverity.slice(1)} severity
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors shadow-sm"
          >
            {copied ? '✓ Copied!' : '🔗 Copy link'}
          </button>
          <a
            href="https://querytuner.com"
            className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
          >
            Analyze your SQL →
          </a>
        </div>
      </div>

      {/* ── Original Query ── */}
      <Section title="Original Query">
        <pre className="bg-gray-900 text-green-300 text-sm rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
          {report.original_query}
        </pre>
      </Section>

      {/* ── Findings ── */}
      <Section title={`Findings (${findings.length})`}>
        {findings.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No issues detected.</p>
        ) : (
          <ul className="space-y-3">
            {findings.map((f, i) => {
              const sev = (f.severity ?? 'low').toLowerCase();
              return (
                <li
                  key={i}
                  className={`rounded-lg p-4 ${SEVERITY_STYLES[sev] ?? SEVERITY_STYLES.low}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        SEVERITY_DOT[sev] ?? SEVERITY_DOT.low
                      }`}
                    />
                    <span className="text-xs font-semibold uppercase tracking-wide opacity-70">
                      {sev} · {f.type ?? 'finding'}
                    </span>
                  </div>
                  <p className="text-sm font-medium">{f.suggestion}</p>
                  {f.reason && <p className="text-xs mt-1 opacity-80">{f.reason}</p>}
                  {f.estimated_improvement && (
                    <p className="text-xs mt-1 font-medium opacity-70">
                      Impact: {f.estimated_improvement}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* ── Optimized Query ── */}
      {report.optimized_query && (
        <Section title="Optimized Query">
          <pre className="bg-gray-900 text-cyan-300 text-sm rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
            {report.optimized_query}
          </pre>
        </Section>
      )}

      {/* ── Stats row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
        <StatCard
          label="Readability"
          value={report.readability_score != null ? `${report.readability_score}/100` : '—'}
        />
        <StatCard
          label="Analysis time"
          value={report.analysis_time_ms != null ? `${report.analysis_time_ms.toFixed(1)} ms` : '—'}
        />
        <StatCard
          label="AI used"
          value={report.used_ai ? report.ai_model ?? 'Yes' : 'No (heuristics)'}
        />
        <StatCard label="DB dialect" value={report.db_type ?? '—'} />
      </div>

      {/* ── Footer CTA ── */}
      <div className="mt-8 text-center text-sm text-gray-400">
        Generated by{' '}
        <a href="https://querytuner.com" className="text-indigo-500 hover:underline font-medium">
          QueryTuner
        </a>{' '}
        — AI-powered SQL diagnostics across 5 database dialects
      </div>
    </PageShell>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function PageShell({ children }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-10">{children}</div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mb-5">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">{title}</h2>
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">{children}</div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm text-center">
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-gray-800 truncate" title={value}>
        {value}
      </p>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-gray-400">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      <p className="text-sm">Loading report…</p>
    </div>
  );
}

function ErrorCard({ message }) {
  return (
    <div className="text-center py-24">
      <p className="text-4xl mb-3">🔍</p>
      <p className="text-gray-700 font-medium mb-1">Report not found</p>
      <p className="text-sm text-gray-400 mb-6">{message}</p>
      <a
        href="https://querytuner.com"
        className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
      >
        Analyze a new query →
      </a>
    </div>
  );
}

// ── Utility ────────────────────────────────────────────────────────────────

function setMetaTag(property, content) {
  let el = document.querySelector(`meta[property="${property}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute('property', property);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}
