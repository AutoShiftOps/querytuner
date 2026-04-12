import React, { useEffect, useState } from 'react';
import { AlertCircle, Zap, Shield } from 'lucide-react';
import QueryInput from './components/QueryInput';
import ResultsPanel from './components/ResultsPanel';
import OptimizationSuggestions from './components/OptimizationSuggestions';
import ExecutionPlan from './components/ExecutionPlan';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [query, setQuery] = useState('');
  const [dbType, setDbType] = useState('postgresql');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [caps, setCaps] = useState(null);
  const [llmProvider, setLlmProvider] = useState('huggingface');

  // FIX: you must have a setter, otherwise it's always false
  const [useLlm, setUseLlm] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API_BASE_URL}/capabilities`);
        setCaps(r.data);
        setLlmProvider(r.data?.default_provider || 'huggingface');
      } catch (e) {
        // Capabilities is optional; don't block the app
        setCaps(null);
      }
    })();
  }, []);

  const handleAnalyze = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.post(`${API_BASE_URL}/analyze`, {
        query,
        db_type: dbType,
        schema_info: null, // keep if you don’t support schema yet
        llm_provider: llmProvider,
        use_llm: useLlm,
        focus: 'performance',
      });

      setResult(response.data);
    } catch (err) {
      setResult(null);
      setError(err.response?.data?.detail || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Zap className="w-8 h-8 text-blue-400" />
            <h1 className="text-4xl font-bold text-white">SQL Query Analyzer</h1>
          </div>
          <p className="text-slate-400">AI-powered SQL optimization and performance analysis</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Input */}
          <div className="lg:col-span-2">
            <QueryInput
              query={query}
              setQuery={setQuery}
              dbType={dbType}
              setDbType={setDbType}
              onAnalyze={handleAnalyze}
              loading={loading}
              // NEW: pass these so the checkbox can control the flag
              useLlm={useLlm}
              setUseLlm={setUseLlm}
              llmProvider={llmProvider}
              setLlmProvider={setLlmProvider}
              caps={caps}
            />

            {error && (
              <div className="mt-4 p-4 bg-red-900/20 border border-red-500 rounded-lg flex gap-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                <p className="text-red-200">{error}</p>
              </div>
            )}
          </div>

          {/* Right Column - Stats */}
          {result && (
            <div className="space-y-4">
              <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-sm mb-1">Analysis Time</p>
                <p className="text-2xl font-bold text-white">
                  {Number(result.analysis_time_ms || 0).toFixed(2)}ms
                </p>
              </div>

              <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-sm mb-1">Readability Score</p>
                <p className="text-2xl font-bold text-white">
                  {Math.round(Number(result.readability_score || 0))}%
                </p>
              </div>

              <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-sm mb-1">Issues Found</p>
                <p className="text-2xl font-bold text-red-400">
                  {Array.isArray(result.optimization_suggestions) ? result.optimization_suggestions.length : 0}
                </p>
              </div>

              {/* Optional: show whether AI ran */}
              <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-sm mb-1">AI Insights</p>
                <p className="text-sm text-white">
                  {result.used_ai ? `Enabled (${result.ai_provider || 'provider'}${result.ai_model ? ` / ${result.ai_model}` : ''})` : 'Disabled / not used'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Results */}
        {result && (
          <div className="mt-8 space-y-6">
            <OptimizationSuggestions suggestions={result.optimization_suggestions || []} />

            {/* AI panel (shows only when AI returns something or errors) */}
            {(result.used_ai || result.ai_insights || result.ai_error) && (
              <ResultsPanel
                title={`AI Insights${result.ai_provider ? ` (${result.ai_provider}${result.ai_model ? ` / ${result.ai_model}` : ''})` : ''}`}
                content={result.ai_error ? `AI error: ${result.ai_error}` : (result.ai_insights || 'No AI insights returned.')}
                icon={Zap}
              />
            )}

            {result.optimized_query && (
              <ResultsPanel
                title="Optimized Query"
                content={result.optimized_query}
                icon={Zap}
              />
            )}

            {result.execution_plan && <ExecutionPlan plan={result.execution_plan} />}

            {Array.isArray(result.security_issues) && result.security_issues.length > 0 && (
              <div className="bg-red-900/20 border border-red-500 rounded-lg p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Shield className="w-5 h-5 text-red-400" />
                  <h3 className="text-lg font-bold text-white">Security Issues</h3>
                </div>
                <ul className="space-y-2">
                  {result.security_issues.map((issue, idx) => (
                    <li key={idx} className="text-red-200">• {issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
