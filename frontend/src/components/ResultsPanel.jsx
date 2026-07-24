import { safeParseAiJson } from '../utils/aiInsights';

// The LLM's top-level JSON schema drifts across providers/models — e.g.
// OpenAI's gpt-4o-mini has returned "performance_improvements" where the
// prompt asked for "most_impactful_improvements". Look up whichever key
// name is actually present instead of trusting one fixed schema.
function findKey(obj, candidates) {
  if (!obj || typeof obj !== 'object') return null;
  for (const key of candidates) {
    if (obj[key] !== undefined) return obj[key];
  }
  return null;
}

const IMPROVEMENTS_KEYS = [
  'most_impactful_improvements',
  'performance_improvements',
  'improvements',
  'suggestions',
  'recommendations',
];
const INDEXES_KEYS = ['recommended_indexes', 'indexes', 'index_recommendations', 'missing_indexes'];
const REWRITTEN_QUERY_KEYS = ['rewritten_query', 'optimized_query', 'rewrite'];
const RISKY_ASSUMPTIONS_KEYS = ['risky_assumptions', 'assumptions', 'risks', 'warnings'];

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

// The LLM's structured-output schema drifts across calls/models — sometimes
// {suggestion, reason, ddl_statement}, sometimes {description, rationale, ddl},
// sometimes a nested {suggestion: {text, reason}}, sometimes plain strings.
// Extract whatever's actually there instead of trusting one fixed shape, and
// return null when nothing usable is found so the card renders nothing rather
// than an empty shell with just a type/severity badge.
function extractCardFields(item) {
  // Handle plain string
  if (typeof item === 'string') {
    return {
      title: item,
      reason: null,
      estimate: null,
      ddl: null,
      severity: 'medium',
    };
  }

  if (!item || typeof item !== 'object') {
    return null; // skip entirely
  }

  // Title — try every known field name
  const title =
    (typeof item.suggestion === 'string' ? item.suggestion : null) ||
    (typeof item.suggestion?.text === 'string' ? item.suggestion.text : null) ||
    item.title ||
    item.description ||
    item.name ||
    item.text ||
    // Last resort: first string value > 10 chars
    Object.values(item).find((v) => typeof v === 'string' && v.length > 10) ||
    null;

  // If no title found at all — skip this card
  if (!title) return null;

  const reason =
    (typeof item.reason === 'string' ? item.reason : null) ||
    item.rationale ||
    item.explanation ||
    item.detail ||
    (typeof item.suggestion?.reason === 'string' ? item.suggestion.reason : null) ||
    null;

  const estimate =
    item.estimated_improvement || item.estimate || item.impact || item.benefit || null;

  const ddl = item.ddl_statement || item.ddl || item.ddl_hint || item.index_ddl || item.sql || null;

  const severity = item.severity || 'medium';

  return { title, reason, estimate, ddl, severity };
}

