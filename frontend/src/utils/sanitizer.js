// Client-side query sanitizer — replaces table/column names with deterministic
// dummy values (table_a, col_a, ...) so proprietary schema never leaves the
// browser. This is a regex-based heuristic, not a full SQL AST parser: it is
// tuned to catch the common clause shapes (FROM/JOIN/INTO/UPDATE, SELECT
// lists, WHERE/ON/HAVING, GROUP BY/ORDER BY, SET) across the 5 supported
// dialects without adding a parser dependency to the frontend bundle.

// ── SQL keyword / function exclusion list (covers postgresql, mysql, oracle,
// sqlserver, sqlite) — never substituted, even though they appear next to
// identifiers in the clauses we scan. ─────────────────────────────────────
const SQL_KEYWORDS = new Set(
  [
    'SELECT',
    'FROM',
    'WHERE',
    'JOIN',
    'INNER',
    'LEFT',
    'RIGHT',
    'FULL',
    'OUTER',
    'CROSS',
    'ON',
    'AS',
    'AND',
    'OR',
    'NOT',
    'NULL',
    'IS',
    'IN',
    'EXISTS',
    'BETWEEN',
    'LIKE',
    'ILIKE',
    'ANY',
    'ALL',
    'SOME',
    'GROUP',
    'BY',
    'ORDER',
    'HAVING',
    'LIMIT',
    'OFFSET',
    'UNION',
    'DISTINCT',
    'INSERT',
    'INTO',
    'VALUES',
    'UPDATE',
    'SET',
    'DELETE',
    'CREATE',
    'TABLE',
    'ALTER',
    'DROP',
    'INDEX',
    'VIEW',
    'TRIGGER',
    'PROCEDURE',
    'FUNCTION',
    'DECLARE',
    'BEGIN',
    'END',
    'CASE',
    'WHEN',
    'THEN',
    'ELSE',
    'CAST',
    'CONVERT',
    'TOP',
    'ROWNUM',
    'FETCH',
    'NEXT',
    'ROWS',
    'ROW',
    'ONLY',
    'WITH',
    'RECURSIVE',
    'PARTITION',
    'OVER',
    'ASC',
    'DESC',
    'PRIMARY',
    'KEY',
    'FOREIGN',
    'REFERENCES',
    'CONSTRAINT',
    'UNIQUE',
    'CHECK',
    'DEFAULT',
    'AUTO_INCREMENT',
    'IDENTITY',
    'SERIAL',
    'SCHEMA',
    'DATABASE',
    'USE',
    'GRANT',
    'REVOKE',
    'COMMIT',
    'ROLLBACK',
    'TRANSACTION',
    'EXPLAIN',
    'ANALYZE',
    'VACUUM',
    'TRUNCATE',
    'REPLACE',
    'MERGE',
    'USING',
    'RETURNING',
    'CONFLICT',
    'DO',
    'NOTHING',
    'FOR',
    'LATERAL',
    'WINDOW',
    'FILTER',
    'WITHIN',
    'CONNECT',
    'START',
    'PRIOR',
    'DUAL',
    'GO',
    'IF',
    'ELSEIF',
    'WHILE',
    'LOOP',
    'CURSOR',
    'TABLESPACE',
    'NULLS',
    'FIRST',
    'LAST',
    'BUFFERS',
    'VERBOSE',
    'FORMAT',
    'JSON',
    'TEXT_PLAN',
    'PLAN',
    'STATISTICS',
    'IO',
    'TIME',
    // aggregate / scalar functions commonly seen adjacent to identifiers
    'COUNT',
    'SUM',
    'AVG',
    'MIN',
    'MAX',
    'COALESCE',
    'NULLIF',
    'NVL',
    'ISNULL',
    'ROUND',
    'TRUNC',
    'ROW_NUMBER',
    'RANK',
    'DENSE_RANK',
    'LAG',
    'LEAD',
    'NTILE',
    'SUBSTRING',
    'SUBSTR',
    'TRIM',
    'UPPER',
    'LOWER',
    'LENGTH',
    'LEN',
    'CONCAT',
    'TO_CHAR',
    'TO_DATE',
    'TO_NUMBER',
    'GETDATE',
    'NOW',
    'CURRENT_DATE',
    'CURRENT_TIME',
    'CURRENT_TIMESTAMP',
    'EXTRACT',
    'DATEADD',
    'DATEDIFF',
    'DATE_ADD',
    'DATE_SUB',
    // data types
    'VARCHAR',
    'VARCHAR2',
    'NVARCHAR',
    'CHAR',
    'NCHAR',
    'CLOB',
    'BLOB',
    'INT',
    'INTEGER',
    'BIGINT',
    'SMALLINT',
    'TINYINT',
    'DECIMAL',
    'NUMERIC',
    'NUMBER',
    'FLOAT',
    'DOUBLE',
    'REAL',
    'BOOLEAN',
    'BOOL',
    'DATE',
    'DATETIME',
    'DATETIME2',
    'TIMESTAMP',
    'TIME',
    'MONEY',
    'UUID',
    'JSONB',
    'XML',
    'BIT',
    // literals
    'TRUE',
    'FALSE',
    'UNKNOWN',
  ].map((k) => k.toUpperCase())
);

