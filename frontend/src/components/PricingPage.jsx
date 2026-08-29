/**
 * PricingPage.jsx — Issue #51: dedicated /pricing route with a Free vs Pro
 * feature comparison table + Stripe Checkout CTA for the Pro tier.
 *
 * Market-standard shape for this kind of page (Stripe, Linear, Vercel,
 * Notion all do the same two-part layout): pricing cards up top for an
 * at-a-glance choice + price, a detailed feature-by-feature comparison
 * table below for anyone who wants to dig in — rather than just a bullet
 * list (UpgradeModal.jsx's shape, which stays as the in-context upgrade
 * nudge; this is the standalone, linkable, SEO-visible page that never
 * existed before).
 *
 * Every row in the comparison table below is a REAL, currently-enforced
 * entitlement verified against this session's own audit work — not
 * copied from the original issue's wording (which the Phase 4 audit
 * already found doesn't always match what shipped). Notably: schema-aware
 * analysis and EXPLAIN plan cross-referencing are NOT Pro-gated anywhere
 * in the code (confirmed via grep — QueryInput.jsx's schema/EXPLAIN
 * textareas have no sign-in or isPro check at all), so this page doesn't
 * claim otherwise just because an early issue once said "no schema" on
 * free tier. A pricing page that oversells what's actually gated is worse
 * than a plain one. The "Batch workload analysis" row briefly carried a
 * `note: 'API only...'` caveat (added ahead of DZone launch traffic, when
 * #115/#120's backend-only v1 scope meant a bare checkmark there would
 * have overpromised parity with Quiz Mode/Query history) — removed once
 * BatchAnalysisPage.jsx (/batch) actually shipped that parity.
 *
 * Self-contained styles (own T tokens / injected <style> block) rather
 * than importing Header.jsx or another page's styles — same rationale
 * HistoryPage.jsx's own docstring already gives for this codebase: this
 * page has its own identity and a shared theme module isn't worth the
 * risk of a regression elsewhere for the amount of duplication saved.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth, useUser, SignUpButton } from '@clerk/clerk-react';
import { Check, Minus } from 'lucide-react';
import axios from 'axios';
import { trackPageView } from '../utils/analytics';

const API_URL =
  import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api');

// Same reasoning as UpgradeModal.jsx's own PAYMENT_LINK constant — there is
// no real Stripe Payment Link without one being created in the Stripe
// dashboard first, so a missing env var degrades to a disabled CTA with an
// explicit note instead of a silently-404ing button.
const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';

// ── Design tokens (mirrors HistoryPage.jsx / ReportPage.jsx's #0f172a palette) ──
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
  red: '#f87171',
};

// The actual comparison table — every row verified against real,
// currently-enforced code, not the original issue's wording. See this
// file's own module docstring for the specific things that turned out
// NOT to be gated (schema-aware analysis, EXPLAIN cross-referencing).
const FEATURE_ROWS = [
  { label: 'Analyses', free: '10 / month', pro: 'Unlimited' },
  { label: 'Max query length', free: '8,000 characters', pro: '32,000 characters' },
  { label: 'Heuristic engine (24 checks, evidence-tiered)', free: true, pro: true },
  { label: 'Schema-aware index recommendations', free: true, pro: true },
  { label: 'EXPLAIN plan cross-referencing', free: true, pro: true },
  { label: 'Quiz Mode', free: true, pro: true },
  { label: 'Shareable report links', free: true, pro: true },
  { label: 'AI Insights provider', free: 'Hugging Face', pro: 'Hugging Face + OpenAI GPT-4o-mini' },
  { label: 'Query history', free: false, pro: true },
  // BatchAnalysisPage.jsx (/batch, linked from the header nav) closed the
  // gap PR #167's caveat note flagged here — #115/#120 shipped backend-only
  // originally (docs/querytuner-batch-analysis-issue.md), so this row used
  // to carry a `note: 'API only...'` distinguishing it from Quiz Mode/Query
  // history, which a Pro user could actually find in the app. Removed now
  // that this one can make the same claim.
  { label: 'Batch workload analysis (Query Store / pg_stat_statements)', free: false, pro: true },
];

function injectStyles() {
  if (document.getElementById('qt-pricing-styles')) return;
  const style = document.createElement('style');
  style.id = 'qt-pricing-styles';
  style.textContent = `
    :where(.qt-pricing *) { box-sizing: border-box; }
    .qt-pricing {
      font-family: 'IBM Plex Sans', system-ui, sans-serif;
      background: ${T.bg};
      min-height: 100vh;
      color: ${T.text};
    }
    .qt-pricing-shell { max-width: 900px; margin: 0 auto; padding: 2.5rem 1.25rem 5rem; }
    .qt-pricing-nav {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 1.75rem; margin-bottom: 2.5rem;
      border-bottom: 1px solid ${T.border};
    }
    .qt-pricing-brand { display: flex; align-items: center; gap: 8px; text-decoration: none; }
    .qt-pricing-brand-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: ${T.accent}; box-shadow: 0 0 8px ${T.accent};
    }
    .qt-pricing-brand-name {
      font-size: 13px; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; color: ${T.accent};
    }
    .qt-pricing-btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      padding: 6px 14px; border-radius: 6px; font-size: 12px;
      font-weight: 500; cursor: pointer; transition: all 0.15s;
      font-family: inherit; border: none; text-decoration: none;
    }
    .qt-pricing-btn-ghost { background: transparent; border: 1px solid ${T.border}; color: ${T.textMuted}; }
    .qt-pricing-btn-ghost:hover { border-color: ${T.borderBright}; color: ${T.text}; }

    .qt-pricing-hero { text-align: center; margin-bottom: 3rem; }
    .qt-pricing-title { font-size: 32px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 10px; }
    .qt-pricing-subtitle { font-size: 15px; color: ${T.textMuted}; max-width: 480px; margin: 0 auto; }

    .qt-pricing-cards {
      display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 3.5rem;
    }
    @media (max-width: 640px) { .qt-pricing-cards { grid-template-columns: 1fr; } }
    .qt-pricing-card {
      background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 14px;
      padding: 28px; display: flex; flex-direction: column;
    }
    .qt-pricing-card-pro { border-color: ${T.accent}; box-shadow: 0 0 0 1px ${T.accent}; }
    .qt-pricing-card-badge {
      display: inline-flex; align-self: flex-start; padding: 3px 10px; border-radius: 20px;
      font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
      background: rgba(56,189,248,0.12); color: ${T.accent}; margin-bottom: 14px;
    }
    .qt-pricing-card-tier { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
    .qt-pricing-card-blurb { font-size: 13px; color: ${T.textMuted}; margin-bottom: 20px; min-height: 34px; }
    .qt-pricing-card-price { display: flex; align-items: baseline; gap: 5px; margin-bottom: 22px; }
    .qt-pricing-card-price-amount { font-size: 34px; font-weight: 700; }
    .qt-pricing-card-price-period { font-size: 13px; color: ${T.textMuted}; }
    .qt-pricing-card-cta {
      display: block; text-align: center; padding: 11px 16px; border-radius: 8px;
      font-weight: 600; font-size: 14px; text-decoration: none; border: none;
      cursor: pointer; font-family: inherit; margin-top: auto;
    }
    .qt-pricing-card-cta-primary { background: ${T.accent}; color: #0f172a; }
    .qt-pricing-card-cta-primary:hover { background: #7dd3fc; }
    .qt-pricing-card-cta-secondary { background: transparent; border: 1px solid ${T.border}; color: ${T.text}; }
    .qt-pricing-card-cta-secondary:hover { border-color: ${T.borderBright}; }
    .qt-pricing-card-cta:disabled { opacity: 0.5; cursor: not-allowed; }
    .qt-pricing-card-note { font-size: 11px; color: ${T.textDim}; margin-top: 8px; text-align: center; }
    .qt-pricing-card-active {
      display: block; text-align: center; padding: 11px 16px; border-radius: 8px;
      font-weight: 600; font-size: 14px; margin-top: auto;
      background: rgba(52,211,153,0.1); color: ${T.green}; border: 1px solid rgba(52,211,153,0.3);
    }

    .qt-pricing-table-title { font-size: 20px; font-weight: 600; margin-bottom: 1.25rem; }
    .qt-pricing-table-wrap { overflow-x: auto; border: 1px solid ${T.border}; border-radius: 12px; }
    .qt-pricing-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 480px; table-layout: fixed; }
    .qt-pricing-table th, .qt-pricing-table td {
      padding: 12px 16px; text-align: left; border-bottom: 1px solid ${T.border};
    }
    .qt-pricing-table th {
      color: ${T.textMuted}; font-weight: 600; font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.04em; background: ${T.surfaceHigh};
      border-bottom: 1px solid ${T.borderBright};
    }
    /* Real column grid — a vertical rule per value column, not just row
       dividers, so this reads as a table at a glance instead of three
       loosely-aligned text columns. */
    .qt-pricing-table th:not(:first-child), .qt-pricing-table td:not(:first-child) {
      text-align: center; width: 160px; border-left: 1px solid ${T.border};
    }
    /* Pro column gets a faint accent tint, tying it back to the highlighted
       "Recommended" pricing card above instead of looking identical to Free. */
    .qt-pricing-table th:last-child, .qt-pricing-table td:last-child {
      background: rgba(56,189,248,0.05);
    }
    .qt-pricing-table th:last-child { background: rgba(56,189,248,0.1); }
    .qt-pricing-table tbody tr:nth-child(even) td:first-child,
    .qt-pricing-table tbody tr:nth-child(even) td:not(:first-child):not(:last-child) {
      background: rgba(255,255,255,0.025);
    }
    .qt-pricing-table tbody tr:last-child td { border-bottom: none; }
    .qt-pricing-table tbody tr:hover td { background: ${T.surfaceHigh}; }
    .qt-pricing-table td:first-child { color: ${T.text}; }
  `;
  document.head.appendChild(style);
}

function Nav() {
  return (
    <nav className="qt-pricing-nav">
      <Link to="/" className="qt-pricing-brand">
        <div className="qt-pricing-brand-dot" />
        <span className="qt-pricing-brand-name">QueryTuner</span>
      </Link>
      <Link to="/" className="qt-pricing-btn qt-pricing-btn-ghost">
        ← Back
      </Link>
    </nav>
  );
}

function FeatureCell({ value }) {
  if (value === true) return <Check size={16} style={{ color: T.green }} />;
  if (value === false) return <Minus size={16} style={{ color: T.textDim }} />;
  return <span style={{ color: T.text }}>{value}</span>;
}

export default function PricingPage() {
  const { isSignedIn, user } = useUser();
  const { getToken } = useAuth();
  const [isPro, setIsPro] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    injectStyles();
    trackPageView('/pricing', 'QueryTuner — Pricing');
  }, []);

  // Same GET /usage authoritative-Pro-status pattern App.jsx/HistoryPage.jsx
  // already use — a page offering to sell someone something they already
  // bought should know that before rendering the "Upgrade" button.
  useEffect(() => {
    if (!isSignedIn) return;
    (async () => {
      try {
        const token = await getToken();
        const r = await axios.get(`${API_URL}/usage`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        setIsPro(!!r.data?.is_pro);
      } catch {
        // Fall back to showing the upgrade CTA — worse case is a Pro user
        // sees an upgrade button they don't need, not a broken page.
      }
    })();
  }, [isSignedIn, getToken]);

  // Mirrors Header.jsx's own handleManageSubscription — same endpoint,
  // same redirect-to-Stripe-hosted-portal pattern, just no showToast prop
  // to report a failure through on this standalone page, so a plain
  // inline note substitutes.
  const [portalError, setPortalError] = useState(null);
  const handleManageSubscription = async () => {
    setPortalLoading(true);
    setPortalError(null);
    try {
      const token = await getToken();
      const r = await axios.post(
        `${API_URL}/billing-portal`,
        {},
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      window.location.href = r.data.url;
    } catch (err) {
      setPortalError(
        err.response?.data?.detail || "Couldn't open billing portal — please try again shortly."
      );
      setPortalLoading(false);
    }
  };

  // Same client_reference_id mechanism as UpgradeModal.jsx — the backend
  // webhook (POST /webhook/stripe) reads it off checkout.session.completed
  // to link this Clerk user to the Stripe customer that was just created.
  const paymentUrl =
    PAYMENT_LINK && user?.id
      ? `${PAYMENT_LINK}${
          PAYMENT_LINK.includes('?') ? '&' : '?'
        }client_reference_id=${encodeURIComponent(user.id)}`
      : PAYMENT_LINK;

  return (
    <div className="qt-pricing">
      <div className="qt-pricing-shell">
        <Nav />

        <div className="qt-pricing-hero">
          <h1 className="qt-pricing-title">Simple, transparent pricing</h1>
          <p className="qt-pricing-subtitle">
            Start free. Upgrade when you need unlimited analyses, query history, and OpenAI-powered
            insights.
          </p>
        </div>

        <div className="qt-pricing-cards">
          {/* ── Free ── */}
          <div className="qt-pricing-card">
            <div className="qt-pricing-card-tier">Free</div>
            <p className="qt-pricing-card-blurb">For trying QueryTuner out or occasional use.</p>
            <div className="qt-pricing-card-price">
              <span className="qt-pricing-card-price-amount">$0</span>
              <span className="qt-pricing-card-price-period">/month</span>
            </div>
            <Link to="/" className="qt-pricing-card-cta qt-pricing-card-cta-secondary">
              Get started free →
            </Link>
          </div>

          {/* ── Pro ── */}
          <div className="qt-pricing-card qt-pricing-card-pro">
            <span className="qt-pricing-card-badge">Recommended</span>
            <div className="qt-pricing-card-tier">Pro</div>
            <p className="qt-pricing-card-blurb">
              For engineers running this regularly on real work.
            </p>
            <div className="qt-pricing-card-price">
              <span className="qt-pricing-card-price-amount">$19</span>
              <span className="qt-pricing-card-price-period">/month</span>
            </div>

            {isPro ? (
              <>
                <div className="qt-pricing-card-active">You&rsquo;re on Pro ✓</div>
                <button
                  onClick={handleManageSubscription}
                  disabled={portalLoading}
                  className="qt-pricing-card-cta qt-pricing-card-cta-secondary"
                  style={{ marginTop: 10 }}
                >
                  {portalLoading ? 'Opening…' : 'Manage subscription'}
                </button>
                {portalError && (
                  <p className="qt-pricing-card-note" style={{ color: T.red }}>
                    {portalError}
                  </p>
                )}
              </>
            ) : isSignedIn ? (
              PAYMENT_LINK ? (
                <a
                  href={paymentUrl}
                  rel="noopener noreferrer"
                  className="qt-pricing-card-cta qt-pricing-card-cta-primary"
                >
                  Upgrade to Pro →
                </a>
              ) : (
                <>
                  <button disabled className="qt-pricing-card-cta qt-pricing-card-cta-primary">
                    Upgrade to Pro →
                  </button>
                  <p className="qt-pricing-card-note">Payment link not configured yet.</p>
                </>
              )
            ) : (
              <SignUpButton mode="modal">
                <button className="qt-pricing-card-cta qt-pricing-card-cta-primary">
                  Sign up to upgrade →
                </button>
              </SignUpButton>
            )}
          </div>
        </div>

        <h2 className="qt-pricing-table-title">Compare plans</h2>
        <div className="qt-pricing-table-wrap">
          <table className="qt-pricing-table">
            <thead>
              <tr>
                <th>Feature</th>
                <th>Free</th>
                <th>Pro</th>
              </tr>
            </thead>
            <tbody>
              {FEATURE_ROWS.map((row) => (
                <tr key={row.label}>
                  <td>
                    {row.label}
                    {row.note && (
                      <div style={{ fontSize: 11, color: T.textDim, marginTop: 2 }}>{row.note}</div>
                    )}
                  </td>
                  <td>
                    <FeatureCell value={row.free} />
                  </td>
                  <td>
                    <FeatureCell value={row.pro} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
