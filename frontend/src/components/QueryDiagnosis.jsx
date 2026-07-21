import { BookOpen } from 'lucide-react';

// ── Token colours matching the design system ─────────────────────────────
const C = {
  surface: '#1e293b',
  border: '#2d3f55',
  text: '#e2e8f0',
  muted: '#94a3b8',
  dim: '#4a6480',
  label: '#7fa3c4',
  accent: '#38bdf8',
  green: '#34d399',
  yellow: '#fbbf24',
  red: '#f87171',
};

// ── Section detection helpers ─────────────────────────────────────────────

const SECTION_MARKERS = [
  'Query Summary',
  'Schema Context',
  'Performance Findings',
  'Security Observations',
  'Security Notes',
  'Readability Tips',
  'Optimization Hints',
];

function isSectionHeader(line) {
  const stripped = line
    .replace(/^#{1,3}\s*/, '')
    .replace(/📖|🔍|⚠️|✅|❌/gu, '')
    .trim();
  // Covers "PostgreSQL Maintenance Commands", "MySQL Maintenance Commands", etc.
  // without hardcoding every dialect variant.
  if (stripped.endsWith('Maintenance Commands')) return true;
  return SECTION_MARKERS.some((m) => stripped.startsWith(m));
}

function isFenceLine(line) {
  const t = line.trim();
  return t === '```sql' || t === '```';
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

// Matches the sql_analyzer "**N issue(s) detected** — ..." findings summary line
function parseIssueCountLine(line) {
  const m = line.match(/^\*\*(\d+)\s+(issue\(s\)\s+detected)\*\*(.*)$/);
  if (!m) return null;
  return { count: m[1], label: m[2], rest: m[3] };
}

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
  let inCodeBlock = false;
  let codeBuffer = [];

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (isFenceLine(line)) {
      if (inCodeBlock) {
        if (!currentSection) currentSection = { title: null, lines: [] };
        currentSection.lines.push({ type: 'code', content: codeBuffer.join('\n') });
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeBuffer = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(raw);
      continue;
    }

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

    const issueCount = parseIssueCountLine(line);
    if (issueCount) {
      currentSection.lines.push({ type: 'issue-count', ...issueCount });
      continue;
    }

    currentSection.lines.push({ type: 'text', content: line });
  }

  // Unterminated fence (shouldn't happen, but don't silently drop the content)
  if (inCodeBlock && codeBuffer.length) {
    if (!currentSection) currentSection = { title: null, lines: [] };
    currentSection.lines.push({ type: 'code', content: codeBuffer.join('\n') });
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

                if (line.type === 'code') {
                  return (
                    <pre
                      key={li}
                      style={{
                        background: '#0f172a',
                        color: C.green,
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 11.5,
                        lineHeight: 1.6,
                        padding: 12,
                        borderRadius: 8,
                        overflowX: 'auto',
                        margin: '2px 0',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {line.content}
                    </pre>
                  );
                }

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
                          color: C.label,
                          fontWeight: 500,
                          flexShrink: 0,
                          minWidth: 140,
                        }}
                      >
                        {line.key}
                      </span>
                      <span style={{ color: C.text }}>{line.value}</span>
                    </div>
                  );
                }

                if (line.type === 'issue-count') {
                  return (
                    <p
                      key={li}
                      style={{ fontSize: 12, lineHeight: 1.65, color: C.text, margin: 0 }}
                    >
                      <strong style={{ color: C.red, fontWeight: 700 }}>{line.count}</strong>{' '}
                      {line.label}
                      {line.rest}
                    </p>
                  );
                }

                // Text line — render inline bold segments (readability tips, generic body text)
                const segments = parseBold(line.content);

                return (
                  <p
                    key={li}
                    style={{
                      fontSize: 11,
                      lineHeight: 1.65,
                      color: C.muted,
                      margin: 0,
                    }}
                  >
                    {segments.map((seg, segi) =>
                      seg.bold ? (
                        <strong
                          key={segi}
                          style={{
                            color: C.text,
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
