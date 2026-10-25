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

// Rewritten SQL first (it is what people came for); the original sits below,
// collapsed until asked for. Both panes scroll inside a fixed height.
export function RewriteView({
  original,
  rewrite,
  isAi,
  changed,
  aiCutOff,
  onCopyRewrite,
  onCopyOriginal,
}) {
  const [showOriginal, setShowOriginal] = useState(false);
  if (!rewrite) {
    return (
      <div
        className="rounded-xl p-4 text-sm"
        style={{ background: '#1e293b', border: '1px solid #2d3f55', color: '#94a3b8' }}
      >
        No rewrite was produced for this query.
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {aiCutOff && (
        <div
          className="rounded-xl p-3 flex gap-3 items-start text-xs"
          style={{
            background: 'rgba(251,191,36,0.06)',
            border: '1px solid rgba(251,191,36,0.2)',
            color: '#fbbf24',
          }}
        >
          <Zap className="w-4 h-4 flex-shrink-0" />
          <span>
            The AI rewrite was cut off because the query is long, so it is not shown. The
            heuristic rewrite is shown instead — re-run with a shorter query for a full AI rewrite.
          </span>
        </div>
      )}
      <CodePane
        title="Rewritten"
        badge={
          isAi ? '✓ AI rewrite · review before applying' : 'Heuristic rewrite · review before applying'
        }
        badgeColor="#34d399"
        text={rewrite}
        color="#34d399"
        onCopy={onCopyRewrite}
      />
      {changed && <OptimizationComplete />}
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
    </div>
  );
}
