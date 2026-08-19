/**
 * Handles the redirect back from Stripe Checkout (?upgraded=true) on
 * QueryTuner's root route. Pulled out of App.jsx as plain, DOM-optional
 * functions so the actual retry/decision logic is unit-testable without
 * needing a full component-mounting test setup (no @testing-library/react
 * or jsdom exists in this project yet) — App.jsx stays a thin wiring layer
 * that calls these and touches window/history itself.
 */

/** True when the current URL's query string carries ?upgraded=true. */
export function hasUpgradedParam(search) {
  return new URLSearchParams(search).get('upgraded') === 'true';
}

/**
 * Returns `href` with the `upgraded` param removed, for
 * window.history.replaceState — so a page refresh after the checkout
 * redirect doesn't re-trigger the welcome toast / re-poll /usage.
 */
export function buildUrlWithoutUpgradedParam(href) {
  const url = new URL(href);
  url.searchParams.delete('upgraded');
  return url.toString();
}

/**
 * Polls fetchUsage (a thin wrapper around GET /usage) until is_pro comes
 * back true, or attempts run out.
 *
 * Why this exists: the redirect back from Stripe Checkout and Stripe's
 * webhook (which is what actually flips is_pro in Supabase — see
 * backend/app/main.py's stripe_webhook()) are two independent async paths
 * from the same checkout. The browser can land back on the site before the
 * webhook has finished, so a single fetch right on mount isn't reliable —
 * this is what makes the retry loop necessary rather than trusting the
 * ?upgraded=true param (or one GET /usage call) outright.
 *
 * fetchUsage: () => Promise<{count, is_pro, limit}> — same shape GET
 *   /usage already returns. A rejected/throwing fetchUsage call counts as
 *   "not yet pro" for that attempt rather than aborting the whole poll —
 *   a single flaky request shouldn't sink the retry loop.
 * delayFn: (ms) => Promise<void> — injected so tests can resolve instantly
 *   instead of waiting on real wall-clock time; defaults to a real
 *   setTimeout-based wait for actual runtime use.
 *
 * Returns {success, usage, attempts}. success is only ever true when a
 * fetch actually returned is_pro: true — callers must not assume Pro
 * status from the query param alone, only from this result.
 */
export async function pollForProStatus(fetchUsage, { attempts = 5, delayMs = 1500, delayFn } = {}) {
  const wait = delayFn || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));

  for (let i = 0; i < attempts; i++) {
    let usage = null;
    try {
      usage = await fetchUsage();
    } catch {
      usage = null;
    }
    if (usage?.is_pro) {
      return { success: true, usage, attempts: i + 1 };
    }
    if (i < attempts - 1) {
      await wait(delayMs);
    }
  }
  return { success: false, usage: null, attempts };
}
