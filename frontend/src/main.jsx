import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ClerkProvider } from '@clerk/clerk-react';
import { dark } from '@clerk/themes';
import ReportPage from './components/ReportPage';
import App from './App';

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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} appearance={clerkAppearance}>
      <BrowserRouter>
        <Routes>
          <Route path="/report/:id" element={<ReportPage />} />
          <Route path="/" element={<App />} />
        </Routes>
      </BrowserRouter>
    </ClerkProvider>
  </React.StrictMode>
);
