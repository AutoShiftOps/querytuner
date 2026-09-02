# PR-ready instructions: disable Pro checkout, add "coming soon" + free-upgrade request flow

**Context for whoever applies this (VS Code Claude / anyone with write access):**
Sajja needs Stripe checkout to stop being a live, clickable path — even
accidentally — while he confirms whether operating a paid SaaS is
compatible with his Canadian closed/employer-specific work permit. This
is NOT a request to rip out Stripe integration code; it's a request to
make "Pro checkout is live" an explicit, deliberate opt-in rather than
something that quietly turns on if `VITE_STRIPE_PAYMENT_LINK` ever gets
set in Vercel. In the meantime, anyone who wants Pro gets it manually,
for free, via an email that lands in its own labeled folder.

Two files change (`UpgradeModal.jsx`, `PricingPage.jsx`), one new file is
added (`frontend/src/utils/proWaitlist.js`, plus its test).

---

## 1. New file: `frontend/src/utils/proWaitlist.js`

```js
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
```

## 2. New file: `frontend/src/utils/proWaitlist.test.js`

```js
import { describe, it, expect } from 'vitest';
import { buildProRequestMailto } from './proWaitlist';

describe('buildProRequestMailto', () => {
  it('includes the fixed subject prefix for Gmail filtering', () => {
    const url = buildProRequestMailto({ email: 'a@b.com', userId: 'user_123' });
    expect(url).toContain('mailto:admin%40autoshiftops.com'.replace('%40', '@')); // recipient present
    expect(decodeURIComponent(url)).toContain('subject=[QueryTuner Pro Request] a@b.com');
  });

  it('falls back gracefully for signed-out visitors', () => {
    const url = buildProRequestMailto({});
    const decoded = decodeURIComponent(url);
    expect(decoded).toContain('[QueryTuner Pro Request] signed-out visitor');
    expect(decoded).toContain('(not signed in)');
  });
});
```

## 3. Edit `frontend/src/components/UpgradeModal.jsx`

Replace the top of the file (imports + constants):

```diff
 import { useUser } from '@clerk/clerk-react';
 import { X, Zap, History, Sparkles } from 'lucide-react';
+import { buildProRequestMailto } from '../utils/proWaitlist';

-// Phase 4: shown when a signed-in free-tier user hits FREE_LIMIT in App.jsx.
-//
-// The CTA reads its target from VITE_STRIPE_PAYMENT_LINK rather than a
-// hardcoded URL — there is no real Stripe Payment Link available yet (one
-// must be created in the Stripe dashboard for price_1U0nGnDnampVVaUXDZ2MvqQc
-// and the resulting https://buy.stripe.com/... URL set as that env var).
-// Shipping a fake/placeholder URL in source would silently 404 for every
-// user, so the button disables itself with an explicit note instead.
-const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';
+// Phase 4: shown when a signed-in free-tier user hits FREE_LIMIT in App.jsx.
+//
+// CHECKOUT_ENABLED is a deliberate, explicit switch — separate from
+// whether a Stripe Payment Link happens to be configured. Real checkout
+// only ever shows when BOTH are true. This is intentional: an env var
+// that's merely unset is too easy to flip on by accident later (someone
+// sets VITE_STRIPE_PAYMENT_LINK for an unrelated reason and real
+// payments silently go live). Until CHECKOUT_ENABLED is explicitly set
+// to "true" in Vercel, every user sees the "coming soon" + free-request
+// flow below, no matter what else is configured.
+const CHECKOUT_ENABLED = (import.meta.env.VITE_PRO_CHECKOUT_ENABLED || '').toLowerCase() === 'true';
+const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';
```

Replace the CTA block (the `{PAYMENT_LINK ? (...) : (...)}` section):

