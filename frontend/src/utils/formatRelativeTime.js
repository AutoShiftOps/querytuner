/**
 * Formats an ISO timestamp as a short relative string ("2h ago", "3d ago")
 * for the History page's list rows — created_at is the only timestamp
 * GET /history returns per row (backend/app/utils/database.py's
 * get_analysis_history), and a relative label reads faster in a scanning
 * list than a full date would.
 *
 * `now` is injectable (defaults to `new Date()`) so tests don't depend on
 * wall-clock time.
 */
export function formatRelativeTime(isoString, now = new Date()) {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';

  const diffSec = Math.round((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;

  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;

  const diffDay = Math.round(diffHour / 24);
  if (diffDay < 30) return `${diffDay}d ago`;

  const diffMonth = Math.round(diffDay / 30);
  if (diffMonth < 12) return `${diffMonth}mo ago`;

  const diffYear = Math.round(diffMonth / 12);
  return `${diffYear}y ago`;
}
