import React, { useState } from 'react';
import {
  extractIdentifiers,
  buildSubstitutionMap,
  sanitize,
  desanitize,
  buildDiff,
} from '../utils/sanitizer';

const MIN_QUERY_LENGTH = 20;

export default function SanitizerPanel({
  query,
  setQuery,
  explainPlan,
  setExplainPlan,
  substitutionMap,
  setSubstitutionMap,
}) {
  const [preview, setPreview] = useState(null); // { map, sanitizedQuery, diff }
  const [showMap, setShowMap] = useState(false);

  if (!query || query.trim().length <= MIN_QUERY_LENGTH) return null;

  const handleSanitizeClick = () => {
    const identifiers = extractIdentifiers(query);
    const map = buildSubstitutionMap(identifiers);
    setPreview({
      map,
      sanitizedQuery: sanitize(query, map),
      diff: buildDiff(query, map),
    });
  };

  const handleApply = () => {
    if (!preview) return;
    setQuery(preview.sanitizedQuery);
    if (explainPlan && explainPlan.trim()) {
      setExplainPlan(sanitize(explainPlan, preview.map));
    }
    setSubstitutionMap(preview.map);
    setPreview(null);
  };

  const handleCancel = () => setPreview(null);

  const handleUndo = () => {
    if (!substitutionMap) return;
    setQuery(desanitize(query, substitutionMap));
    if (explainPlan && explainPlan.trim()) {
      setExplainPlan(desanitize(explainPlan, substitutionMap));
    }
    setSubstitutionMap(null);
    setShowMap(false);
  };

  // ── STATE 3 — sanitized ──────────────────────────────────────────────────
  if (substitutionMap) {
    const entries = Object.entries(substitutionMap);
    return (
      <div className="mt-3 border-t border-slate-700 pt-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{
              background: 'rgba(52,211,153,0.1)',
              color: '#34d399',
              border: '1px solid rgba(52,211,153,0.3)',
            }}
          >
            🔒 Sanitized
          </span>
          {explainPlan && explainPlan.trim() && (
            <span className="text-xs" style={{ color: '#34d399' }}>
              🔒 EXPLAIN plan also sanitized
            </span>
          )}
        </div>

        <div className="mt-2 flex items-center gap-4">
          <button
            type="button"
            onClick={() => setShowMap((v) => !v)}
            className="text-xs text-slate-400 hover:text-white underline"
          >
            {showMap ? 'Hide' : 'View'} substitution map
          </button>
          <button
            type="button"
            onClick={handleUndo}
            className="text-xs text-slate-400 hover:text-red-400 underline"
          >
            Undo sanitization
          </button>
        </div>

        {showMap && (
          <div className="mt-2 rounded border border-slate-700 bg-slate-900 p-3">
            {entries.length === 0 ? (
              <p className="text-xs text-slate-500">No identifiers were substituted.</p>
            ) : (
              entries.map(([orig, sub]) => (
                <div key={orig} className="flex items-center gap-2 text-xs font-mono py-0.5">
                  <span className="text-slate-400">{orig}</span>
                  <span className="text-slate-600">&rarr;</span>
                  <span style={{ color: '#38bdf8' }}>{sub}</span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    );
  }

  // ── STATE 2 — preview ────────────────────────────────────────────────────
  if (preview) {
    const originalLines = query.split('\n').slice(0, 3).join('\n');
    const sanitizedLines = preview.sanitizedQuery.split('\n').slice(0, 3).join('\n');
    const shownDiff = preview.diff.slice(0, 8);
    const remaining = preview.diff.length - shownDiff.length;

    return (
      <div className="mt-3 border-t border-slate-700 pt-3">
        <p className="text-sm font-medium text-slate-300">
          Substitution preview — confirm to apply
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          <div>
            <p className="text-xs font-medium text-slate-500 mb-1">Original</p>
            <pre className="text-xs bg-slate-900 border border-slate-700 rounded p-2 overflow-x-auto text-slate-300 font-mono whitespace-pre-wrap">
              {originalLines}
            </pre>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-1">Sanitized</p>
            <pre
              className="text-xs bg-slate-900 border border-slate-700 rounded p-2 overflow-x-auto font-mono whitespace-pre-wrap"
              style={{ color: '#34d399' }}
            >
              {sanitizedLines}
            </pre>
          </div>
        </div>

        {shownDiff.length > 0 && (
          <div className="mt-3 rounded border border-slate-700 bg-slate-900 p-3">
            {shownDiff.map(({ original, sanitized }) => (
              <div key={original} className="flex items-center gap-2 text-xs font-mono py-0.5">
                <span className="text-slate-400">{original}</span>
                <span className="text-slate-600">&rarr;</span>
                <span style={{ color: '#38bdf8' }}>{sanitized}</span>
              </div>
            ))}
            {remaining > 0 && <p className="text-xs text-slate-500 mt-1">+ {remaining} more</p>}
          </div>
        )}

        <p className="text-xs text-slate-500 mt-2">
          Single-letter aliases (p, t, u) are preserved as-is
        </p>

        <div className="flex items-center gap-3 mt-3">
          <button
            type="button"
            onClick={handleApply}
            className="text-sm font-medium px-4 py-1.5 rounded"
            style={{ background: '#38bdf8', color: '#0f172a' }}
          >
            Apply sanitization
          </button>
          <button
            type="button"
            onClick={handleCancel}
            className="text-xs text-slate-400 hover:text-white underline"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // ── STATE 1 — idle ───────────────────────────────────────────────────────
  return (
    <div className="mt-3 border-t border-slate-700 pt-3">
      <button
        type="button"
        onClick={handleSanitizeClick}
        className="text-xs font-medium text-slate-400 hover:text-slate-200"
      >
        🔒 Sanitize before analyzing
      </button>
      <p className="text-xs text-slate-500 mt-1">
        Replace table and column names with dummy values — nothing proprietary leaves your browser
      </p>
    </div>
  );
}
