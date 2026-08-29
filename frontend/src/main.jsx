import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ClerkProvider } from '@clerk/clerk-react';
import { dark } from '@clerk/themes';
import * as Sentry from '@sentry/react';
import ReportPage from './components/ReportPage';
import HistoryPage from './components/HistoryPage';
import PricingPage from './components/PricingPage';
import BatchAnalysisPage from './components/BatchAnalysisPage';
import App from './App';

// Phase 5 (#135): error tracking — same degrades-gracefully pattern as the
// backend's SENTRY_DSN (app/main.py) and this file's own PAYMENT_LINK
// precedent elsewhere: no VITE_SENTRY_DSN, no Sentry.init() call, zero
// behavior change. Deliberately not gating app render on this the way
// PUBLISHABLE_KEY below does — losing error visibility should never mean
// losing the app itself.
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    // Light session/error sampling, not full session replay — keeps a
    // free-tier Sentry project's event quota mostly for what actually
    // matters: errors. Matches the backend's traces_sample_rate=0.1.
    tracesSampleRate: 0.1,
  });
}

// Phase 4: Clerk auth — publishable key is safe to expose client-side by
// design, but the app has no usable auth without it, so fail fast rather
// than silently rendering a broken sign-in experience.
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!PUBLISHABLE_KEY) {
  throw new Error('Missing Clerk publishable key');
}

// Without this, Clerk renders its default light-theme modal against
// QueryTuner's dark UI. `dark` from @clerk/themes gets the base look right
// (dark surfaces, light text); the variables below tune it to the site's
// actual palette (tailwind.config.js's qt.* tokens / the same values
// UpgradeModal.jsx uses inline) instead of Clerk's generic dark grey.
// Applies to both the sign-in and sign-up modals — they share this same
// ClerkProvider, so there's nothing to configure per-modal.
const clerkAppearance = {
  baseTheme: dark,
  variables: {
    colorBackground: '#1e293b', // card surface — matches UpgradeModal.jsx / qt.surface
    colorInputBackground: '#0f172a', // recessed input fields — matches QueryInput's textareas / qt.bg
    colorPrimary: '#38bdf8', // qt.accent — buttons, links, focus rings
    borderRadius: '0.5rem', // 8px — matches UpgradeModal's buttons/inputs
    fontFamily: "'IBM Plex Sans', system-ui, sans-serif", // site's global font (tailwind.config.js)
  },
};

// Falls back to a plain reload prompt rather than a blank white screen on
// an unhandled render error — reports to Sentry when configured (a no-op
// call otherwise, same as every Sentry.* call in this file when
// VITE_SENTRY_DSN is unset).
function ErrorFallback() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: 12,
        background: '#0f172a',
        color: '#e2e8f0',
        fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
        padding: 24,
        textAlign: 'center',
      }}
    >
      <p style={{ fontSize: 16, fontWeight: 600 }}>Something went wrong.</p>
      <p style={{ fontSize: 13, color: '#7fa3c4' }}>Try reloading the page.</p>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={<ErrorFallback />}>
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} appearance={clerkAppearance}>
        <BrowserRouter>
          <Routes>
            <Route path="/report/:id" element={<ReportPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/batch" element={<BatchAnalysisPage />} />
            <Route path="/" element={<App />} />
          </Routes>
        </BrowserRouter>
      </ClerkProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>
);
