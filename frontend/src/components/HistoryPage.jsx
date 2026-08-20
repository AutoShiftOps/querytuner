/**
 * HistoryPage.jsx — Phase 5 (backlog #54): "Query history" for Pro users.
 *
 * UpgradeModal.jsx has advertised this as a Pro perk since Phase 4
 * (FEATURES array) without the feature existing — this is what backs it.
 * Backend: GET /history (backend/app/main.py), gated server-side the same
 * way /analyze's tier check is (not just this page's own UI).
 *
 * Self-contained styles (own T tokens / injected <style> block, id
 * qt-history-styles) rather than importing ReportPage.jsx's — deliberate:
 * ReportPage.jsx is an already-shipped, public-facing shareable-link
 * surface, and refactoring it to share a theme module with a brand new
 * page isn't worth the risk of a regression there for this. Some
 * duplication of the same design tokens/nav/card classes is the trade-off.
 */

import { useCallback, useEffect, useState } from 'react';
import { useAuth, useUser, SignInButton } from '@clerk/clerk-react';
import axios from 'axios';
import { formatRelativeTime } from '../utils/formatRelativeTime';
import UpgradeModal from './UpgradeModal';

const API_URL =
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api');

const PAGE_SIZE = 20;

// ── Design tokens (mirrors ReportPage.jsx's #0f172a palette) ────────────────
const T = {
  bg: '#0f172a',
  surface: '#1e293b',
  surfaceHigh: '#263347',
  border: '#2d3f55',
  borderBright: '#3b5268',
  text: '#e2e8f0',
  textMuted: '#7fa3c4',
  textDim: '#4a6480',
  accent: '#38bdf8',
  green: '#34d399',
  yellow: '#fbbf24',
  orange: '#f97316',
  red: '#f87171',
};

const SEV = {
  critical: { badge: '#3d1515', text: T.red, label: 'Critical' },
  high: { badge: '#3d2210', text: T.orange, label: 'High' },
  medium: { badge: '#3a2c0a', text: T.yellow, label: 'Medium' },
  low: { badge: '#0d3328', text: T.green, label: 'Low' },
};

function injectStyles() {
  if (document.getElementById('qt-history-styles')) return;
  const style = document.createElement('style');
  style.id = 'qt-history-styles';
  style.textContent = `
    :where(.qt-history *) { box-sizing: border-box; }
    .qt-history {
      font-family: 'IBM Plex Sans', system-ui, sans-serif;
      background: ${T.bg};
      min-height: 100vh;
      color: ${T.text};
    }
    .qt-history-shell { max-width: 760px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    .qt-history-nav {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 1.75rem; margin-bottom: 1.75rem;
      border-bottom: 1px solid ${T.border};
    }
    .qt-history-brand { display: flex; align-items: center; gap: 8px; text-decoration: none; }
    .qt-history-brand-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: ${T.accent}; box-shadow: 0 0 8px ${T.accent};
    }
    .qt-history-brand-name {
      font-size: 13px; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; color: ${T.accent};
    }
    .qt-history-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 6px; font-size: 12px;
      font-weight: 500; cursor: pointer; transition: all 0.15s;
      font-family: inherit; border: none; text-decoration: none;
    }
    .qt-history-btn-primary { background: ${T.accent}; color: #0f172a; font-weight: 600; }
    .qt-history-btn-primary:hover { background: #7dd3fc; }
    .qt-history-btn-ghost { background: transparent; border: 1px solid ${T.border}; color: ${T.textMuted}; }
    .qt-history-btn-ghost:hover { border-color: ${T.borderBright}; color: ${T.text}; }
    .qt-history-title { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 6px; }
    .qt-history-subtitle { font-size: 13px; color: ${T.textMuted}; margin-bottom: 1.75rem; }

    .qt-history-list { display: flex; flex-direction: column; gap: 1px; background: ${T.border}; border: 1px solid ${T.border}; border-radius: 10px; overflow: hidden; }
    .qt-history-row {
      display: block; background: ${T.surface}; padding: 14px 16px;
      text-decoration: none; color: inherit; transition: background 0.12s;
    }
    .qt-history-row:hover { background: ${T.surfaceHigh}; }
    .qt-history-row-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
    .qt-history-chip {
      display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 20px;
      font-size: 10px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .qt-history-chip-db { background: rgba(56,189,248,0.1); color: ${T.accent}; }
    .qt-history-time { font-size: 11px; color: ${T.textDim}; margin-left: auto; }
    .qt-history-query {
      font-family: 'JetBrains Mono', monospace; font-size: 12px; color: ${T.textMuted};
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .qt-history-issues { font-size: 11px; color: ${T.textDim}; margin-top: 4px; }

    .qt-history-state-center {
      display: flex; flex-direction: column; align-items: center; text-align: center;
      justify-content: center; min-height: 50vh; gap: 14px; padding: 2rem 1rem;
    }
    .qt-history-spinner {
      width: 32px; height: 32px; border-radius: 50%;
      border: 2px solid ${T.border}; border-top-color: ${T.accent};
      animation: qt-history-spin 0.7s linear infinite;
    }
    @keyframes qt-history-spin { to { transform: rotate(360deg); } }
    .qt-history-load-more { display: flex; justify-content: center; margin-top: 1.25rem; }
  `;
  document.head.appendChild(style);
}

function Nav() {
  return (
    <nav className="qt-history-nav">
      <a href="/" className="qt-history-brand">
        <div className="qt-history-brand-dot" />
        <span className="qt-history-brand-name">QueryTuner</span>
      </a>
      <a href="/" className="qt-history-btn qt-history-btn-ghost">
        ← Back
      </a>
    </nav>
  );
}

