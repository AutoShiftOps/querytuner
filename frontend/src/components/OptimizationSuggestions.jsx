import React from 'react';

function severityColor(sev) {
  const s = (sev || '').toLowerCase();
  if (s === 'critical') return 'border-red-500 bg-red-900/20 text-red-200';
  if (s === 'high') return 'border-orange-500 bg-orange-900/20 text-orange-200';
  if (s === 'medium') return 'border-yellow-500 bg-yellow-900/20 text-yellow-200';
  return 'border-slate-600 bg-slate-800 text-slate-200';
}

export default function OptimizationSuggestions({ suggestions }) {
  const items = Array.isArray(suggestions) ? suggestions : [];

  if (items.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h3 className="text-lg font-bold text-white">Suggestions</h3>
        <p className="text-slate-400 text-sm mt-2">No suggestions found.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h3 className="text-lg font-bold text-white mb-4">Suggestions</h3>

      <div className="space-y-3">
        {items.map((s, idx) => (
          <div key={idx} className={`p-4 rounded border ${severityColor(s.severity)}`}>
            <div className="flex items-center justify-between gap-3">
              <p className="font-semibold">{(s.type || 'issue').toUpperCase()}</p>
              <span className="text-xs opacity-90">{(s.severity || 'low').toUpperCase()}</span>
            </div>

            <p className="mt-2">{s.suggestion}</p>

            {s.reason ? <p className="mt-2 text-sm opacity-90">Reason: {s.reason}</p> : null}

            {s.estimated_improvement ? (
              <p className="mt-2 text-sm opacity-90">Estimate: {s.estimated_improvement}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
