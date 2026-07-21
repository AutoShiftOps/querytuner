import { safeParseAiJson } from '../utils/aiInsights';

// ── Token colours matching the design system (QueryDiagnosis.jsx, App.jsx) ──
const SEVERITY_COLORS = {
  critical: '#f87171',
  high: '#f97316',
  medium: '#fbbf24',
  low: '#34d399',
};

function severityColor(sev) {
  return SEVERITY_COLORS[(sev || '').toLowerCase()] || SEVERITY_COLORS.low;
}

const copyButtonClass =
  'text-xs text-slate-400 hover:text-white border border-slate-600 ' +
  'hover:border-slate-400 px-3 py-1 rounded transition-colors';

function CopyButton({ text, label = 'Copy' }) {
  return (
    <button onClick={() => navigator.clipboard.writeText(text || '')} className={copyButtonClass}>
      {label}
    </button>
  );
}

function SectionTitle({ children }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: '#4a6480',
        marginBottom: 10,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      {children}
      <span style={{ flex: 1, height: 1, background: '#2d3f55', display: 'inline-block' }} />
    </div>
  );
}

function SuggestionCard({ item }) {
  return (
    <div
      style={{
        background: '#1e293b',
        border: '1px solid #2d3f55',
        borderRadius: 8,
        padding: 14,
        marginBottom: 10,
      }}
    >
      <div
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#7fa3c4',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          {(item.type || 'suggestion').replace(/_/g, ' ')}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            color: severityColor(item.severity),
            border: `1px solid ${severityColor(item.severity)}`,
            borderRadius: 999,
            padding: '2px 8px',
            flexShrink: 0,
          }}
        >
          {item.severity || 'low'}
        </span>
      </div>

      {item.suggestion && (
        <p
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: '#e2e8f0',
            margin: '8px 0 0',
            lineHeight: 1.5,
          }}
        >
          {item.suggestion}
        </p>
      )}

      {item.reason && (
        <p style={{ fontSize: 12, color: '#94a3b8', margin: '6px 0 0', lineHeight: 1.5 }}>
          {item.reason}
        </p>
      )}

      {item.estimated_improvement && (
        <p
          style={{
            fontSize: 11,
            color: '#38bdf8',
            fontFamily: "'JetBrains Mono', monospace",
            margin: '8px 0 0',
          }}
        >
          {item.estimated_improvement}
        </p>
      )}

      {item.ddl_statement && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
            <CopyButton text={item.ddl_statement} />
          </div>
          <pre
            style={{
              background: '#0f172a',
              color: '#7dd3fc',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
              padding: 12,
              borderRadius: 8,
              overflowX: 'auto',
              margin: 0,
              whiteSpace: 'pre-wrap',
            }}
          >
            {item.ddl_statement}
          </pre>
        </div>
      )}
    </div>
  );
}

const RISKY_CARD_STYLE = {
  background: 'rgba(251,191,36,0.06)',
  border: '1px solid rgba(251,191,36,0.2)',
  borderRadius: 8,
  padding: '10px 14px',
  marginBottom: 8,
};

const RISKY_NOTE_STYLE = {
  fontSize: 13,
  color: '#e2e8f0',
  margin: 0,
  lineHeight: 1.5,
};

function RiskyAssumptionCard({ item }) {
  // Plain string assumption — render directly, no object shape to unpack.
  if (typeof item === 'string') {
    return (
      <div style={RISKY_CARD_STYLE}>
        <p style={RISKY_NOTE_STYLE}>{item}</p>
      </div>
    );
  }

  // Defensive fallback for anything that's neither a string nor an object
  // (number, boolean, null, undefined) — never hand JSON.stringify a
  // non-object here, since that's how raw braces leak to the user.
  if (!item || typeof item !== 'object') {
    return (
      <div style={RISKY_CARD_STYLE}>
        <p style={RISKY_NOTE_STYLE}>{String(item)}</p>
      </div>
    );
  }

  // {"type": "unknown_cardinality", "column": "p.category", "note": "..."}
  const note = item.note || item.assumption || JSON.stringify(item);

  return (
    <div style={RISKY_CARD_STYLE}>
      {item.type && (
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            color: '#94a3b8',
            border: '1px solid rgba(148,163,184,0.3)',
            borderRadius: 999,
            padding: '1px 6px',
            display: 'inline-block',
            marginBottom: 6,
          }}
        >
          {String(item.type).replace(/_/g, ' ')}
        </span>
      )}
      <p style={RISKY_NOTE_STYLE}>{note}</p>
      {item.column && (
        <p
          style={{
            fontSize: 11,
            color: '#fbbf24',
            fontFamily: "'JetBrains Mono', monospace",
            margin: '6px 0 0',
          }}
        >
          Column: {item.column}
        </p>
      )}
    </div>
  );
}

