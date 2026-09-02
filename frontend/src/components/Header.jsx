import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  SignedIn,
  SignedOut,
  UserButton,
  SignInButton,
  SignUpButton,
  useAuth,
} from '@clerk/clerk-react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Mirrors UpgradeModal.jsx / PricingPage.jsx's CHECKOUT_ENABLED — same
// explicit opt-in flag, so "Manage subscription" (which opens a real
// Stripe billing portal session) comes back automatically whenever real
// checkout does, instead of needing a second flag remembered separately.
const CHECKOUT_ENABLED = (import.meta.env.VITE_PRO_CHECKOUT_ENABLED || '').toLowerCase() === 'true';

// Official GitHub Buttons widget (buttons.github.io) — renders a live star
// count + one-click star action inside a cross-origin iframe. Loaded once,
// async+defer, so it never blocks first paint. The script itself watches
// the DOM for `.github-button` elements (it doesn't require being loaded
// before the markup exists), so a plain one-time inject in an effect is
// enough even though React owns the DOM.
const GITHUB_BUTTONS_SCRIPT_ID = 'gh-buttons-widget-script';

function injectGithubButtonsScript() {
  if (document.getElementById(GITHUB_BUTTONS_SCRIPT_ID)) return;
  const script = document.createElement('script');
  script.id = GITHUB_BUTTONS_SCRIPT_ID;
  script.src = 'https://buttons.github.io/buttons.js';
  script.async = true;
  script.defer = true;
  document.body.appendChild(script);
}

