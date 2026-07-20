import React, { useState } from 'react';

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
  explainPlan, // Issue #60: new prop — raw EXPLAIN output text
  setExplainPlan, // Issue #60: new prop — setter from parent
  schemaDdl, // Issue #8: new prop — raw CREATE TABLE DDL text
  setSchemaDdl, // Issue #8: new prop — setter from parent
}) {
  const openaiEnabled = !!caps?.providers?.openai;
  const hfEnabled = caps?.providers?.huggingface ?? true;
  const anyAiEnabled = hfEnabled || openaiEnabled;

  // Issue #60: collapsed by default — keeps the form uncluttered
  const [explainOpen, setExplainOpen] = useState(false);
  // Issue #8: collapsed by default — same rationale as the EXPLAIN accordion
  const [schemaOpen, setSchemaOpen] = useState(false);

  const onChangeProvider = (next) => {
    setLlmProvider(next);
    if (!useLlm) setUseLlm(true);
  };

  // Issue #60: per-dialect placeholder so users paste in the right format
  const explainPlaceholders = {
    postgresql:
      "Paste output of: EXPLAIN (ANALYZE, BUFFERS) your_query;\n\nExample:\nSeq Scan on orders  (cost=0.00..431.00 rows=10000 width=244)\n  Filter: (status = 'pending'::text)",
    mysql:
      'Paste output of: EXPLAIN FORMAT=JSON your_query;\n\nExample:\n{"query_block": {"table": {"table_name": "orders", "access_type": "ALL", "rows_examined_per_scan": 10000}}}',
    oracle:
      'Paste output of:\nEXPLAIN PLAN FOR your_query;\nSELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);\n\nExample:\n| Id | Operation | Name | Rows |\n| 0 | SELECT STATEMENT | | |\n| 1 |  TABLE ACCESS FULL | ORDERS | 10000 |',
    sqlserver:
      "Paste output of: SET STATISTICS IO, TIME ON;  (or Actual Execution Plan XML from SSMS)\n\nExample:\nTable 'orders'. Scan count 1, logical reads 431",
    sqlite: 'Paste output of: EXPLAIN QUERY PLAN your_query;\n\nExample:\nSCAN TABLE orders',
  };

  const explainHint = {
    postgresql: 'EXPLAIN (ANALYZE, BUFFERS)',
    mysql: 'EXPLAIN FORMAT=JSON',
    oracle: 'DBMS_XPLAN.DISPLAY',
    sqlserver: 'SET STATISTICS IO, TIME ON',
    sqlite: 'EXPLAIN QUERY PLAN',
  };

  // Issue #8: per-dialect CREATE TABLE placeholder so users paste the right syntax
  const schemaPlaceholders = {
    postgresql:
      "CREATE TABLE orders (\n  id SERIAL PRIMARY KEY,\n  customer_id INTEGER NOT NULL,\n  status VARCHAR(20) DEFAULT 'pending',\n  created_at TIMESTAMPTZ DEFAULT NOW()\n);",
    mysql:
      "CREATE TABLE orders (\n  id INT AUTO_INCREMENT PRIMARY KEY,\n  customer_id INT NOT NULL,\n  status VARCHAR(20) DEFAULT 'pending',\n  created_at DATETIME DEFAULT CURRENT_TIMESTAMP\n);",
    oracle:
      "CREATE TABLE orders (\n  id NUMBER PRIMARY KEY,\n  customer_id NUMBER NOT NULL,\n  status VARCHAR2(20) DEFAULT 'pending',\n  created_at TIMESTAMP DEFAULT SYSTIMESTAMP\n);",
    sqlserver:
      "CREATE TABLE orders (\n  id INT IDENTITY(1,1) PRIMARY KEY,\n  customer_id INT NOT NULL,\n  status NVARCHAR(20) DEFAULT 'pending',\n  created_at DATETIME2 DEFAULT GETDATE()\n);",
    sqlite:
      "CREATE TABLE orders (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  customer_id INTEGER NOT NULL,\n  status TEXT DEFAULT 'pending',\n  created_at TEXT DEFAULT CURRENT_TIMESTAMP\n);",
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <label className="block text-sm font-medium text-slate-300 mb-2">SQL Query</label>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full h-40 bg-slate-900 text-white rounded border border-slate-600 p-3 font-mono text-sm"
        placeholder="SELECT * FROM orders WHERE status = 'pending'"
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

      {/* Issue #60: Collapsible EXPLAIN plan section */}
      <div className="mt-4 border-t border-slate-700 pt-4">
        <button
          type="button"
          onClick={() => setExplainOpen((v) => !v)}
          className="flex items-center justify-between w-full text-left group"
        >
          <span className="flex items-center gap-2 text-sm font-medium text-slate-300">
            <ChevronIcon open={explainOpen} />
            EXPLAIN plan
            <span className="text-xs font-normal text-slate-500">
              (optional — paste {explainHint[dbType] || 'EXPLAIN'} output for confirmed analysis)
            </span>
          </span>
          {explainPlan?.trim() && !explainOpen && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                background: 'rgba(52,211,153,0.1)',
                color: '#34d399',
                border: '1px solid rgba(52,211,153,0.3)',
              }}
            >
              ✓ plan attached
            </span>
          )}
        </button>

        {explainOpen && (
          <div className="mt-3">
            <textarea
              value={explainPlan || ''}
              onChange={(e) => setExplainPlan(e.target.value)}
              className="w-full h-32 bg-slate-900 text-white rounded border border-slate-600 p-3 font-mono text-xs leading-relaxed"
              placeholder={explainPlaceholders[dbType] || explainPlaceholders.postgresql}
            />
            <p className="text-xs text-slate-500 mt-2">
              Pasting a real EXPLAIN plan upgrades heuristic findings from{' '}
              <span className="text-amber-400 font-medium">estimated</span> to{' '}
              <span className="text-emerald-400 font-medium">confirmed</span> — QueryTuner
              cross-references your actual execution plan against the parsed query instead of
              guessing from syntax alone.
            </p>
            {explainPlan?.trim() && (
              <button
                type="button"
                onClick={() => setExplainPlan('')}
                className="text-xs text-slate-400 hover:text-red-400 mt-2 underline"
              >
                Clear plan
              </button>
            )}
          </div>
        )}
      </div>

      {/* Issue #8: Collapsible Schema DDL section */}
      <div className="mt-4 border-t border-slate-700 pt-4">
        <button
          type="button"
          onClick={() => setSchemaOpen((v) => !v)}
          className="flex items-center justify-between w-full text-left group"
        >
          <span className="flex items-center gap-2 text-sm font-medium text-slate-300">
            <ChevronIcon open={schemaOpen} />
            Schema DDL
            <span className="text-xs font-normal text-slate-500">
              (optional — paste CREATE TABLE statements for confirmed index recommendations)
            </span>
          </span>
          {schemaDdl?.trim() && !schemaOpen && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                background: 'rgba(56,189,248,0.1)',
                color: '#38bdf8',
                border: '1px solid rgba(56,189,248,0.3)',
              }}
            >
              ✓ schema attached
            </span>
          )}
        </button>

        {schemaOpen && (
          <div className="mt-3">
            <textarea
              value={schemaDdl || ''}
              onChange={(e) => setSchemaDdl(e.target.value)}
              className="w-full h-40 bg-slate-900 text-white rounded border border-slate-600 p-3 font-mono text-xs leading-relaxed"
              placeholder={schemaPlaceholders[dbType] || schemaPlaceholders.postgresql}
            />
            <p className="text-xs text-slate-500 mt-2">
              Providing your schema upgrades index recommendations from{' '}
              <span className="text-amber-400 font-medium">estimated</span> to{' '}
              <span className="font-medium" style={{ color: '#38bdf8' }}>
                confirmed
              </span>
              .
            </p>
            {schemaDdl?.trim() && (
              <button
                type="button"
                onClick={() => setSchemaDdl('')}
                className="text-xs text-slate-400 hover:text-red-400 mt-2 underline"
              >
                Clear schema
              </button>
            )}
          </div>
        )}
      </div>

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

function ChevronIcon({ open }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
        transition: 'transform 0.15s',
      }}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}