function StructuredInsights({ data, aiConfirmedTypes }) {
  const allImprovements = Array.isArray(data.most_impactful_improvements)
    ? data.most_impactful_improvements
    : [];
  // Types already confirmed on a heuristic card (badged in OptimizationSuggestions)
  // are dropped here instead of repeating the same finding in both panels.
  const improvements =
    aiConfirmedTypes && aiConfirmedTypes.size > 0
      ? allImprovements.filter((item) => !aiConfirmedTypes.has(item?.type))
      : allImprovements;
  const indexes = Array.isArray(data.recommended_indexes) ? data.recommended_indexes : [];
  const rewritten = typeof data.rewritten_query === 'string' ? data.rewritten_query.trim() : '';
  const risky = Array.isArray(data.risky_assumptions) ? data.risky_assumptions : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {improvements.length > 0 && (
        <div>
          <SectionTitle>
            Most Impactful Improvements
            <span
              style={{
                textTransform: 'none',
                fontWeight: 400,
                letterSpacing: 'normal',
                color: '#4a6480',
              }}
            >
              (complements heuristic findings above)
            </span>
          </SectionTitle>
          {improvements.map((item, idx) => (
            <SuggestionCard key={idx} item={item} />
          ))}
        </div>
      )}

      {indexes.length > 0 && (
        <div>
          <SectionTitle>Recommended Indexes</SectionTitle>
          {indexes.map((item, idx) => (
            <SuggestionCard key={idx} item={item} />
          ))}
        </div>
      )}

      {rewritten && (
        <div>
          <SectionTitle>Rewritten Query</SectionTitle>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
            <CopyButton text={rewritten} />
          </div>
          <pre
            style={{
              background: '#0f172a',
              color: '#34d399',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 12,
              lineHeight: 1.6,
              padding: 12,
              borderRadius: 8,
              overflowX: 'auto',
              margin: 0,
              whiteSpace: 'pre-wrap',
            }}
          >
            {rewritten}
          </pre>
        </div>
      )}

      {risky.length > 0 && (
        <div>
          <SectionTitle>Risky Assumptions</SectionTitle>
          {risky.map((item, idx) => (
            <RiskyAssumptionCard key={idx} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function PlainTextInsights({ content }) {
  const lines = content.split('\n').filter((line) => line.trim());
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {lines.map((line, idx) => (
        <p key={idx} style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
          {line}
        </p>
      ))}
    </div>
  );
}

function ResultsPanel({ title, content, icon: Icon, onShare, aiConfirmedTypes }) {
  if (!content) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    if (onShare) {
      onShare();
    }
  };

  const parsed = safeParseAiJson(content);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-2">
          {Icon && <Icon className="w-5 h-5 text-blue-400 mt-0.5" />}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-white">{title}</h3>
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: '#7fa3c4',
                  background: 'rgba(127,163,196,0.1)',
                  border: '1px solid rgba(127,163,196,0.25)',
                  borderRadius: 999,
                  padding: '2px 8px',
                }}
              >
                AI Generated
              </span>
            </div>
            <p style={{ fontSize: 11, color: '#7fa3c4', margin: '2px 0 0' }}>
              AI-enhanced reasoning and query rewrites
            </p>
          </div>
        </div>
        <button onClick={handleCopy} className={copyButtonClass}>
          Copy
        </button>
      </div>

      {parsed ? (
        <StructuredInsights data={parsed} aiConfirmedTypes={aiConfirmedTypes} />
      ) : (
        <PlainTextInsights content={content} />
      )}
    </div>
  );
}

export default ResultsPanel;