export default function Header({ isPro = false, showToast } = {}) {
  useEffect(() => {
    injectGithubButtonsScript();
  }, []);

  const { getToken } = useAuth();
  const [portalLoading, setPortalLoading] = useState(false);

  // POST /billing-portal, then redirect the browser to the Stripe-hosted
  // Billing Portal session it returns — no custom billing UI in this app.
  // Only ever called from the "Manage subscription" link below, which only
  // renders for isPro users, but the backend can still legitimately 400
  // (e.g. is_pro and stripe_customer_id are tracked independently — see
  // get_user_stripe_customer_id's docstring in backend/app/utils/database.py)
  // or fail outright, so this doesn't let a raw error surface either way.
  const handleManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const token = await getToken();
      const r = await axios.post(
        `${API_BASE_URL}/billing-portal`,
        {},
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      window.location.href = r.data.url;
    } catch (err) {
      const message =
        err.response?.data?.detail || "Couldn't open billing portal — please try again shortly.";
      showToast?.(message, 'error');
      setPortalLoading(false);
    }
    // No finally-reset on success: navigating away makes it moot, and
    // leaving the button in its loading state until then avoids a second
    // click firing a duplicate portal-session request mid-redirect.
  };

  return (
    <>
      <style>{`
        .qt-header {
          position: sticky; top: 0; z-index: 50;
          background: #0f172a;
          border-bottom: 1px solid #1e3a5f;
          height: 48px;
          display: flex; align-items: center;
          justify-content: space-between;
          padding: 0 20px;
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
        }
        .qt-header-brand {
          display: flex; align-items: center; gap: 8px;
          text-decoration: none;
        }
        .qt-header-logo {
          width: 22px; height: 22px; border-radius: 5px;
          display: block;
        }
        .qt-header-name {
          font-size: 13px; font-weight: 600;
          letter-spacing: 0.06em; text-transform: uppercase;
          color: #38bdf8;
        }
        .qt-header-version {
          font-size: 9px; font-weight: 600;
          padding: 2px 6px; border-radius: 4px;
          background: rgba(56,189,248,0.1);
          color: #38bdf8;
          border: 1px solid rgba(56,189,248,0.2);
          text-transform: uppercase; letter-spacing: 0.04em;
          margin-left: 2px;
        }
        /* Same pill/accent-color language as .qt-header-version above, on
           the signed-in user's own tier rather than the app's version —
           separate class (not .qt-header-pro, which is the filled "Sign up
           free" CTA button) since this is a small badge, not a button. */
        .qt-header-pro-badge {
          font-size: 9px; font-weight: 600;
          padding: 2px 6px; border-radius: 4px;
          background: rgba(56,189,248,0.1);
          color: #38bdf8;
          border: 1px solid rgba(56,189,248,0.2);
          text-transform: uppercase; letter-spacing: 0.04em;
          margin-right: 6px;
        }
        .qt-header-nav {
          display: flex; align-items: center; gap: 2px;
        }
        .qt-header-link {
          font-size: 12px; color: #7fa3c4;
          padding: 5px 10px; border-radius: 5px;
          cursor: pointer; text-decoration: none;
          transition: color 0.15s, background 0.15s;
          white-space: nowrap;
        }
        .qt-header-link:hover {
          color: #e2e8f0; background: #1e293b;
        }
        .qt-header-manage-sub {
          background: none; border: none;
          font-family: inherit;
        }
        .qt-header-manage-sub:disabled {
          opacity: 0.5; cursor: default;
        }
        .qt-header-divider {
          width: 1px; height: 18px; background: #1e3a5f; margin: 0 4px;
        }
        .qt-header-btn {
          font-size: 12px; font-weight: 500;
          padding: 5px 12px; border-radius: 6px;
          cursor: pointer; font-family: 'IBM Plex Sans', system-ui, sans-serif;
          transition: all 0.15s; border: none;
        }
        .qt-header-signin {
          background: transparent;
          border: 1px solid #2d3f55 !important;
          color: #7fa3c4;
          margin-left: 4px;
        }
        .qt-header-signin:hover { border-color: #3b5268 !important; color: #e2e8f0; }
        .qt-header-pro {
          background: #38bdf8; color: #0f172a;
          font-weight: 600; margin-left: 6px;
        }
        .qt-header-pro:hover { background: #7dd3fc; }
        .qt-header-star {
          display: inline-flex; align-items: center;
          margin-left: 6px; line-height: 0;
        }
        @media (max-width: 640px) {
          .qt-header-hide-mobile { display: none; }
          .qt-header-signin { display: none; }
        }
      `}</style>

      <header className="qt-header">
        <a href="/" className="qt-header-brand">
          <img src="/querytuner-mark.svg" alt="QueryTuner logo" className="qt-header-logo" />
          <span className="qt-header-name">QueryTuner</span>
          <span className="qt-header-version">v0.3.0</span>
        </a>

        <nav className="qt-header-nav">
          {/* Issue #51: the dedicated /pricing route's only entry point in
              the main nav — shown to everyone regardless of sign-in state,
              same as every other link in this row. */}
          <Link to="/pricing" className="qt-header-link qt-header-hide-mobile">
            Pricing
          </Link>
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            API Docs
          </a>
          <a
            href="https://github.com/AutoShiftOps/querytuner"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            GitHub
          </a>
          <a
            href="https://github.com/AutoShiftOps/querytuner/blob/master/ROADMAP.md"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            Roadmap
          </a>

          <div className="qt-header-divider qt-header-hide-mobile" />

          {/* Phase 4: Clerk auth. Re-uses the existing .qt-header-signin /
              .qt-header-pro button styles so signed-out and signed-in states
              stay visually consistent with the rest of the header instead of
              introducing a second, duplicated inline style. */}
          <SignedOut>
            <SignInButton mode="modal">
              <button className="qt-header-btn qt-header-signin">Sign in</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="qt-header-btn qt-header-pro">Sign up free</button>
            </SignUpButton>
          </SignedOut>
          <SignedIn>
            <span style={{ marginLeft: 8, display: 'inline-flex', alignItems: 'center' }}>
              {/* Phase 5 (backlog #54): shown to every signed-in user, Pro
                  or not — unlike "Manage subscription" below, which is
                  Pro-only. A free user who clicks through lands on
                  HistoryPage.jsx's own locked state (reuses UpgradeModal's
                  pitch) rather than the link disappearing outright; the
                  data itself is still gated server-side by GET /history
                  regardless of what this link does. */}
              <a href="/history" className="qt-header-link qt-header-hide-mobile">
                History
              </a>
              {/* Phase 5 (#115/#120): same always-shown, page-locks-itself
                  pattern as History above — a free user who clicks through
                  lands on BatchAnalysisPage.jsx's own locked state rather
                  than the link disappearing outright. The pricing page's
                  Batch workload analysis row (PR #167's caveat note)
                  should have its "API only" note removed now that this
                  exists. */}
              <a href="/batch" className="qt-header-link qt-header-hide-mobile">
                Batch
              </a>
              <div className="qt-header-divider qt-header-hide-mobile" />
              {isPro && (
                <>
                  <span className="qt-header-pro-badge">Pro</span>
                  {CHECKOUT_ENABLED && (
                    <button
                      onClick={handleManageSubscription}
                      disabled={portalLoading}
                      className="qt-header-link qt-header-hide-mobile qt-header-manage-sub"
                    >
                      {portalLoading ? 'Opening…' : 'Manage subscription'}
                    </button>
                  )}
                  <div className="qt-header-divider qt-header-hide-mobile" />
                </>
              )}
              <UserButton
                appearance={{
                  elements: {
                    avatarBox: {
                      width: 32,
                      height: 32,
                    },
                  },
                }}
              />
            </span>
          </SignedIn>
          <span className="qt-header-star">
            <a
              className="github-button"
              href="https://github.com/AutoShiftOps/querytuner"
              data-icon="octicon-star"
              data-show-count="true"
              aria-label="Star AutoShiftOps/querytuner on GitHub"
            >
              Star
            </a>
          </span>
        </nav>
      </header>
    </>
  );
}
