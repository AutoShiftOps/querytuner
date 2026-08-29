/**
 * setup.js — runs before every test file (vite.config.js's test.setupFiles).
 *
 * Two things every component-render test in this repo needs and shouldn't
 * have to set up itself:
 *
 * 1. jest-dom's matchers (toBeInTheDocument(), etc.) registered globally.
 * 2. A working @clerk/clerk-react mock. Every Clerk-gated page
 *    (HistoryPage.jsx, PricingPage.jsx, BatchAnalysisPage.jsx, Header.jsx)
 *    calls useUser()/useAuth() or renders <SignedIn>/<SignedOut> — without
 *    a mock, importing any of them in a test throws immediately (Clerk's
 *    hooks require a real <ClerkProvider> in the tree, which needs a real
 *    publishable key this test environment doesn't have and shouldn't need).
 *
 * `clerkState` is exported so individual tests can flip signed-in/signed-out
 * state with a plain assignment (`clerkState.isSignedIn = true`) instead of
 * re-mocking the module per test file — see BatchAnalysisPage.render.test.jsx
 * for the pattern. Reset in each test file's own beforeEach; this file only
 * sets the initial defaults once.
 */

import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// vite.config.js doesn't set test.globals: true (existing tests all use
// explicit `import { describe, it, expect } from 'vitest'`, and there's no
// reason to add ambient globals just for this) — which means
// @testing-library/react's usual auto-cleanup-after-each-test never
// registers on its own. Without this, every render test in a file leaves
// its DOM tree in document.body, and the NEXT test's queries (getByRole,
// findByText, ...) start matching duplicate elements from prior tests.
afterEach(() => cleanup());

export const clerkState = {
  isSignedIn: false,
  user: null,
  getToken: vi.fn(async () => 'fake-test-token'),
};

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({ isSignedIn: clerkState.isSignedIn, user: clerkState.user }),
  useAuth: () => ({ getToken: clerkState.getToken }),
  // Real SignInButton/SignUpButton render Clerk's own modal trigger — tests
  // here only need to confirm the button/prompt is present, not exercise
  // Clerk's actual modal, so these just render their children directly.
  SignInButton: ({ children }) => children,
  SignUpButton: ({ children }) => children,
  SignedIn: ({ children }) => (clerkState.isSignedIn ? children : null),
  SignedOut: ({ children }) => (clerkState.isSignedIn ? null : children),
  UserButton: () => null,
  ClerkProvider: ({ children }) => children,
}));
