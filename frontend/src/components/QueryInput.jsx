import React, { useState, useEffect, useRef, forwardRef } from 'react';
import { SignInButton } from '@clerk/clerk-react';
import SanitizerPanel from './SanitizerPanel';
import {
  shouldResetStaleOpenAiSelection,
  shouldAutoSelectOpenAiForPro,
} from '../utils/providerSelection';

const QueryInput = forwardRef(function QueryInput(
  {
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
    substitutionMap, // query sanitizer — null when not sanitized, map when active
    setSubstitutionMap, // query sanitizer — setter from parent
    highlightAnalyze, // new prop — whether to highlight the Analyze button
    isSignedIn, // anonymous-AI-gap fix — gates the "Use AI insights" checkbox client-side
    isPro, // Phase 4 audit (#53) fix — gates the OpenAI option client-side
  },
  ref
) {
  // Phase 4 audit (#53): OpenAI is Pro-tier by design — this dropdown
  // used to only check whether the server had an API key configured, not
  // whether the signed-in user was actually Pro, so any free user could
  // select it and the backend (before its own #53 fix) would honor it.
  // The server-side check in main.py's /analyze handler is the
  // authoritative one; this is the client-side half of the same fix, same
  // relationship the "Use AI insights" checkbox already has with its own
  // sign-in gate below.
  const openaiConfigured = !!caps?.providers?.openai;
  const openaiEnabled = openaiConfigured && !!isPro;
  const hfEnabled = caps?.providers?.huggingface ?? true;
  const anyAiEnabled = hfEnabled || openaiEnabled;

  // Bug fix (docs/querytuner-quiz-provider-fixes.md, Bug 2): nothing
  // reconciled llmProvider against openaiEnabled — a stale "openai"
  // selection (from before the #53 Pro-gate shipped, or after Pro status
  // lapses) stayed selected forever, showing a disabled option as the
  // dropdown's current value with no way back. Reset it the moment it's
  // no longer allowed, falling back to the always-available option.
  useEffect(() => {
    if (shouldResetStaleOpenAiSelection(llmProvider, openaiEnabled)) {
      setLlmProvider('huggingface');
    }
  }, [openaiEnabled, llmProvider, setLlmProvider]);

  // Default confirmed Pro users to the recommended provider once, without
  // fighting a deliberate manual choice made afterward (didAutoSelectOpenAi
  // latches after the first auto-select so a Pro user who switches back to
  // Hugging Face stays there on later re-renders). Deliberately keyed only
  // on openaiEnabled — including llmProvider/setLlmProvider would re-run
  // this on every manual dropdown change, which the ref guard alone
  // already prevents from re-firing, but keeping the dep list narrow
  // makes the "runs once when Pro turns on" intent explicit rather than
  // relying on the guard to paper over a broader trigger.
  const didAutoSelectOpenAi = useRef(false);
  useEffect(() => {
    if (shouldAutoSelectOpenAiForPro(llmProvider, openaiEnabled, didAutoSelectOpenAi.current)) {
      didAutoSelectOpenAi.current = true;
      setLlmProvider('openai');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openaiEnabled]);

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
        className={`w-full h-40 bg-slate-900 text-white rounded border p-3 font-mono text-sm ${
          substitutionMap ? 'border-emerald-500' : 'border-slate-600'
        }`}
        placeholder="SELECT * FROM orders WHERE status = 'pending'"
      />

      <SanitizerPanel
        query={query}
        setQuery={setQuery}
        explainPlan={explainPlan}
        setExplainPlan={setExplainPlan}
        substitutionMap={substitutionMap}
        setSubstitutionMap={setSubstitutionMap}
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
              Hugging Face
            </option>
            <option value="openai" disabled={!openaiEnabled}>
              OpenAI (recommended){' '}
              {openaiEnabled ? '' : !openaiConfigured ? '(not enabled on server)' : '(Pro only)'}
            </option>
          </select>
          {!anyAiEnabled && (
            <p className="text-xs text-slate-400 mt-1">AI providers not enabled on server.</p>
          )}
        </div>

        {/* Same label-above-control shape as the Database/AI Provider columns
            beside it (rather than the old bottom-anchored `items-end` row),
            so the checkbox sits at the same vertical position as the two
            selects instead of floating at the bottom of a taller row. */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">AI Insights</label>
          {isSignedIn ? (
            <label className="w-full bg-slate-900 text-slate-300 rounded border border-slate-600 p-2 flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={useLlm}
                disabled={!anyAiEnabled}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="w-4 h-4 accent-qt-accent disabled:opacity-50"
              />
              Use AI insights
            </label>
          ) : (
            // Anonymous callers can't reach the AI path server-side (the
            // OpenAI-backed call requires sign-in — see backend/app/main.py's
            // /analyze anonymous gate). Telling them that only after they've
            // checked the box and clicked Analyze is a dead end, so the
            // checkbox is disabled up front and this row doubles as the
            // sign-in trigger — same SignInButton pattern Header.jsx uses for
            // the header's "Sign in" button, just wrapping this row instead
            // of a <button>. Deliberately a <span>, not a <label>: a <label>
            // whose associated control is disabled is treated as
            // non-interactive for clicks by Chromium (verified — clicking it
            // silently did nothing, no modal), which would've made this
            // whole "click to sign in" affordance dead on arrival. A plain
            // span has no such control-forwarding relationship, so the row
            // stays genuinely clickable. The inline notice in App.jsx stays
            // as a fallback for any state where this client-side gate is
            // bypassed or out of sync — the backend check is the one that's
            // authoritative.
            <SignInButton mode="modal">
              <span
                className="w-full bg-slate-900 text-slate-400 rounded border border-slate-700 p-2 flex items-center gap-2 text-sm cursor-pointer hover:text-slate-300 hover:border-slate-600"
                title="Sign in to use AI insights"
              >
                <input
                  type="checkbox"
                  checked={false}
                  disabled
                  readOnly
                  className="w-4 h-4 accent-qt-accent opacity-50"
                />
                Use AI insights <span className="text-slate-500">(sign in required)</span>
              </span>
            </SignInButton>
          )}
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
              (optional — paste {explainHint[dbType] || 'EXPLAIN'} output for schema-verified
              analysis)
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
              <span className="text-emerald-400 font-medium">schema-verified</span> — QueryTuner
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
              (optional — paste CREATE TABLE statements for schema-verified index recommendations)
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
                schema-verified
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
        ref={ref}
        onClick={onAnalyze}
        disabled={loading || !query.trim()}
        className={`mt-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white px-6 py-2 rounded font-medium transition-all ${
          highlightAnalyze ? 'ring-4 ring-blue-400 animate-pulse' : ''
        }`}
      >
        {loading ? 'Analyzing...' : 'Analyze'}
      </button>
    </div>
  );
});

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

export default QueryInput;
