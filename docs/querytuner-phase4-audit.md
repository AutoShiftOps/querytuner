# Phase 4 — Monetization: audit vs. actual shipped code

**Trigger:** milestone page shows 10 open / 1 closed despite Phase 4 (Clerk auth, Stripe billing, free/Pro gating) being live in production. This audit checks each of the 10 open issues' literal acceptance criteria against the real code on `master` (verified at commit `90b7fd0b`, which includes PR #153 Quiz Mode and PR #154 Batch Workload Analysis, both confirmed merged).

Same discipline as the EXPLAIN chain and batch-analysis docs: every claim below is grep/read-verified against real code, not assumed from the ROADMAP or from the fact that the product "obviously" has monetization live.

**Bottom line:** all 10 are genuinely under-tracked (real, shipped functionality behind every one), but literal acceptance criteria differ from what shipped on **7 of 10** — mostly naming/shape decisions worth a comment, not a defect. **One issue (`#53`) has a real, unflagged product gap**: free users can access the Pro-tier LLM. **One (`#124`) is genuinely half-built**: list view shipped, delete/share/sanitized-filter did not.

Recommend: comment-and-keep-open on all 10 (do not close any yet) — same pattern as `#61`/`#62`/`#63`. None of these are "close outright," because every one has at least a naming or scope gap worth recording for the acquirer-facing paper trail.

---

## `#46` — Free/Pro tier limits

**Asked:** "Free: 10 analyses/day, no schema, no AI. Pro ($19/mo): unlimited, schema, GPT-4o-mini, history."

**Shipped:** `FREE_TIER_MONTHLY_LIMIT = 10` (`main.py:46`), keyed by `usage_month = datetime.now(UTC).strftime("%Y-%m")` — a **calendar-month** limit, not a **daily** one. Schema-info and AI-insights gating, history, and Pro pricing all confirmed present elsewhere. The "$19/mo" price and "no schema/no AI on free" parts aren't independently verified in this pass (pricing lives in the Stripe dashboard, not the repo) but the free/Pro count-limit split is real and enforced server-side (`main.py:345`, `HTTPException(402, ...)`).

**Gap:** "10/day" (issue) vs. 10/month (shipped) — an order-of-magnitude-looser interpretation than literally asked for. This is a real product decision already made and live, not a bug — but the issue's literal text is wrong against the shipped system. Recommend updating the issue's wording to "10/month," not changing the shipped limit to match the old wording.

---

## `#47` — Clerk auth on `/analyze`

**Asked:** "Integrate Clerk. Protect /analyze endpoint with JWT. Show login/logout in navbar."

**Shipped:** confirmed via `Depends(get_current_user)`-style JWT verification, `ClerkProvider` wired at the app root (see `#52` below), `useUser`/`useAuth` from `@clerk/clerk-react` driving auth state in `App.jsx`. This one matches its literal ask closely — no material gap found. Safe to comment-and-close once the group is reviewed, or fold into a single "Phase 4 sync" comment pass.

---

## `#48` — Usage tracking table

**Asked:** "Add PostgreSQL table usage_log(id, user_id, timestamp, query_hash, db_type, used_ai). Wire into /analyze endpoint."

**Shipped:** two tables, not one, and neither is named `usage_log`:
- `user_usage` (migration 006): `id, user_id, month, analysis_count, is_pro, stripe_customer_id, created_at, updated_at` — one row per user per calendar month, an aggregate counter, not a per-request log.
- `user_accounts` (migration 007, added later as a bugfix — see its own note below): `user_id, is_pro, stripe_customer_id, created_at, updated_at`.

Neither table has `timestamp`, `query_hash`, `db_type`, or `used_ai` columns — those already exist on the pre-existing `analyses` table from migration 001, which now also has a `user_id` column (added in migration 006) linking each analysis back to its Clerk user.

