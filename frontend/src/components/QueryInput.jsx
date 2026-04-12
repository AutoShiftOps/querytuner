import React from "react";

export default function QueryInput({
  query, setQuery,
  dbType, setDbType,
  llmProvider, setLlmProvider,
  useLlm, setUseLlm,
  onAnalyze, loading,
  caps
}) {
  const openaiEnabled = !!caps?.providers?.openai;
  const hfEnabled = caps?.providers?.huggingface ?? true; // assume true if server doesn’t report
  const anyAiEnabled = hfEnabled || openaiEnabled;

  const onChangeProvider = (next) => {
    setLlmProvider(next);
    // Optional UX: if user chooses a provider, they probably want AI on
    if (!useLlm) setUseLlm(true);
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <label className="block text-sm font-medium text-slate-300 mb-2">SQL Query</label>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full h-40 bg-slate-900 text-white rounded border border-slate-600 p-3 font-mono text-sm"
      />

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
            <option value="huggingface" disabled={!hfEnabled}>Hugging Face (default)</option>
            <option value="openai" disabled={!openaiEnabled}>
              OpenAI {openaiEnabled ? "" : "(not enabled on server)"}
            </option>
          </select>
          {!anyAiEnabled && (
            <p className="text-xs text-slate-400 mt-1">
              AI providers not enabled on server.
            </p>
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

      <button
        onClick={onAnalyze}
        disabled={loading || !query.trim()}
        className="mt-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white px-6 py-2 rounded font-medium"
      >
        {loading ? "Analyzing..." : "Analyze"}
      </button>
    </div>
  );
}
