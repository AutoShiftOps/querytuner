# Follow-up: hide "Manage subscription" too, behind the same flag

**Context:** After the `pro-checkout-coming-soon.md` change (already merged —
commit `fa12f48`), the "Upgrade to Pro" CTA is correctly gated behind
`VITE_PRO_CHECKOUT_ENABLED`. But Sajja's own account was manually marked
`is_pro: true` earlier (for testing), so he still sees a **"Manage
subscription"** button (in both `Header.jsx` and `PricingPage.jsx`) that
opens a real Stripe-hosted billing portal — a second, separate
Stripe-facing surface the first change didn't touch.

Goal: gate "Manage subscription" behind the *same* `CHECKOUT_ENABLED` flag,
so flipping `VITE_PRO_CHECKOUT_ENABLED` back to `"true"` brings back both
the upgrade CTA and subscription management together — one flag, not two
to remember. The "Pro ✓" badge/indicator itself stays visible either way
(it's just a label, not a Stripe link) — only the button that actually
opens Stripe's billing portal is hidden.

Two files change: `frontend/src/components/Header.jsx`,
`frontend/src/components/PricingPage.jsx`. No backend change — the
`/billing-portal` endpoint stays exactly as-is; existing subscribers who
somehow reach it directly are unaffected. This purely hides the button
that links to it from the UI while checkout is paused.

---

## 1. Edit `frontend/src/components/Header.jsx`

`Header.jsx` doesn't currently import/define `CHECKOUT_ENABLED` — add it
at module scope, same pattern as `UpgradeModal.jsx`/`PricingPage.jsx`:

```diff
 const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
+
+// Mirrors UpgradeModal.jsx / PricingPage.jsx's CHECKOUT_ENABLED — same
+// explicit opt-in flag, so "Manage subscription" (which opens a real
+// Stripe billing portal session) comes back automatically whenever real
+// checkout does, instead of needing a second flag remembered separately.
+const CHECKOUT_ENABLED = (import.meta.env.VITE_PRO_CHECKOUT_ENABLED || '').toLowerCase() === 'true';
```

Then gate just the button (keep the "Pro" badge and divider visible for
`isPro` users either way — only the Stripe-portal button hides):

```diff
               {isPro && (
                 <>
                   <span className="qt-header-pro-badge">Pro</span>
-                  <button
-                    onClick={handleManageSubscription}
-                    disabled={portalLoading}
-                    className="qt-header-link qt-header-hide-mobile qt-header-manage-sub"
-                  >
-                    {portalLoading ? 'Opening…' : 'Manage subscription'}
-                  </button>
+                  {CHECKOUT_ENABLED && (
+                    <button
+                      onClick={handleManageSubscription}
+                      disabled={portalLoading}
+                      className="qt-header-link qt-header-hide-mobile qt-header-manage-sub"
+                    >
+                      {portalLoading ? 'Opening…' : 'Manage subscription'}
+                    </button>
+                  )}
                   <div className="qt-header-divider qt-header-hide-mobile" />
                 </>
               )}
```

## 2. Edit `frontend/src/components/PricingPage.jsx`

`PricingPage.jsx` already defines `CHECKOUT_ENABLED` (from the previous
change) — just reuse it. Gate the button + its error note, keep the
"You're on Pro ✓" line visible either way:

```diff
             {isPro ? (
               <>
                 <div className="qt-pricing-card-active">You&rsquo;re on Pro ✓</div>
-                <button
-                  onClick={handleManageSubscription}
-                  disabled={portalLoading}
-                  className="qt-pricing-card-cta qt-pricing-card-cta-secondary"
-                  style={{ marginTop: 10 }}
-                >
-                  {portalLoading ? 'Opening…' : 'Manage subscription'}
-                </button>
-                {portalError && (
-                  <p className="qt-pricing-card-note" style={{ color: T.red }}>
-                    {portalError}
-                  </p>
-                )}
+                {CHECKOUT_ENABLED && (
+                  <>
+                    <button
+                      onClick={handleManageSubscription}
+                      disabled={portalLoading}
+                      className="qt-pricing-card-cta qt-pricing-card-cta-secondary"
+                      style={{ marginTop: 10 }}
+                    >
+                      {portalLoading ? 'Opening…' : 'Manage subscription'}
+                    </button>
+                    {portalError && (
+                      <p className="qt-pricing-card-note" style={{ color: T.red }}>
+                        {portalError}
+                      </p>
+                    )}
+                  </>
+                )}
               </>
             ) : isSignedIn ? (
```

## 3. Not changed, deliberately

- `backend/app/main.py`'s `/billing-portal` endpoint is untouched — this
  is a pure UI-visibility change, not an access-control change. Anyone
  who already knows the endpoint could still call it directly; that was
  already true before this change too (the frontend never was the only
  gate on that route).
- `is_pro` itself isn't touched — Sajja's account stays marked Pro, it
  just won't show a working path to Stripe's billing portal while
  `VITE_PRO_CHECKOUT_ENABLED` is unset/false.

## 4. Result

With `VITE_PRO_CHECKOUT_ENABLED` unset (current state): free users see
the "coming soon" mailto CTA (from the previous change), and Sajja's own
Pro account sees "You're on Pro ✓" / a "Pro" badge but no
Stripe-portal button anywhere in the app. Flipping the one flag to
`"true"` in Vercel brings back both the real Upgrade CTA and the Manage
subscription button at once.