function SuggestionCard({ item }) {
  const fields = extractCardFields(item);
  if (!fields) return null;

  const typeLabel =
    item && typeof item === 'object' && item.type ? String(item.type).replace(/_/g, ' ') : '';

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
          {typeLabel}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            color: severityColor(fields.severity),
            border: `1px solid ${severityColor(fields.severity)}`,
            borderRadius: 999,
            padding: '2px 8px',
            flexShrink: 0,
          }}
        >
          {fields.severity}
        </span>
      </div>

      <p
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: '#e2e8f0',
          margin: '8px 0 0',
          lineHeight: 1.5,
        }}
      >
        {fields.title}
      </p>

      {fields.reason && (
        <p style={{ fontSize: 12, color: '#94a3b8', margin: '6px 0 0', lineHeight: 1.5 }}>
          {fields.reason}
        </p>
      )}

      {fields.estimate && (
        <p
          style={{
            fontSize: 11,
            color: '#38bdf8',
            fontFamily: "'JetBrains Mono', monospace",
            margin: '8px 0 0',
          }}
        >
          {fields.estimate}
        </p>
      )}

      {fields.ddl && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
            <CopyButton text={fields.ddl} />
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
            {fields.ddl}
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

  // {"type": "unknown_cardinality", "column": "p.category", "note": "..."} —
  // but the LLM doesn't always use those exact keys (e.g. {"schema":"missing",
  // "reason":"..."}), so fall through several aliases before ever resorting
  // to JSON.stringify, and never let a JSON-shaped string reach the screen.
  let displayText = item.note || item.reason || item.assumption || JSON.stringify(item);
  if (typeof displayText === 'string' && /^[[{]/.test(displayText.trim())) {
    displayText =
      'AI identified a potential assumption — provide schema DDL for more specific analysis';
  }

  const columnLabel = item.column || item.field || item.table || null;
  const typeLabel = item.type || item.schema || null;

  return (
    <div style={RISKY_CARD_STYLE}>
      {typeLabel && (
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
          {String(typeLabel).replace(/_/g, ' ')}
        </span>
      )}
      <p style={RISKY_NOTE_STYLE}>{displayText}</p>
      {columnLabel && (
        <p
          style={{
            fontSize: 11,
            color: '#fbbf24',
            fontFamily: "'JetBrains Mono', monospace",
            margin: '6px 0 0',
          }}
        >
          Column: {columnLabel}
        </p>
      )}
    </div>
  );
}

function StructuredInsights({ data, aiConfirmedTypes }) {
  const improvementsRaw = findKey(data, IMPROVEMENTS_KEYS);
  const allImprovements = Array.isArray(improvementsRaw) ? improvementsRaw : [];
  // Types already confirmed on a heuristic card (badged in OptimizationSuggestions)
  // are dropped here instead of repeating the same finding in both panels.
  const improvements =
    aiConfirmedTypes && aiConfirmedTypes.size > 0
      ? allImprovements.filter((item) => !aiConfirmedTypes.has(item?.type))
      : allImprovements;
  const indexesRaw = findKey(data, INDEXES_KEYS);
  const indexes = Array.isArray(indexesRaw) ? indexesRaw : [];
  const rewrittenRaw = findKey(data, REWRITTEN_QUERY_KEYS);
  const rewritten = typeof rewrittenRaw === 'string' ? rewrittenRaw.trim() : '';
  const riskyRaw = findKey(data, RISKY_ASSUMPTIONS_KEYS);
  const risky = Array.isArray(riskyRaw) ? riskyRaw : [];

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
  // A parsed JSON object with none of the known top-level keys isn't a
  // recognisable structured shape (e.g. an LLM that returned unrelated JSON)
  // — fall back to plain text rather than rendering an empty panel.
  const hasStructuredContent =
    parsed &&
    (findKey(parsed, IMPROVEMENTS_KEYS) !== null ||
      findKey(parsed, INDEXES_KEYS) !== null ||
      findKey(parsed, REWRITTEN_QUERY_KEYS) !== null);

  const parts = title.split('(');
  const mainTitle = parts[0].trim();
  const subtitle = parts[1] ? parts[1].replace(')', '').trim() : '';

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 12,
        }}
      >
        {/* LEFT: icon + title stack */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          {Icon && <Icon size={16} style={{ color: '#38bdf8', flexShrink: 0, marginTop: 2 }} />}
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#e2e8f0',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {mainTitle}
            </div>
            {subtitle && (
              <div
                style={{
                  fontSize: 11,
                  color: '#7fa3c4',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  marginTop: 2,
                }}
              >
                {subtitle}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: badge + copy button — always inline */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: 9,
              fontWeight: 600,
              padding: '3px 7px',
              borderRadius: 20,
              background: 'rgba(56,189,248,0.1)',
              color: '#38bdf8',
              border: '1px solid rgba(56,189,248,0.2)',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}
          >
            AI Generated
          </span>
          <button onClick={handleCopy} className={copyButtonClass}>
            Copy
          </button>
        </div>
      </div>

      {hasStructuredContent ? (
        <StructuredInsights data={parsed} aiConfirmedTypes={aiConfirmedTypes} />
      ) : (
        <PlainTextInsights content={content} />
      )}
    </div>
  );
}

export default ResultsPanel;
