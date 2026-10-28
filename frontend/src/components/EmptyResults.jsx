import { ListChecks, Database, Wand2, ShieldAlert, Link2 } from 'lucide-react';

// Empty state of the results panel. Before the first run the right half of the
// page is otherwise blank, so it shows what a run produces (this used to be a
// row of chips in the hero, pushing the editor below the fold).
const ITEMS = [
  {
    icon: ListChecks,
    title: 'Prioritised findings',
    text: 'Severity-ranked issues with evidence levels',
  },
  {
    icon: Database,
    title: 'Index DDL with rollback',
    text: 'Dialect-correct CREATE and DROP statements',
  },
  {
    icon: Wand2,
    title: 'Rewrite or targeted fixes',
    text: 'Same-result rewrites, checked before showing',
  },
  {
    icon: ShieldAlert,
    title: 'Security notes',
    text: 'Injection risks, multi-statement input, comments',
  },
  { icon: Link2, title: 'Shareable report', text: 'A permanent link, plus a /analyze API' },
];

export default function EmptyResults() {
  return (
    <div
      className="rounded-xl px-6 py-6"
      style={{ background: '#1e293b', border: '1px dashed #2d3f55' }}
    >
      <p className="text-xs uppercase tracking-wider mb-4" style={{ color: '#4a6480' }}>
        What you get
      </p>
      <ul className="grid gap-4 sm:grid-cols-2">
        {ITEMS.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3 items-start">
            <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#38bdf8' }} />
            <div>
              <p className="text-sm font-medium" style={{ color: '#e2e8f0' }}>
                {title}
              </p>
              <p className="text-xs mt-0.5" style={{ color: '#7fa3c4' }}>
                {text}
              </p>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-sm mt-6 pt-4" style={{ color: '#7fa3c4', borderTop: '1px solid #2d3f55' }}>
        Paste a query and press{' '}
        <kbd
          className="px-2 py-0.5 rounded text-xs font-mono"
          style={{ background: '#0f172a', border: '1px solid #2d3f55', color: '#7fa3c4' }}
        >
          ⌘ Enter
        </kbd>{' '}
        or <strong style={{ color: '#e2e8f0' }}>Run Diagnostics</strong>, or pick a sample on the
        left.
      </p>
    </div>
  );
}