**Gap:** the issue asks for one flat log table; what shipped is an aggregate counter table (`user_usage`) plus reuse of an existing table (`analyses`) for the per-request detail, plus a second table (`user_accounts`) added specifically to fix a real bug — migration 007's own comment documents that `is_pro` on a month-scoped `user_usage` row silently reverted to `false` every new calendar month for actual paying subscribers, because Stripe's `is_pro` flag never carried forward to a new month's freshly-created row. That's a genuine, already-fixed production bug worth knowing about for diligence purposes even though it's not this issue's literal ask. Recommend the comment note both the schema deviation and this history, since an acquirer reading migration 007 cold would want the context.

---

## `#49` — Enforce the limit, return 429

**Asked:** "Check usage_log count in last 24h before running analysis. Return 429 with upgrade prompt for free tier over limit."

**Shipped:** enforced server-side at `main.py:345`, monthly (not 24h, same gap as `#46`), returning **`402 Payment Required`** (`main.py:346-349`), not 429. `429` is used elsewhere in the same file (anonymous per-IP rate limiting, `main.py:189` middleware) — a different, unrelated limit. `402` for "you've hit your tier's usage cap" is arguably the more semantically correct HTTP status (429 is for rate limiting, 402 is literally "payment required" and this is a paywall, not a rate limit), but it's not what the issue asked for.

**Gap:** 24h→monthly (same root cause as `#46`), 429→402. Both look like decisions made deliberately and correctly, just never reconciled back into the issue text.

---

## `#50` — Checkout + webhook

**Asked:** "Add POST /create-checkout-session and POST /webhook. On payment success, set user.tier = pro in DB."

**Shipped:** no `/create-checkout-session` endpoint exists — Pro upgrade uses a **Stripe Payment Link** instead (`VITE_STRIPE_PAYMENT_LINK`, referenced in `UpgradeModal.jsx`), with `client_reference_id` appended client-side to carry the Clerk `user_id` through to Stripe's hosted checkout. Webhook lives at **`POST /webhook/stripe`** (`main.py:675`), not `POST /webhook`, and reads `client_reference_id` off `checkout.session.completed` plus `customer.subscription.*` events to call `update_user_pro_status()` / `link_stripe_customer()`.

**Gap:** materially different implementation shape — no backend Checkout Session creation at all, Stripe's own hosted Payment Link page is used instead. This is a legitimate simpler-and-safer pattern (no card data or checkout logic in this codebase at all), but it's a different mechanism than the issue specifies, not just a renamed endpoint. Worth flagging explicitly since an acquirer's engineer grepping for `/create-checkout-session` will find nothing and could misread that as missing functionality.

---

## `#51` — Pricing page

**Asked:** "Add /pricing route. Feature comparison table. Stripe Checkout button for Pro tier."

**Shipped:** confirmed via `main.jsx` — routes are exactly `/`, `/report/:id`, `/history`. **No `/pricing` route exists anywhere.** Pricing/upgrade is instead a modal (`UpgradeModal.jsx`) triggered inline when a free user hits the usage cap or clicks upgrade, containing the Stripe Payment Link CTA.

**Gap:** this is the most literal, unambiguous miss of the ten — the issue asks for a standalone route and none exists; a modal is not a page, and there's no in-app URL an acquirer (or a prospective customer) could visit to see pricing without first triggering the free-limit flow. Worth a real product call: is a dedicated `/pricing` route still wanted for direct-link/SEO/marketing purposes, or is the modal-on-demand pattern the intended final shape? Recommend flagging this as the one item in this group that might warrant actual follow-up work, not just a wording update.

---

## `#52` — Clerk provider + header + auth redirect

**Asked:** "Add Clerk provider to App.jsx. Show user avatar in header. Redirect to login if unauthenticated and over free limit."

