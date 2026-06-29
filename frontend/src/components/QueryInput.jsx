import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export default function QueryInput({
  query,
  setQuery,
  dbType,
  setDbType,
  llmProvider,
  setLlmProvider,
  useLlm,
  setUseLlm,
  onAnalyze,
  loading,
  caps,
  explainPlan = '', // Issue #60
  setExplainPlan = () => {}, // Issue #60
}) {
  const [explainOpen, setExplainOpen] = useState(false); // Issue #60: collapsed by default

  const openaiEnabled = !!caps?.providers?.openai;
  const hfEnabled = caps?.providers?.huggingface ?? true;
  const anyAiEnabled = hfEnabled || openaiEnabled;

  const onChangeProvider = (next) => {
    setLlmProvider(next);
    if (!useLlm) setUseLlm(true);
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      {/* ── SQL Query textarea ── */}
      <label className="block text-sm font-medium text-slate-300 mb-2">SQL Query</label>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Paste your SQL query here..."
        className="w-full h-40 bg-slate-900 text-white rounded border border-slate-600 p-3 font-mono text-sm resize-y focus:outline-none focus:border-sky-500"
      />

      {/* ── Issue #60: Collapsible EXPLAIN plan textarea ── */}
      <div className="mt-3">
        <button
          type="button"
          onClick={() => setExplainOpen((o) => !o)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-sky-400 transition-colors"
        >
          {explainOpen ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
          {explainOpen ? 'Hide EXPLAIN plan' : 'Add EXPLAIN plan output (optional)'}
        </button>

        {explainOpen && (
          <div className="mt-2">
            <p className="text-xs text-slate-500 mb-1.5">
              Paste the raw output of{' '}
              <code className="bg-slate-900 px-1 py-0.5 rounded text-sky-400 text-xs">
                EXPLAIN ANALYZE
              </code>{' '}
              (PostgreSQL),{' '}
              <code className="bg-slate-900 px-1 py-0.5 rounded text-sky-400 text-xs">
                EXPLAIN FORMAT=JSON
              </code>{' '}
              (MySQL), or your dialect''s equivalent. This gives the AI layer concrete cost data to
              work with.
            </p>
            <textarea
              value={explainPlan}
              onChange={(e) => setExplainPlan(e.target.value)}
              placeholder="Paste EXPLAIN / EXPLAIN ANALYZE output here..."
              rows={6}
              className="w-full bg-slate-900 text-emerald-300 rounded border border-slate-600 p-3 font-mono text-xs resize-y focus:outline-none focus:border-sky-500"
            />
            {explainPlan && (
              <div className="flex justify-end mt-1">
                <button
                  type="button"
                  onClick={() => setExplainPlan('')}
                  className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                >
                  Clear
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Controls row ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">Database</label>
          <select
            value={dbType}
            onChange={(e) => setDbType(e.target.value)}
            className="w-full bg-slate-900 text-white rounded border border-slate-600 p-2"
          >
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
            <option value="sqlserver">SQL Server</option>
            <option value="oracle">Oracle</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">AI Provider</label>
          <select
            value={llmProvider}
            onChange={(e) => onChangeProvider(e.target.value)}
            disabled={!anyAiEnabled}
            className="w-full bg-slate-900 text-white rounded border border-slate-600 p-2 disabled:opacity-50"
          >
            <option value="huggingface" disabled={!hfEnabled}>
              Hugging Face (default)
            </option>
            <option value="openai" disabled={!openaiEnabled}>
              OpenAI {openaiEnabled ? '' : '(not enabled on server)'}
            </option>
          </select>
          {!anyAiEnabled && (
            <p className="text-xs text-slate-400 mt-1">AI providers not enabled on server.</p>
          )}
        </div>

        <div className="flex items-end gap-3">
          <label className="text-slate-300 text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={useLlm}
              disabled={!anyAiEnabled}
              onChange={(e) => setUseLlm(e.target.checked)}
            />
            Use AI insights
          </label>
        </div>
      </div>

      {/* ── Analyze button ── */}
      <button
        onClick={onAnalyze}
        disabled={loading || !query.trim()}
        className="mt-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white px-6 py-2 rounded font-medium"
      >
        {loading ? 'Analyzing...' : 'Analyze'}
      </button>
    </div>
  );
}
