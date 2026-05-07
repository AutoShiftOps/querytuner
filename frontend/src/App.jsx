import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import ShareButton from './components/ShareButton';
import { BookOpen, AlertCircle, Zap, Shield } from 'lucide-react';
import QueryInput from './components/QueryInput';
import ResultsPanel from './components/ResultsPanel';
import OptimizationSuggestions from './components/OptimizationSuggestions';
import ExecutionPlan from './components/ExecutionPlan';
import SampleQueries from './components/SampleQueries';
import Header from './components/Header';
import Hero from './components/Hero';
import Footer from './components/Footer';
import { ToastContainer, useToast } from './components/Toast';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [query, setQuery] = useState('');
  const [dbType, setDbType] = useState('postgresql');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [caps, setCaps] = useState(null);
  const [llmProvider, setLlmProvider] = useState('huggingface');
  const [useLlm, setUseLlm] = useState(false);
  const { toasts, showToast, dismissToast } = useToast();

  // ── Cmd/Ctrl + Enter shortcut ───────────────────────────────────────────
  useEffect(() => {
    const handleKeydown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleAnalyze();
      }
    };
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  }, []);

  // ── AI toggle toast ─────────────────────────────────────────────────────
  useEffect(() => {
    if (useLlm) showToast('AI insights enabled', 'info');
  }, [useLlm]);

  // ── Fetch backend capabilities ──────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API_BASE_URL}/capabilities`);
        setCaps(r.data);
        setLlmProvider(r.data?.default_provider || 'huggingface');
      } catch {
        setCaps(null);
      }
    })();
  }, []);

  // ── Analyze ─────────────────────────────────────────────────────────────
  const handleAnalyze = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.post(`${API_BASE_URL}/analyze`, {
        query,
        db_type: dbType,
        schema_info: null,
        llm_provider: llmProvider,
        use_llm: useLlm,
        focus: 'performance',
      });
      setResult(response.data);
      showToast('Analysis complete · share link ready', 'success');
    } catch (err) {
      setResult(null);
      setError(err.response?.data?.detail || 'Analysis failed');
      showToast('Analysis failed — please check your query', 'error');
    } finally {
      setLoading(false);
    }
  };

  // ── Derived values ───────────────────────────────────────────────────────
  const issueCount = Array.isArray(result?.optimization_suggestions)
    ? result.optimization_suggestions.length
    : 0;

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: '#0f172a' }} // flat — matches Header, Hero, Footer, ReportPage
    >
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      <Header />
      <Hero />

      {/* ── Main two-column grid ── */}
      <div className="flex-grow w-full mx-auto px-4 py-8" style={{ maxWidth: 1280 }}>
        <div
          className="grid gap-6"
          style={{
            gridTemplateColumns: result ? '1fr 1fr' : '1fr',
            alignItems: 'start',
          }}
        >
          {/* ── LEFT COLUMN — always visible ── */}
          <div className="space-y-4 min-w-0">
            <SampleQueries
              onSelect={(sql, db) => {
                setQuery(sql);
                setDbType(db);
              }}
            />
            <QueryInput
              query={query}
              setQuery={setQuery}
              dbType={dbType}
              setDbType={setDbType}
              onAnalyze={handleAnalyze}
              loading={loading}
              useLlm={useLlm}
              setUseLlm={setUseLlm}
              llmProvider={llmProvider}
              setLlmProvider={setLlmProvider}
              caps={caps}
            />
            {error && (
              <div className="p-4 bg-red-900/20 border border-red-500 rounded-lg flex gap-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-red-200 text-sm">{error}</p>
              </div>
            )}
          </div>

          {/* ── RIGHT COLUMN — appears only after analysis ── */}
          {result && (
            <div className="space-y-4 min-w-0">
              {/* Stat strip */}
              <div
                className="grid grid-cols-4 rounded-xl overflow-hidden"
                style={{
                  gap: 1,
                  background: '#2d3f55',
                  border: '1px solid #2d3f55',
                }}
              >
                {[
                  {
                    label: 'Analysis time',
                    value: `${Number(result.analysis_time_ms || 0).toFixed(1)}ms`,
                  },
                  {
                    label: 'Readability',
                    value: `${Math.round(Number(result.readability_score || 0))}/100`,
                  },
                  { label: 'Issues', value: issueCount, danger: issueCount > 0 },
                  {
                    label: 'Engine',
                    value: result.used_ai ? result.ai_provider || 'AI' : 'Heuristic',
                  },
                ].map(({ label, value, danger }) => (
                  <div
                    key={label}
                    className="flex flex-col gap-1 px-3 py-3"
                    style={{ background: '#1e293b' }}
                  >
                    <span
                      className="text-xs font-medium uppercase tracking-wider"
                      style={{ fontSize: 9, color: '#4a6480', letterSpacing: '0.08em' }}
                    >
                      {label}
                    </span>
                    <span
                      className="font-mono font-medium text-sm"
                      style={{ color: danger ? '#f87171' : '#38bdf8' }}
                    >
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Share button */}
              <div className="flex justify-end">
                <ShareButton
                  analysisId={result.analysis_id}
                  onShare={() => showToast('Share link copied to clipboard', 'success')}
                />
              </div>

              {/* Query Diagnosis */}
              {result.plain_explanation && (
                <div
                  className="rounded-xl p-5"
                  style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <BookOpen className="w-4 h-4 text-blue-400" />
                    <h3 className="font-semibold text-white text-sm">Query Diagnosis</h3>
                  </div>
                  <div className="prose prose-invert prose-sm max-w-none text-slate-300">
                    <ReactMarkdown>{result.plain_explanation}</ReactMarkdown>
                  </div>
                </div>
              )}

              {/* Optimization findings */}
              <OptimizationSuggestions suggestions={result.optimization_suggestions || []} />

              {/* AI Insights */}
              {(result.used_ai || result.ai_insights || result.ai_error) && (
                <ResultsPanel
                  title={`AI Insights${
                    result.ai_provider
                      ? ` (${result.ai_provider}${result.ai_model ? ` / ${result.ai_model}` : ''})`
                      : ''
                  }`}
                  content={
                    result.ai_error
                      ? `AI error: ${result.ai_error}`
                      : result.ai_insights || 'No AI insights returned.'
                  }
                  icon={Zap}
                  onShare={() => {
                    navigator.clipboard.writeText(result.ai_insights || '');
                    showToast('AI insights copied to clipboard', 'success');
                  }}
                />
              )}

              {/* Optimized Query */}
              {result.optimized_query && (
                <div
                  className="rounded-xl overflow-hidden"
                  style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
                >
                  <div
                    className="flex items-center justify-between px-4 py-2"
                    style={{ background: 'rgba(0,0,0,0.25)', borderBottom: '1px solid #2d3f55' }}
                  >
                    <div className="flex items-center gap-2">
                      <Zap className="w-4 h-4 text-blue-400" />
                      <span className="text-sm font-semibold text-white">Optimized Query</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        style={{
                          fontSize: 10,
                          color: '#34d399',
                          fontFamily: 'monospace',
                          fontWeight: 500,
                        }}
                      >
                        ✓ rewritten
                      </span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(result.optimized_query);
                          showToast('Optimized query copied', 'success');
                        }}
                        className="text-xs text-slate-400 hover:text-white border border-slate-600
                                   hover:border-slate-400 px-3 py-1 rounded transition-colors"
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                  <pre
                    className="whitespace-pre-wrap text-sm leading-relaxed overflow-x-auto p-4"
                    style={{ color: '#34d399', fontFamily: "'JetBrains Mono', monospace" }}
                  >
                    {result.optimized_query}
                  </pre>
                </div>
              )}

              {/* Execution Plan */}
              {result.execution_plan && <ExecutionPlan plan={result.execution_plan} />}

              {/* Security Issues */}
              {Array.isArray(result.security_issues) && result.security_issues.length > 0 && (
                <div
                  className="rounded-xl p-5"
                  style={{
                    background: 'rgba(248,113,113,0.06)',
                    border: '1px solid rgba(248,113,113,0.3)',
                  }}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="w-4 h-4 text-red-400" />
                    <h3 className="text-sm font-semibold text-white">Security Issues</h3>
                  </div>
                  <ul className="space-y-2">
                    {result.security_issues.map((issue, idx) => (
                      <li key={idx} className="text-sm text-red-200 flex gap-2">
                        <span style={{ color: '#f87171' }}>·</span>
                        {issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Empty state — shown before first analysis */}
        {!result && !loading && (
          <div className="mt-12 text-center" style={{ color: '#4a6480' }}>
            <p className="text-sm">
              Paste a query above and press{' '}
              <kbd
                className="px-2 py-0.5 rounded text-xs font-mono"
                style={{ background: '#1e293b', border: '1px solid #2d3f55', color: '#7fa3c4' }}
              >
                ⌘ Enter
              </kbd>{' '}
              to analyze
            </p>
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}

export default App;