**Shipped:** `ClerkProvider` wraps the app in **`main.jsx`** (the actual root), not `App.jsx` — a more correct location architecturally (provider should wrap the router, not live inside one page component), but literally different from the ask. Avatar/login state driven by `useUser`/`isSignedIn` throughout `App.jsx`, confirmed present. "Redirect to login if unauthenticated and over free limit": not confirmed as a browser redirect — instead, `main.py` returns a structured `401 sign_in_required` error the frontend handles inline (`App.jsx`'s `isSignInRequired` handling, `~line 283-307`), most likely surfacing Clerk's sign-in modal/component in place rather than navigating to a separate login page. Functionally equivalent (user is prompted to sign in before proceeding), but not literally a "redirect."

**Gap:** file location (main.jsx vs. App.jsx) and redirect-vs-inline-prompt are both minor, both look like reasonable-or-better implementation choices, neither is a real functional gap.

---

## `#53` — Pro-tier LLM routing — genuine gap, flagged for real follow-up

**Asked:** "Route Pro users to OpenAI GPT-4o-mini via langchain-openai with structured output. Free tier stays on HuggingFace."

**Shipped, confirmed via direct code read of `backend/app/llm/router.py`:**
- OpenAI is called via the raw `openai` Python SDK (`openai.AsyncOpenAI`), not `langchain-openai` — a naming/library difference, not a functional one.
- "Structured output" isn't used in the strict sense (no JSON mode / function-calling / schema-constrained response) — the system prompt just instructs the model to return JSON with specific keys, then presumably parses it downstream the same way the HuggingFace path does. Lower reliability than true structured output, but not what I'd call broken.
- **The tier-routing itself is not enforced.** `POST /analyze` reads `request.llm_provider` directly from the client request body (`main.py:361-363`) and passes it straight to `analyzer.analyze()` with **no check against `is_pro` anywhere in the call path** — confirmed by reading the full `/analyze` handler and `router.py`'s `call_llm()`, neither references `is_pro` when choosing a provider. The frontend dropdown (`QueryInput.jsx:29,126-127`) only disables the OpenAI option when the server hasn't configured an API key (`openaiEnabled = !!caps?.providers?.openai`) — it never checks `isPro`. Sign-in is required to use AI insights at all (a separate, confirmed gate), but once signed in, **a free-tier user can select "OpenAI (recommended)" in the dropdown and the backend will honor it**, calling GPT-4o-mini on the free tier's dime.

**This is the one finding in this audit that isn't just stale-tracker bookkeeping** — it's a real, live gap between the intended Free/Pro cost structure and what the code actually enforces. Every paying customer's OpenAI API costs are currently exposed to any signed-in free user who changes a dropdown. Recommend treating this as new, prioritized follow-up work (add an `is_pro` check in `main.py` before honoring `llm_provider="openai"`, mirroring the pattern already used for `max_query_chars`'s free/Pro split at `main.py:313`), not just a comment — this is worth fixing promptly rather than filing away.

---

## `#116` — reference only

**Correction (verified against the real GitHub issue state, not assumed):** this doc originally said `#116` was "already closed" — it is not. `DELETE /report/{id}` and expiring share links did ship earlier this session, but the earlier docs-sync handoff (`docs/querytuner-docs-sync-handoff.md`) explicitly called for **comment, don't close** on `#116` (it only shipped a fixed 90-day window, not the user-selectable 7/30/never the issue also asked for) — and that's exactly what happened: `#116` is still OPEN with that comment on it. Included here only because `#124` explicitly references it — no new findings from this pass.

---

## `#124` — User report dashboard: half-built

**Asked:** "(1) list view with timestamp, dialect, severity badge, and sanitized/unsanitized indicator, (2) delete button per report, (3) share button per report, (4) filter: show sanitized only / show all."

