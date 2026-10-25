import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import OptimizationComplete from './OptimizationComplete';

// Tab bar for the result sections. Each tab: { id, label, count?, hidden? }.
export function ResultTabs({ tabs, active, onChange }) {
  const visible = tabs.filter((t) => !t.hidden);
  return (
    <div
      role="tablist"
      aria-label="Result sections"
      className="flex gap-1 overflow-x-auto overflow-y-hidden"
      style={{ borderBottom: '1px solid #2d3f55' }}
    >
      {visible.map((t) => {
        const selected = t.id === active;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`result-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`result-panel-${t.id}`}
            onClick={() => onChange(t.id)}
            className="px-4 py-2.5 text-sm whitespace-nowrap transition-colors rounded-t-lg hover:text-white"
            style={{
              color: selected ? '#ffffff' : '#7fa3c4',
              fontWeight: selected ? 600 : 500,
              background: selected ? 'rgba(56,189,248,0.14)' : 'transparent',
              borderBottom: selected ? '3px solid #38bdf8' : '3px solid transparent',
              marginBottom: -1,
            }}
          >
            {t.label}
            {t.count != null && (
              <span
                className="ml-2 text-xs px-1.5 py-0.5 rounded-full"
                style={{
                  background: selected ? 'rgba(56,189,248,0.15)' : 'rgba(127,163,196,0.12)',
                  color: selected ? '#38bdf8' : '#7fa3c4',
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, children }) {
  return (
    <div role="tabpanel" id={`result-panel-${id}`} aria-labelledby={`result-tab-${id}`}>
      {children}
    </div>
  );
}

// Amber callout for AI output that was held back, with the reason and a next step.
export function AiNote({ title, children }) {
  return (
    <div
      role="status"
      className="rounded-lg p-3 flex gap-3 items-start"
      style={{
        background: 'rgba(251,191,36,0.08)',
        border: '1px solid rgba(251,191,36,0.3)',
      }}
    >
      <Zap className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#fbbf24' }} />
      <div className="text-sm">
        <p className="font-semibold" style={{ color: '#fbbf24' }}>
          {title}
        </p>
        <p className="mt-1" style={{ color: '#cbd5e1' }}>
          {children}
        </p>
      </div>
    </div>
  );
}

// Shown when the AI reply hit its length limit while writing the rewrite.
export function AiCutOffNote({ extra }) {
  return (
    <AiNote title="AI rewrite incomplete — the reply hit its length limit">
      {extra ? `${extra} ` : ''}For a full rewrite, analyze a smaller piece — for example the main
      SELECT on its own, without any DECLARE or temp-table setup around it.
    </AiNote>
  );
}

// Shown when the backend refused the AI's full rewrite (dropped a table or
// column, or broken syntax).
export function AiRejectedNote({ reason, extra }) {
  return (
    <AiNote title="AI rewrite not shown — it would change your results">
      The model&apos;s rewrite was held back because {reason}. {extra || ''}
    </AiNote>
  );
}

// Before -> after snippets for long queries and batches.
export function TargetedFixList({ fixes }) {
  if (!fixes || fixes.length === 0) return null;
  return (
    <div className="space-y-3">
      {fixes.map((f, i) => (
        <div
          key={i}
          className="rounded-xl overflow-hidden"
          style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
        >
          <div className="px-4 py-3" style={{ borderBottom: '1px solid #2d3f55' }}>
            <p className="text-sm font-semibold text-white">
              {i + 1}. {f.title || 'Suggested change'}
            </p>
            {f.why && (
              <p className="text-sm mt-1" style={{ color: '#94a3b8' }}>
                {f.why}
              </p>
            )}
          </div>
          <FixSnippet label="Before" text={f.before} color="#cbd5e1" />
          <FixSnippet label="After" text={f.after} color="#34d399" copy />
        </div>
      ))}
    </div>
  );
}

function FixSnippet({ label, text, color, copy }) {
  return (
    <div className="px-4 py-3" style={{ borderTop: '1px solid #233247' }}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs uppercase tracking-wider" style={{ color: '#4a6480' }}>
          {label}
        </span>
        {copy && (
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(text)}
            className="text-xs text-slate-400 hover:text-white border border-slate-600 hover:border-slate-400 px-2 py-0.5 rounded transition-colors"
          >
            Copy
          </button>
        )}
      </div>
      <pre
        className="whitespace-pre-wrap break-words text-xs leading-relaxed overflow-auto rounded p-3"
        style={{
          background: '#0f172a',
          color,
          fontFamily: "'JetBrains Mono', monospace",
          maxHeight: '16rem',
        }}
      >
        {text}
      </pre>
    </div>
  );
}

// A code pane with a fixed height that scrolls inside itself, so a long query
// never stretches the page. "Expand" shows it in full.
function CodePane({ title, badge, badgeColor, text, color, onCopy }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="rounded-xl overflow-hidden flex flex-col min-w-0"
      style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
    >
      <div
        className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-2"
        style={{ background: 'rgba(0,0,0,0.25)', borderBottom: '1px solid #2d3f55' }}
      >
        <div className="flex flex-wrap items-center gap-x-3 min-w-0">
          <span className="text-sm font-semibold text-white">{title}</span>
          {badge && (
            <span className="text-xs" style={{ color: badgeColor, fontFamily: 'monospace' }}>
              {badge}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="text-xs text-slate-400 hover:text-white px-2 py-1"
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
          <button
            type="button"
            onClick={onCopy}
            className="text-xs text-slate-400 hover:text-white border border-slate-600 hover:border-slate-400 px-3 py-1 rounded transition-colors"
          >
            Copy
          </button>
        </div>
      </div>
      <pre
        className="whitespace-pre-wrap break-words text-sm leading-relaxed overflow-auto p-4"
        style={{
          color,
          fontFamily: "'JetBrains Mono', monospace",
          maxHeight: expanded ? 'none' : '26rem',
        }}
      >
        {text}
      </pre>
    </div>
  );
}

// Rewrite tab: the AI's targeted fixes (long queries/batches) or its full
// rewrite when it passed the backend checks, else the safe rule-based
// rewrite, else an explanation. The original query sits below, collapsed.
export function RewriteView({
  original,
  rewrite,
  isAi,
  changed,
  aiCutOff,
  aiRejected,
  aiFixes,
  aiEnabled,
  onCopyRewrite,
  onCopyOriginal,
}) {
  const [showOriginal, setShowOriginal] = useState(false);
  const fixes = aiFixes || [];
  const fallback = rewrite ? 'The safe rewrite is shown below instead.' : '';

  return (
    <div className="space-y-4">
      {aiCutOff && <AiCutOffNote extra={fallback} />}
      {aiRejected && <AiRejectedNote reason={aiRejected} extra={fallback} />}

      {fixes.length > 0 && (
        <div className="space-y-3">
          <div>
            <p className="text-sm font-semibold text-white">AI targeted fixes</p>
            <p className="text-xs mt-0.5" style={{ color: '#7fa3c4' }}>
              Each change is shown on its own so you can apply and test it separately. Review before
              applying.
            </p>
          </div>
          <TargetedFixList fixes={fixes} />
        </div>
      )}

      {rewrite ? (
        <CodePane
          title="Rewritten"
          badge={
            isAi
              ? '✓ AI rewrite · review before applying'
              : 'Safe rewrite · same results · review before applying'
          }
          badgeColor="#34d399"
          text={rewrite}
          color="#34d399"
          onCopy={onCopyRewrite}
        />
      ) : (
        fixes.length === 0 && (
          <div
            className="rounded-xl p-4 text-sm"
            style={{ background: '#1e293b', border: '1px solid #2d3f55', color: '#94a3b8' }}
          >
            <p className="font-semibold text-white">No safe automatic rewrite for this query</p>
            <p className="mt-1">
              QueryTuner only rewrites SQL when the result is guaranteed to stay the same. The
              Findings tab lists what to change by hand.
              {!aiEnabled ? ' Enable "Use AI insights" and run again for AI fixes.' : ''}
            </p>
          </div>
        )
      )}
      {changed && <OptimizationComplete />}

      {original && (
        <>
          <button
            type="button"
            onClick={() => setShowOriginal((o) => !o)}
            aria-expanded={showOriginal}
            className="text-sm"
            style={{ color: '#7fa3c4' }}
          >
            {showOriginal ? '▾ Hide original query' : '▸ Compare with original query'}
          </button>
          {showOriginal && (
            <CodePane title="Original" text={original} color="#cbd5e1" onCopy={onCopyOriginal} />
          )}
        </>
      )}
    </div>
  );
}
