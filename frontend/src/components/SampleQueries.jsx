import { useState } from 'react';
import { ChevronDown, ChevronUp, FlaskConical } from 'lucide-react';

const SAMPLE_QUERIES = [
  {
    category: 'Beginner',
    color: 'emerald',
    queries: [
      {
        label: 'SELECT * — Column Selection',
        db: 'postgresql',
        description: 'Classic SELECT * anti-pattern — triggers column selection warning',
        sql: 'SELECT *\nFROM users;',
      },
      {
        label: 'Missing WHERE Clause',
        db: 'mysql',
        description: 'Full table scan risk on a large table',
        sql: 'SELECT id, email, created_at\nFROM orders;',
      },
      {
        label: 'Simple Indexed Lookup',
        db: 'postgresql',
        description: 'Well-written query — low complexity, should score clean',
        sql: 'SELECT id, name, email\nFROM users\nWHERE id = 42;',
      },
    ],
  },
  {
    category: 'Intermediate',
    color: 'yellow',
    queries: [
      {
        label: 'LIKE with Leading Wildcard',
        db: 'postgresql',
        description: 'Leading % prevents index use — triggers wildcard warning',
        sql: "SELECT id, name\nFROM products\nWHERE name LIKE '%phone';",
      },
      {
        label: 'Function in WHERE Clause',
        db: 'mysql',
        description: 'YEAR() on a column breaks index seeks',
        sql: "SELECT id, user_id, total\nFROM orders\nWHERE YEAR(created_at) = 2024\n  AND status = 'completed';",
      },
      {
        label: 'ORDER BY Without LIMIT',
        db: 'postgresql',
        description: 'Unbounded sort on a large result set',
        sql: 'SELECT u.id, u.name, COUNT(o.id) AS order_count\nFROM users u\nJOIN orders o ON o.user_id = u.id\nGROUP BY u.id, u.name\nORDER BY order_count DESC;',
      },
    ],
  },
  {
    category: 'Advanced',
    color: 'orange',
    queries: [
      {
        label: 'Multi-Join with Subquery',
        db: 'postgresql',
        description: 'Complex query with subquery + multiple joins + GROUP BY',
        sql: `SELECT
  u.id,
  u.name,
  u.email,
  recent.last_order_date,
  COUNT(oi.id) AS total_items
FROM users u
JOIN orders o ON o.user_id = u.id
JOIN order_items oi ON oi.order_id = o.id
JOIN (
  SELECT user_id, MAX(created_at) AS last_order_date
  FROM orders
  GROUP BY user_id
) recent ON recent.user_id = u.id
WHERE YEAR(o.created_at) = 2024
  AND u.status = 'active'
GROUP BY u.id, u.name, u.email, recent.last_order_date
ORDER BY total_items DESC;`,
      },
      {
        label: 'N+1 Pattern (Correlated Subquery)',
        db: 'postgresql',
        description: 'Correlated subquery in SELECT — classic N+1 problem',
        sql: `SELECT
  p.id,
  p.name,
  p.price,
  (SELECT COUNT(*) FROM order_items oi WHERE oi.product_id = p.id) AS times_ordered,
  (SELECT AVG(r.rating) FROM reviews r WHERE r.product_id = p.id) AS avg_rating
FROM products p
WHERE p.category = 'electronics'
ORDER BY times_ordered DESC;`,
      },
      {
        label: 'SQL Injection Risk',
        db: 'mysql',
        description: 'Tests security detection — UNION-based injection pattern',
        sql: `SELECT id, username, email
FROM users
WHERE username = 'admin' -- '
  OR 1=1
UNION SELECT table_name, null, null
FROM information_schema.tables;`,
      },
    ],
  },
];

const colorMap = {
  emerald: {
    badge: 'bg-emerald-900/40 text-emerald-400 border border-emerald-700',
    dot: 'bg-emerald-400',
    hover: 'hover:border-emerald-600',
  },
  yellow: {
    badge: 'bg-yellow-900/40 text-yellow-400 border border-yellow-700',
    dot: 'bg-yellow-400',
    hover: 'hover:border-yellow-600',
  },
  orange: {
    badge: 'bg-orange-900/40 text-orange-400 border border-orange-700',
    dot: 'bg-orange-400',
    hover: 'hover:border-orange-600',
  },
};

export default function SampleQueries({ onSelect }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mb-4 rounded-lg border border-slate-700 bg-slate-800/50">
      {/* Header toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left
                   hover:bg-slate-700/40 transition-colors rounded-lg"
      >
        <div className="flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-slate-300">Try a Sample Query</span>
          <span className="text-xs text-slate-500 ml-1">— 9 examples from simple to complex</span>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>

      {/* Content */}
      {open && (
        <div className="px-5 pb-5 pt-1 space-y-5">
          {SAMPLE_QUERIES.map(({ category, color, queries }) => {
            const c = colorMap[color];
            return (
              <div key={category}>
                {/* Category badge */}
                <div className="flex items-center gap-2 mb-3">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${c.badge}`}>
                    {category}
                  </span>
                </div>

                {/* Query cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {queries.map((q) => (
                    <button
                      key={q.label}
                      onClick={() => {
                        onSelect(q.sql, q.db);
                        setOpen(false);
                      }}
                      className={`text-left p-3 rounded-lg bg-slate-900/60 border border-slate-700
                                  ${c.hover} hover:bg-slate-900 transition-all group`}
                    >
                      <div className="flex items-start gap-2 mb-1">
                        <span
                          className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`}
                        />
                        <span className="text-xs font-semibold text-white leading-tight">
                          {q.label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 ml-3.5 leading-relaxed">
                        {q.description}
                      </p>
                      <div className="mt-2 ml-3.5">
                        <pre className="text-xs text-slate-500 truncate font-mono">
                          {q.sql.split('\n')[0]}...
                        </pre>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}

          <p className="text-xs text-slate-500 pt-1">
            Click any query to load it into the editor, then hit{' '}
            <strong className="text-slate-400">Analyze</strong>.
          </p>
        </div>
      )}
    </div>
  );
}