function isKeyword(word) {
  return SQL_KEYWORDS.has(String(word).toUpperCase());
}

// Negative lookahead used wherever an "implicit alias" is optionally
// captured (e.g. "FROM pinacle JOIN ..."). Without this, a bare optional
// capture group happily matches the *next clause's keyword* as if it were
// an alias — the keyword gets filtered out by value afterwards, but the
// regex's lastIndex has already advanced past it, so the next exec() call
// never sees that keyword as the start of its own clause.
const KEYWORD_LOOKAHEAD = `(?!(?:${[...SQL_KEYWORDS].join('|')})\\b)`;

function shouldExclude(name) {
  if (!name) return true;
  if (name.length <= 1) return true; // single-letter aliases (p, t, u, o, a, b, c...)
  if (/^\d+$/.test(name)) return true; // numeric literal, not an identifier
  if (isKeyword(name)) return true;
  return false;
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ── Identifier grammar fragments ────────────────────────────────────────────
const IDENT_SRC = '[A-Za-z_][A-Za-z0-9_$]*';
const QUOTED_SRC = '"[^"]+"|`[^`]+`|\\[[^\\]]+\\]';
const NAME_SRC = `(?:${QUOTED_SRC}|${IDENT_SRC})`;
// schema.table / table.column / db.schema.table — dotted chains
const QUALIFIED_SRC = `${NAME_SRC}(?:\\s*\\.\\s*${NAME_SRC})*`;

const BOUNDARY_KEYWORDS =
  'FROM|WHERE|GROUP\\s+BY|ORDER\\s+BY|HAVING|LIMIT|OFFSET|UNION|JOIN|INNER\\s+JOIN|' +
  'LEFT\\s+JOIN|LEFT\\s+OUTER\\s+JOIN|RIGHT\\s+JOIN|RIGHT\\s+OUTER\\s+JOIN|FULL\\s+JOIN|' +
  'FULL\\s+OUTER\\s+JOIN|CROSS\\s+JOIN|ON|USING|SET|VALUES|RETURNING|;';

function stripLiteralsAndComments(sql) {
  return sql
    .replace(/--.*$/gm, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''");
}

// "public"."pinacle" / dbo.transactions / pinacle -> local name, quotes stripped.
// Only the last dotted segment is treated as the substitutable identifier —
// schema/db prefixes are left untouched (constraint #5).
function lastSegment(raw) {
  const parts = raw.split('.');
  const last = parts[parts.length - 1].trim();
  return last.replace(/^[`"[]/, '').replace(/[`"\]]$/, '');
}

function splitTopLevel(text, sep = ',') {
  const parts = [];
  let depth = 0;
  let current = '';
  for (const ch of text) {
    if (ch === '(') depth += 1;
    if (ch === ')') depth -= 1;
    if (ch === sep && depth === 0) {
      parts.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  parts.push(current);
  return parts;
}

// Scans free-form clause text (WHERE conditions, SELECT items, ORDER BY
// items) for identifier-shaped tokens, skipping function-call names (an
// identifier immediately followed by "(") and resolving dotted refs to their
// last segment.
function scanGenericIdentifiers(text, type, add) {
  const re = new RegExp(QUALIFIED_SRC, 'g');
  let m;
  while ((m = re.exec(text))) {
    const token = m[0];
    const after = text.slice(m.index + token.length);
    if (/^\s*\(/.test(after)) continue; // function call, not an identifier
    add(token, type);
  }
}

/**
 * Extract table/column/alias identifiers from a SQL string.
 *
 * Returns an array of { name, type } — type is 'table' or 'column'. (A flat
 * dedup on `name` is one call away via `.map(i => i.name)`; the type tag is
 * kept because buildSubstitutionMap needs it to assign table_x vs col_x.)
 */
export function extractIdentifiers(sql) {
  if (!sql || typeof sql !== 'string') return [];
  const cleaned = stripLiteralsAndComments(sql);
  const results = new Map();

  const add = (rawName, type) => {
    if (!rawName) return;
    const name = lastSegment(String(rawName).trim());
    if (shouldExclude(name)) return;
    const key = `${name.toLowerCase()}|${type}`;
    if (!results.has(key)) results.set(key, { name, type });
  };

  // Tables: FROM / JOIN / INTO / UPDATE, with optional alias.
  const tableRe = new RegExp(
    `\\b(?:FROM|JOIN|INTO|UPDATE)\\s+(${QUALIFIED_SRC})(?:\\s+(?:AS\\s+)?${KEYWORD_LOOKAHEAD}(${IDENT_SRC}))?`,
    'gi'
  );
  let m;
  while ((m = tableRe.exec(cleaned))) {
    add(m[1], 'table');
    if (m[2] && !isKeyword(m[2])) add(m[2], 'table');
  }

  // Legacy comma-separated FROM lists: FROM a, b c
  const fromListRe = new RegExp(
    `\\bFROM\\s+([\\s\\S]*?)(?=\\b(?:${BOUNDARY_KEYWORDS})\\b|$)`,
    'gi'
  );
  while ((m = fromListRe.exec(cleaned))) {
    for (const item of splitTopLevel(m[1])) {
      const trimmed = item.trim();
      if (!trimmed || trimmed.startsWith('(')) continue;
      const parts = trimmed.split(/\s+/).filter(Boolean);
      if (parts[0]) add(parts[0], 'table');
      if (parts.length >= 2 && /^AS$/i.test(parts[1]) && parts[2]) add(parts[2], 'table');
      else if (parts.length >= 2 && !isKeyword(parts[1])) add(parts[1], 'table');
    }
  }

  // SELECT list — columns and their aliases.
  const selectRe = new RegExp(`\\bSELECT\\s+(?:DISTINCT\\s+|ALL\\s+)?([\\s\\S]*?)\\bFROM\\b`, 'i');
  const selMatch = selectRe.exec(cleaned);
  if (selMatch) {
    for (const item of splitTopLevel(selMatch[1])) {
      const trimmed = item.trim();
      if (!trimmed || trimmed === '*') continue;
      const asMatch = trimmed.match(new RegExp(`\\bAS\\s+(${IDENT_SRC})\\s*$`, 'i'));
      if (asMatch) add(asMatch[1], 'column');
      scanGenericIdentifiers(trimmed, 'column', add);
    }
  }

  // WHERE / HAVING / ON — condition operands.
  for (const kw of ['WHERE', 'HAVING', 'ON']) {
    const re = new RegExp(`\\b${kw}\\s+([\\s\\S]*?)(?=\\b(?:${BOUNDARY_KEYWORDS})\\b|$)`, 'gi');
    while ((m = re.exec(cleaned))) {
      scanGenericIdentifiers(m[1], 'column', add);
    }
  }

  // GROUP BY / ORDER BY column lists.
  for (const kw of ['GROUP\\s+BY', 'ORDER\\s+BY']) {
    const re = new RegExp(`\\b${kw}\\s+([\\s\\S]*?)(?=\\b(?:${BOUNDARY_KEYWORDS})\\b|$)`, 'gi');
    while ((m = re.exec(cleaned))) {
      for (const item of splitTopLevel(m[1])) scanGenericIdentifiers(item, 'column', add);
    }
  }

  // SET col = val, col2 = val2 (UPDATE statements).
  const setRe = new RegExp(`\\bSET\\s+([\\s\\S]*?)(?=\\b(?:${BOUNDARY_KEYWORDS})\\b|$)`, 'gi');
  while ((m = setRe.exec(cleaned))) {
    for (const item of splitTopLevel(m[1])) {
      const [lhs] = item.split('=');
      if (lhs) add(lhs.trim(), 'column');
    }
  }

  return [...results.values()];
}

// Excel-style suffix generator: 0 -> 'a', 25 -> 'z', 26 -> 'aa', ...
function suffixFor(index) {
  let n = index + 1;
  let out = '';
  while (n > 0) {
    n -= 1;
    out = String.fromCharCode(97 + (n % 26)) + out;
    n = Math.floor(n / 26);
  }
  return out;
}

/**
 * Build a deterministic { original: substituted } map from extracted
 * identifiers. Tables -> table_a, table_b, ...; columns -> col_a, col_b, ...
 * Ordering is alphabetical (case-insensitive) so the same query always
 * produces the same map within a session, regardless of clause order.
 */
export function buildSubstitutionMap(identifiers) {
  const list = Array.isArray(identifiers) ? identifiers : [];
  const tables = new Map(); // lowercase -> first-seen casing
  const columns = new Map();

  for (const item of list) {
    const name = typeof item === 'string' ? item : item?.name;
    const type = typeof item === 'string' ? 'column' : item?.type;
    if (!name || shouldExclude(name)) continue;
    const key = name.toLowerCase();
    const bucket = type === 'table' ? tables : columns;
    if (!bucket.has(key)) bucket.set(key, name);
  }
  // A name classified as both a table and a column keeps only its table slot.
  for (const key of tables.keys()) columns.delete(key);

  const sortedTables = [...tables.values()].sort((a, b) => a.localeCompare(b));
  const sortedColumns = [...columns.values()].sort((a, b) => a.localeCompare(b));

  const map = {};
  sortedTables.forEach((name, i) => {
    map[name] = `table_${suffixFor(i)}`;
  });
  sortedColumns.forEach((name, i) => {
    map[name] = `col_${suffixFor(i)}`;
  });
  return map;
}

// Boundary that treats any non-alphanumeric char (including "_") as a break,
// so "pinacle_id" matches the "pinacle" entry (prefix match) while
// "pinnacle" (not a substring of "pinacle" at all) never does.
function boundaryRegex(term) {
  return new RegExp(`(?<![A-Za-z0-9])${escapeRegExp(term)}(?![A-Za-z0-9])`, 'gi');
}

/** Apply a substitution map to arbitrary text (SQL query or EXPLAIN plan). */
export function sanitize(text, substitutionMap) {
  if (!text || typeof text !== 'string') return text;
  if (!substitutionMap || typeof substitutionMap !== 'object') return text;
  const entries = Object.entries(substitutionMap).sort((a, b) => b[0].length - a[0].length);
  let result = text;
  for (const [original, substituted] of entries) {
    result = result.replace(boundaryRegex(original), substituted);
  }
  return result;
}

/** Reverse a sanitize() call — longest substituted names replaced first. */
export function desanitize(text, substitutionMap) {
  if (!text || typeof text !== 'string') return text;
  if (!substitutionMap || typeof substitutionMap !== 'object') return text;
  const entries = Object.entries(substitutionMap)
    .map(([original, substituted]) => [substituted, original])
    .sort((a, b) => b[0].length - a[0].length);
  let result = text;
  for (const [substituted, original] of entries) {
    result = result.replace(boundaryRegex(substituted), original);
  }
  return result;
}

/**
 * Build the substitution list for the preview UI: [{ original, sanitized }],
 * sorted by where `original` first appears in the source query.
 */
export function buildDiff(original, substitutionMap) {
  if (!original || typeof original !== 'string') return [];
  if (!substitutionMap || typeof substitutionMap !== 'object') return [];
  const lowerOriginal = original.toLowerCase();
  return Object.entries(substitutionMap)
    .map(([orig, sub]) => ({
      original: orig,
      sanitized: sub,
      pos: lowerOriginal.indexOf(orig.toLowerCase()),
    }))
    .filter((e) => e.pos !== -1)
    .sort((a, b) => a.pos - b.pos)
    .map(({ original: orig, sanitized: sub }) => ({ original: orig, sanitized: sub }));
}