```diff
-        {PAYMENT_LINK ? (
+        {CHECKOUT_ENABLED && PAYMENT_LINK ? (
           <a
             href={paymentUrl}
             rel="noopener noreferrer"
             style={{
               display: 'block',
               textAlign: 'center',
               background: '#38bdf8',
               color: '#0f172a',
               fontWeight: 600,
               fontSize: 14,
               padding: '10px 16px',
               borderRadius: 8,
               textDecoration: 'none',
             }}
           >
             Upgrade to Pro →
           </a>
         ) : (
           <div>
-            <button
-              disabled
-              title="Stripe payment link not configured — set VITE_STRIPE_PAYMENT_LINK"
-              style={{
-                display: 'block',
-                width: '100%',
-                textAlign: 'center',
-                background: '#2d3f55',
-                color: '#7fa3c4',
-                fontWeight: 600,
-                fontSize: 14,
-                padding: '10px 16px',
-                borderRadius: 8,
-                border: 'none',
-                cursor: 'not-allowed',
-              }}
-            >
-              Upgrade to Pro →
-            </button>
-            <p style={{ fontSize: 11, color: '#4a6480', margin: '8px 0 0' }}>
-              Payment link not configured yet — create one in Stripe Dashboard → Payment Links for{' '}
-              price_1U0nGnDnampVVaUXDZ2MvqQc, then set VITE_STRIPE_PAYMENT_LINK.
-            </p>
+            <a
+              href={buildProRequestMailto({
+                email: user?.primaryEmailAddress?.emailAddress || null,
+                userId: user?.id || null,
+              })}
+              style={{
+                display: 'block',
+                width: '100%',
+                textAlign: 'center',
+                background: '#38bdf8',
+                color: '#0f172a',
+                fontWeight: 600,
+                fontSize: 14,
+                padding: '10px 16px',
+                borderRadius: 8,
+                textDecoration: 'none',
+              }}
+            >
+              Pro is coming soon — request free early access →
+            </a>
+            <p style={{ fontSize: 11, color: '#7fa3c4', margin: '8px 0 0', textAlign: 'center' }}>
+              We're not charging for Pro yet. Click above and we'll turn it on for your account, free.
+            </p>
           </div>
         )}
```

## 4. Edit `frontend/src/components/PricingPage.jsx`

Same two changes, same reasoning:

```diff
+import { buildProRequestMailto } from '../utils/proWaitlist';
+
 const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';
+const CHECKOUT_ENABLED = (import.meta.env.VITE_PRO_CHECKOUT_ENABLED || '').toLowerCase() === 'true';
```

```diff
             ) : isSignedIn ? (
-              PAYMENT_LINK ? (
+              CHECKOUT_ENABLED && PAYMENT_LINK ? (
                 <a
                   href={paymentUrl}
                   rel="noopener noreferrer"
                   className="qt-pricing-card-cta qt-pricing-card-cta-primary"
                 >
                   Upgrade to Pro →
                 </a>
               ) : (
-                <>
-                  <button disabled className="qt-pricing-card-cta qt-pricing-card-cta-primary">
-                    Upgrade to Pro →
-                  </button>
-                  <p className="qt-pricing-card-note">Payment link not configured yet.</p>
-                </>
+                <>
+                  <a
+                    href={buildProRequestMailto({
+                      email: user?.primaryEmailAddress?.emailAddress || null,
+                      userId: user?.id || null,
+                    })}
+                    className="qt-pricing-card-cta qt-pricing-card-cta-primary"
+                  >
+                    Coming soon — request free access →
+                  </a>
+                  <p className="qt-pricing-card-note">
+                    We're not charging for Pro yet — email us and we'll turn it on for free.
+                  </p>
+                </>
               )
             ) : (
```

Also update the card's `blurb` copy slightly since "$19/month" next to a free-access CTA reads oddly — change:

```diff
-            <p className="qt-pricing-card-blurb">
-              For engineers running this regularly on real work.
-            </p>
+            <p className="qt-pricing-card-blurb">
+              For engineers running this regularly on real work.{' '}
+              {!CHECKOUT_ENABLED && 'Free during early access.'}
+            </p>
```

## 5. Gmail filter to route requests into their own folder

In Gmail (on the `admin@autoshiftops.com` account):
1. Settings → **See all settings** → **Filters and Blocked Addresses** → **Create a new filter**.
2. **Subject**: `[QueryTuner Pro Request]`
3. **Create filter** → check **Apply the label** → **New label** → e.g. `QueryTuner/Pro Requests` (optionally also check **Skip the Inbox** if you want them fully separated, or leave inbox-visible with just the label).
4. Save.

Every click on the new CTA opens the visitor's own email client with the
subject pre-filled — no backend change, no new endpoint, nothing that can
silently misfire.

## 6. Not changed, deliberately

- `backend/app/main.py`'s Stripe webhook (`/webhook/stripe`) and
  `/billing-portal` endpoint are untouched — existing Pro subscribers (if
  any real ones exist) keep working normally; this change only affects
  *new* signups seeing the upgrade CTA.
- Nothing in Stripe's dashboard needs to change. `VITE_PRO_CHECKOUT_ENABLED`
  simply doesn't need to be set anywhere — its absence is what keeps this
  safe by default.

## 7. To manually grant someone free Pro

The actual mechanism for flipping `is_pro: true` isn't part of this diff
(it's presumably a direct Supabase update or an internal admin action —
confirm with whoever normally handles Pro grants). The `User ID` in the
request email is what that grant needs to target the right account.
