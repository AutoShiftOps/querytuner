import { BookOpen } from 'lucide-react';

// ── Token colours matching the design system ─────────────────────────────
const C = {
  surface: '#1e293b',
  border: '#2d3f55',
  text: '#e2e8f0',
  muted: '#94a3b8',
  dim: '#4a6480',
  accent: '#38bdf8',
  green: '#34d399',
  yellow: '#fbbf24',
  red: '#f87171',
};

// ── Section detection helpers ─────────────────────────────────────────────

const SECTION_MARKERS = [
  'Query Summary',
  'Performance Findings',
  'Readability Tips',
  'Optimization Hints',
  'Security Notes',
];

function isSectionHeader(line) {
  const stripped = line
    .replace(/^#{1,3}\s*/, '')
    .replace(/📖|🔍|⚠️|✅|❌/gu, '')
    .trim();
  return SECTION_MARKERS.some((m) => stripped.startsWith(m));
}

function isKVLine(line) {
  // Matches "**Key:** value" or "Key: value"
  return /^\*\*[^*]+\*\*:/.test(line.trim()) || /^[A-Z][^:]+:\s/.test(line.trim());
}

function parseKV(line) {
  // Handles "**Query type:** SELECT" → { key: 'Query type', value: 'SELECT' }
  const boldMatch = line.match(/^\*\*([^*]+)\*\*:\s*(.*)/);
  if (boldMatch) return { key: boldMatch[1].trim(), value: boldMatch[2].trim() };
  const plainMatch = line.match(/^([^:]+):\s+(.*)/);
  if (plainMatch) return { key: plainMatch[1].trim(), value: plainMatch[2].trim() };
  return null;
}

// function isBoldLine(line) {
//   return /^\*\*[^*]+\*\*\s*[—–-]/.test(line.trim()) || /^\*\*[^*]+\*\*$/.test(line.trim());
// }

function parseBold(line) {
  // Returns array of { text, bold } segments
  const parts = [];
  const regex = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let match;
  while ((match = regex.exec(line)) !== null) {
    if (match.index > last) parts.push({ text: line.slice(last, match.index), bold: false });
    parts.push({ text: match[1], bold: true });
    last = match.index + match[0].length;
  }
  if (last < line.length) parts.push({ text: line.slice(last), bold: false });
  return parts;
}

function stripEmoji(str) {
  return str.replace(/⚠️|[📖🔍✅❌🧩💡]/gu, '').trim();
}

// ── Main component ────────────────────────────────────────────────────────

export default function QueryDiagnosis({ content }) {
  if (!content) return null;

  const lines = content.split('\n');
  const sections = [];
  let currentSection = null;

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line) {
      if (currentSection) currentSection.lines.push({ type: 'spacer' });
      continue;
    }

    if (isSectionHeader(line)) {
      if (currentSection) sections.push(currentSection);
      currentSection = {
        title: stripEmoji(line.replace(/^#{1,3}\s*/, '')),
        lines: [],
      };
      continue;
    }

    if (!currentSection) {
      currentSection = { title: null, lines: [] };
    }

    if (isKVLine(line)) {
      const kv = parseKV(line);
      if (kv) {
        currentSection.lines.push({ type: 'kv', ...kv });
        continue;
      }
    }

    currentSection.lines.push({ type: 'text', content: line });
  }

  if (currentSection) sections.push(currentSection);

  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 16px',
          borderBottom: `1px solid ${C.border}`,
          background: 'rgba(0,0,0,0.2)',
        }}
      >
        <BookOpen size={14} color={C.accent} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Query Diagnosis</span>
      </div>

      {/* Sections */}
      <div style={{ padding: '4px 0' }}>
        {sections.map((section, si) => (
          <div
            key={si}
            style={{
              borderBottom: si < sections.length - 1 ? `1px solid ${C.border}` : 'none',
              padding: '12px 16px',
            }}
          >
            {/* Section title */}
            {section.title && (
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: C.dim,
                  marginBottom: 10,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                {section.title}
                <span
                  style={{
                    flex: 1,
                    height: 1,
                    background: C.border,
                    display: 'inline-block',
                  }}
                />
              </div>
            )}

            {/* Lines */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {section.lines.map((line, li) => {
                if (line.type === 'spacer') return null;

                if (line.type === 'kv') {
                  return (
                    <div
                      key={li}
                      style={{
                        display: 'flex',
                        gap: 8,
                        alignItems: 'baseline',
                        fontSize: 12,
                        lineHeight: 1.6,
                      }}
                    >
                      <span
                        style={{
                          color: C.muted,
                          fontWeight: 500,
                          flexShrink: 0,
                          minWidth: 130,
                        }}
                      >
                        {line.key}
                      </span>
                      <span style={{ color: C.text }}>{line.value}</span>
                    </div>
                  );
                }

                // Text line — render inline bold segments
                const segments = parseBold(line.content);
                const hasHighlight =
                  line.content.includes('issue') || line.content.includes('detected');

                return (
                  <p
                    key={li}
                    style={{
                      fontSize: 12,
                      lineHeight: 1.65,
                      color: hasHighlight ? C.text : C.muted,
                      margin: 0,
                    }}
                  >
                    {segments.map((seg, segi) =>
                      seg.bold ? (
                        <strong
                          key={segi}
                          style={{
                            color: hasHighlight ? C.yellow : C.text,
                            fontWeight: 600,
                          }}
                        >
                          {seg.text}
                        </strong>
                      ) : (
                        <span key={segi}>{seg.text}</span>
                      )
                    )}
                  </p>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