export default function HistoryPage() {
  const { isSignedIn } = useUser();
  const { getToken } = useAuth();

  const [items, setItems] = useState([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [needsPro, setNeedsPro] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  useEffect(() => {
    injectStyles();
  }, []);

  const fetchPage = useCallback(
    async (nextOffset, { append }) => {
      try {
        const token = await getToken();
        const r = await axios.get(`${API_URL}/history`, {
          params: { limit: PAGE_SIZE, offset: nextOffset },
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        setItems((prev) => (append ? [...prev, ...r.data.items] : r.data.items));
        setOffset(nextOffset);
        setHasMore(!!r.data.has_more);
        setError(null);
        setNeedsPro(false);
      } catch (err) {
        if (err.response?.data?.error === 'pro_required') {
          setNeedsPro(true);
          setShowUpgradeModal(true);
        } else {
          setError('Failed to load your history. Please try again.');
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [getToken]
  );

  useEffect(() => {
    if (isSignedIn === undefined) return; // Clerk still resolving auth state
    if (!isSignedIn) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchPage(0, { append: false });
  }, [isSignedIn, fetchPage]);

  const handleLoadMore = () => {
    setLoadingMore(true);
    fetchPage(offset + PAGE_SIZE, { append: true });
  };

  // ── Loading (includes Clerk auth still resolving) ──
  if (loading || isSignedIn === undefined) {
    return (
      <div className="qt-history">
        <div className="qt-history-shell">
          <div className="qt-history-state-center">
            <div className="qt-history-spinner" />
            <span>Loading your history…</span>
          </div>
        </div>
      </div>
    );
  }

  // ── Not signed in ──
  if (!isSignedIn) {
    return (
      <div className="qt-history">
        <div className="qt-history-shell">
          <Nav />
          <div className="qt-history-state-center">
            <h1 className="qt-history-title">Sign in to view your history</h1>
            <p style={{ color: T.textMuted, fontSize: 13 }}>
              Query history is available to signed-in Pro users.
            </p>
            <SignInButton mode="modal">
              <button className="qt-history-btn qt-history-btn-primary">Sign in</button>
            </SignInButton>
          </div>
        </div>
      </div>
    );
  }

  // ── Signed in but not Pro — locked state + reusable UpgradeModal pitch ──
  if (needsPro) {
    return (
      <div className="qt-history">
        <UpgradeModal
          isOpen={showUpgradeModal}
          onClose={() => setShowUpgradeModal(false)}
          title="Query history is a Pro feature"
          subtitle="Upgrade to QueryTuner Pro to see your saved analyses, any time."
        />
        <div className="qt-history-shell">
          <Nav />
          <div className="qt-history-state-center">
            <span style={{ fontSize: 32 }}>🔒</span>
            <h1 className="qt-history-title">Query history is a Pro feature</h1>
            <p style={{ color: T.textMuted, fontSize: 13, maxWidth: 380 }}>
              Upgrade to QueryTuner Pro to see every analysis you&rsquo;ve run, any time.
            </p>
            <button
              className="qt-history-btn qt-history-btn-primary"
              onClick={() => setShowUpgradeModal(true)}
            >
              Upgrade to Pro →
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Generic fetch error — only full-page when the INITIAL load failed.
  // A failed "Load more" (items.length > 0 already) shouldn't blow away
  // the rows already on screen; that's handled inline near the button
  // further down instead. ──
  if (error && items.length === 0) {
    return (
      <div className="qt-history">
        <div className="qt-history-shell">
          <Nav />
          <div className="qt-history-state-center">
            <span style={{ fontSize: 32 }}>⚠</span>
            <span style={{ color: T.textMuted }}>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  // ── Empty state — every current Pro user starts with zero rows ──
  if (items.length === 0) {
    return (
      <div className="qt-history">
        <div className="qt-history-shell">
          <Nav />
          <h1 className="qt-history-title">Query history</h1>
          <p className="qt-history-subtitle">Your analyses will show up here.</p>
          <div className="qt-history-state-center">
            <span style={{ fontSize: 32 }}>📋</span>
            <span style={{ color: T.textMuted }}>
              No analyses yet — run one and it&rsquo;ll appear here.
            </span>
            <a href="/" className="qt-history-btn qt-history-btn-primary">
              Analyze a query →
            </a>
          </div>
        </div>
      </div>
    );
  }

  // ── List ──
  return (
    <div className="qt-history">
      <div className="qt-history-shell">
        <Nav />
        <h1 className="qt-history-title">Query history</h1>
        <p className="qt-history-subtitle">
          {items.length} analys{items.length !== 1 ? 'es' : 'is'} shown
        </p>

        <div className="qt-history-list">
          {items.map((item) => {
            const sevKey = (item.severity || 'low').toLowerCase();
            const sevCfg = SEV[sevKey] || SEV.low;
            return (
              <a key={item.id} href={`/report/${item.id}`} className="qt-history-row">
                <div className="qt-history-row-top">
                  <span className="qt-history-chip qt-history-chip-db">
                    {(item.db_type || 'sql').toUpperCase()}
                  </span>
                  <span
                    className="qt-history-chip"
                    style={{ background: sevCfg.badge, color: sevCfg.text }}
                  >
                    {sevCfg.label}
                  </span>
                  <span className="qt-history-time">{formatRelativeTime(item.created_at)}</span>
                </div>
                <div className="qt-history-query">{item.query_snippet}</div>
                <div className="qt-history-issues">
                  {item.issue_count} issue{item.issue_count !== 1 ? 's' : ''} found
                </div>
              </a>
            );
          })}
        </div>

        {error && (
          <p style={{ color: T.red, fontSize: 12, textAlign: 'center', marginTop: 12 }}>{error}</p>
        )}

        {hasMore && (
          <div className="qt-history-load-more">
            <button
              className="qt-history-btn qt-history-btn-ghost"
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
