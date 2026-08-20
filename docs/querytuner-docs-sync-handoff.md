# Docs/issue sync for #54, #116, #117, #118

**Why:** Verified via `gh api` that all four GitHub issues are still open with zero comments/PR links, and `ROADMAP.md`/`CHANGELOG.md` still show these as not-yet-shipped, even though `db2f1306`, `7121cc12`, `4e747b95`, and `860950e3` are merged to `master` and independently verified (tests re-run, diffs read). This session has read-only repo access and can't push or comment — handing off the exact content so nothing has to be re-derived.

**Please verify against the real commit log before applying** — this was drafted from what this session could see; you have full repo access to double-check exact dates/scope.

---

## 1. ROADMAP.md — Phase 5 table (around line 190)

Replace these four rows:

```
| #54 | Query history — save + replay past analyses per user | 🔴 High |
```
```
| #116 | URL expiration and deletion for shareable reports | 🟡 Medium |
```
```
| #117 | Column order reasoning in composite index DDL proposals | 🟢 Low |
```
```
| #118 | Write and storage cost estimate per index recommendation | 🟡 Medium |
```

with:

```
| #54 | ✅ Query history — save + replay past analyses per user (`db2f1306`) | 🔴 High |
| #116 | ✅ URL expiration and deletion for shareable reports — shipped as fixed 90-day default + owner-only revoke (`860950e3`); GitHub issue also asked for user-selectable 7/30/never at share time, not yet built — see note below | 🟡 Medium |
| #117 | ✅ Column order reasoning in composite index DDL proposals (`7121cc12`) | 🟢 Low |
| #118 | ✅ Write and storage cost estimate per index recommendation (`4e747b95`) | 🟡 Medium |
```

Also worth checking while in this file: the Milestone Summary table further down still shows `Phase 4 — Monetize` and `Phase 5 — Enterprise` without ✅, even though Phase 4 (Stripe + Clerk) is confirmed live in the commit history. Same staleness issue, larger scope — flagging, not drafting a fix for that here since it needs a judgment call on what "done" means for a whole phase with several items still open (`#55`, `#56`, `#57`, etc.).

---

## 2. CHANGELOG.md — `[Unreleased]` section (top of file)

Currently reads: *"These changes will become v0.3.0 when Phase 4 ships."* — Phase 4 already shipped. Two options, pick whichever matches how you've actually been versioning:

- **If v0.3.0 hasn't been tagged yet:** update the sentence to reflect current reality and add a `### Added` entry for the four items:
  ```
  - Query history for Pro users — `GET /history`, gated server-side on Pro status (#54, `db2f1306`)
  - Shareable report link expiration (90-day default) + owner-initiated early revoke via `DELETE /report/{id}` (#116, `860950e3`)
  - Composite index recommendations now order columns by standard convention (equality → JOIN → range → sort) instead of raw extraction order (#117, `7121cc12`)
  - Write/storage cost estimate alongside every index recommendation's existing read-side benefit estimate (#118, `4e747b95`)
  ```
- **If v0.3.0 was already tagged and this is genuinely the next unreleased batch:** same four bullets, just don't touch the "will become v0.3.0" sentence — replace it with whatever the next version's working name actually is.

Either way, `Header.jsx`'s hardcoded `v0.2.0` badge (`frontend/src/components/Header.jsx`) is worth a look while touching this — if a version bump is happening, that display string needs to move with it or it becomes its own small piece of stale/false presentation.

---

## 3. GitHub issue comments

### #54 — close
> Shipped in `db2f1306` — `GET /history` (Pro-gated server-side, same tier check as `/analyze`), new `HistoryPage.jsx` at `/history`, and a `History` link in the header for signed-in users. Verified: 195 backend tests pass, 33 frontend tests pass, diffs read for scope-creep and non-goal compliance.

### #117 — close
> Fixed in `7121cc12` — composite index column ordering now follows equality-before-range-before-sort convention instead of raw WHERE/JOIN/ORDER BY extraction order. New `test_index_recommender.py` asserts actual DDL column order, not just that a composite was suggested. Verified independently (tests re-run, diff read).

### #118 — close
> Shipped in `4e747b95` — every index suggestion now carries a `cost_estimate` alongside the existing `estimated_improvement`, based on column count and (when schema is available) column type. Verified independently.

### #116 — comment, **do not close yet**
> Partially shipped in `860950e3`: `GET /report/{id}` now enforces a fixed 90-day default expiration (`analyses.expires_at`, migration 008), and a new `DELETE /report/{id}` lets a signed-in owner revoke their own link early (soft-delete, auth-enforced via the `id AND user_id` filter in the query itself, not just app-level).
>
> This issue's original ask also included **user-selectable expiration at share time (7 days / 30 days / never)** — that part wasn't built; v1 shipped a single fixed window instead (see `docs/querytuner-phase5-quick-wins-issue.md`'s explicit non-goals). Recommend either: (a) narrow this issue's title/scope to match what shipped and file a new issue for selectable expiration, or (b) leave this open and treat it as the remaining scope. Whichever you'd rather do — flagging so the issue doesn't get force-closed against acceptance criteria it doesn't actually meet.
