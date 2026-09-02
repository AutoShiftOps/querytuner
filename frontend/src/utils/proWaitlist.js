/**
 * proWaitlist.js — builds the mailto: link for the "Pro — coming soon"
 * flow (UpgradeModal.jsx, PricingPage.jsx), used while Stripe checkout is
 * intentionally disabled (see VITE_PRO_CHECKOUT_ENABLED in both callers).
 * Until that flag is deliberately turned on, this is the only way to get
 * Pro — manually granted by whoever reads this inbox, not through
 * automated checkout.
 *
 * The fixed `[QueryTuner Pro Request]` subject prefix exists so it can be
 * matched by a Gmail filter (Settings → Filters and Blocked Addresses →
 * Create a new filter → Subject: "[QueryTuner Pro Request]" → Create
 * filter → Apply label, e.g. "QueryTuner/Pro Requests") and routed out of
 * the general inbox automatically.
 */

const PRO_REQUEST_EMAIL = 'admin@autoshiftops.com';
const SUBJECT_PREFIX = '[QueryTuner Pro Request]';

/**
 * @param {object} params
 * @param {string|null} params.email  - signed-in user's email, or null
 * @param {string|null} params.userId - Clerk user ID, or null (so the
 *   request can be matched to an account even if the reply doesn't quote
 *   the original email's From address exactly)
 * @returns {string} a mailto: URL ready to use as an <a href>
 */
export function buildProRequestMailto({ email, userId } = {}) {
  const subject = `${SUBJECT_PREFIX} ${email || 'signed-out visitor'}`;
  const body = [
    'Hi,',
    '',
    "I'd like free early access to QueryTuner Pro while checkout isn't live yet.",
    '',
    `Account email: ${email || '(not signed in)'}`,
    `User ID: ${userId || '(not signed in)'}`,
    '',
    'Thanks!',
  ].join('\n');

  return `mailto:${PRO_REQUEST_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