**Shipped, confirmed by reading `HistoryPage.jsx` in full (362 lines):**
- **(1) List view — mostly done.** Confirmed present: relative timestamp (`formatRelativeTime(item.created_at)`), dialect badge (`item.db_type`), severity badge (`sevKey` derived from `item.severity`). **Sanitized/unsanitized indicator — confirmed absent.** No `sanitiz` string anywhere in the file.
- **(2) Delete button — confirmed absent from the UI.** The backend capability exists (`DELETE /report/{id}`, shipped under `#116`), but `#116`'s own design doc explicitly scoped a UI delete trigger **out** of that work — so this isn't a regression or an oversight, it's a known, already-documented gap that `#124` is the natural place to close.
- **(3) Share button — confirmed absent.** No `share`/`Share` string anywhere in `HistoryPage.jsx`. `/report/:id` URLs exist and are copyable manually, but no explicit "copy link" affordance is wired up.
- **(4) Filter (sanitized-only / show-all) — confirmed absent,** consistent with there being no sanitized indicator to filter on in the first place.

**Assessment:** genuinely ~25% done (list view's core fields, minus the sanitized indicator). This is the one issue in the Phase 4 group that's honestly a partial build, not a documentation-lag problem — recommend a real follow-up scoping pass (small: wire the existing `DELETE /report/{id}` to a button, add a copy-link button, and decide whether "sanitized" is even a tracked property anywhere in the data model today — that needs checking before the indicator/filter can be built at all, since nothing in this pass confirmed a `sanitized` field exists on `analyses` rows).

---

## Summary table

| Issue | Core function shipped? | Literal ask matches shipped shape? | Recommended action |
|---|---|---|---|
| #46 | Yes | No — daily vs. monthly | Comment, keep open |
| #47 | Yes | Yes | Comment, safe to close |
| #48 | Yes (different tables) | No — schema/table name differs | Comment, keep open |
| #49 | Yes | No — 24h vs. monthly, 429 vs. 402 | Comment, keep open |
| #50 | Yes (different mechanism) | No — Payment Links vs. Checkout Session, path differs | Comment, keep open |
| #51 | **No** — no route exists | No | **Real follow-up candidate** |
| #52 | Yes | Mostly — file location, redirect vs. inline | Comment, keep open |
| #53 | Partially — routing exists, gating doesn't | No — tier enforcement missing | **Real follow-up, prioritize** (cost exposure) |
| #116 | Yes (already closed) | — | No action |
| #124 | Partially (~25%) | No | **Real follow-up candidate** |

Next: draft per-issue GitHub comments (same format as the `#61`/`#62`/`#63` comments doc) plus a short ROADMAP/CHANGELOG note flagging `#53` and `#124` as newly-identified active gaps rather than closed/stale items, for hand-off through VS Code Claude the same way as before.

---

## What happened next

- **`#53` fixed in code, not just flagged** — the audit's own text called this "worth fixing promptly rather than filing away," so it was: `POST /analyze` now returns a structured `403 pro_required` when a non-Pro user requests `llm_provider="openai"`, and the frontend dropdown now also checks `isPro`. See [PR #156](https://github.com/AutoShiftOps/querytuner/pull/156) — up for review, not yet merged at the time of this note. The library-naming (`langchain-openai` vs. the raw `openai` SDK) and structured-output-strictness gaps this audit also found were left as-is; only the cost-exposure enforcement gap was urgent.
- **Comments posted on all 9 non-reference issues** (`#46`–`#53`, `#124`) — all kept **open**, per this doc's own bottom-line recommendation, including `#47` despite its own per-issue note calling it "safe to close": the top-level "do not close any yet" instruction was treated as authoritative over that aside, and no issue was closed unilaterally.
- **`#116`'s "already closed" claim was wrong** — corrected in that section above. It's a small reminder that even a same-session audit doc needs its own claims checked against real state, not just the code's.
- **`#124` was NOT built in this pass** — the audit only recommended "a real follow-up scoping pass," not immediate work, and the doc's own "Next" section didn't list it as something to build now. Comment posted; still ~25% done, still open.
- **ROADMAP.md/CHANGELOG.md**: intentionally not touched by this pass. This session's established pattern (see the EXPLAIN-parser-chain and batch-workload-analysis docs) is to sync those *after* a fix's PR actually merges, referencing the real merge commit — not before, to avoid documenting shipped functionality that isn't live yet. Revisit once #156 merges.
