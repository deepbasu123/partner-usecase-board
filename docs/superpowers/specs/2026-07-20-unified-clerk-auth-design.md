# Unified Clerk Auth — One App, Role-Gated — Design Spec

**Date:** 2026-07-20
**Author:** Databricks Solutions Architect
**Status:** Approved design, pending implementation plan
**Supersedes routing model in:** [2026-07-15-email-domain-auth-routing-design.md](2026-07-15-email-domain-auth-routing-design.md)
**Builds on:** [2026-07-15-clerk-partner-auth-design.md](2026-07-15-clerk-partner-auth-design.md)

## Problem

The board is currently **two separate React SPAs** served from one origin:

- `portal-frontend/` (Vite base `/`) — the partner board.
- `admin-app/frontend/` (Vite base `/admin/`) — the Databricks-team cockpit.

Both are already wrapped in Clerk and sign in via email-OTP. But when a
`@databricks.com` user signs into the portal, the app does a **full-page
redirect out** into the separate admin SPA
(`portal-frontend/src/App.tsx`, effect calling `window.location.assign("/admin")`).
That means two builds, two Clerk providers, two themes, two API clients, and a
hard app-to-app jump — not "one unified app." An employee cannot fluidly move
between the admin view and the partner board; switching means loading a
different application.

## Goal

Collapse the two SPAs into **one app** that role-gates by verified Clerk email
domain, with no cross-app redirect:

> After Clerk email-OTP sign-in, a `@databricks.com` identity lands on the
> **admin sections** and can **switch to view the partner board**; every other
> identity sees **only the partner board**. The shared admin password is
> retained as a **break-glass fallback**.

## Decisions locked (from brainstorming)

1. **One unified app, role-gated** — fold the admin screens into
   `portal-frontend/` as role-gated routes/sections. Delete the cross-app
   redirect. Stop building `admin-app/frontend/`.
2. **Employee view = admin + board, switchable** — `@databricks.com` users land
   on admin (post/close cases, view responses, partner directory) and have a
   "View board" switch to see the public partner board read-only. Partners only
   ever see the board.
3. **Shared password kept as break-glass fallback** — not retired. Clerk
   `@databricks.com` is the normal admin path; the password is a secondary way
   in (Clerk outage, or a non-`@databricks.com` person who legitimately needs
   admin).
4. **Auth mechanism unchanged** — everyone signs in via Clerk email-OTP;
   `@databricks.com` is auto-detected by the existing `isDatabricksEmail` rule.
5. **No new Settings screen** — "admin settings" means the *existing* admin
   capabilities (cases, responses, partners, identity). A literal new Settings
   page is explicitly out of scope (YAGNI).
6. **Theme:** the portal's editorial theme is the base; admin sections are
   restyled to match it. One app, one look.

## The domain rule (unchanged, one shared definition)

```
isDatabricksEmail(email) := email.trim().toLowerCase().endsWith("@databricks.com")
```

Already defined identically in `portal-frontend/src/auth.ts`,
`admin-app/frontend/src/auth.ts`, and (as `is_databricks_email`)
`board_api/admin_auth.py`. In the unified app the portal copy is the single
frontend definition; the admin-frontend copy is deleted with its app. The
backend copy is unchanged. Matches only exact `...@databricks.com`,
case-insensitively; `sub.databricks.com`, `notdatabricks.com`, and
`databricks.com.evil.com` do NOT match.

## Architecture

```
                Clerk sign-in (email-OTP, any email)
                          │  verified email in JWT `email` claim
                          ▼
                    useRole() resolves
        ┌───────────────────────────────────────────────┐
        │ clerk still loading            → "loading"      │
        │ signed-in & isDatabricksEmail  → "admin"        │
        │ else GET /api/admin/whoami 200 → "admin"        │  ← break-glass cookie
        │ else                           → "partner"      │
        └───────────────────────────────────────────────┘
                          │
             ┌────────────┴─────────────┐
        "admin"                     "partner"
   land on admin sections       board only (browse,
   + "View board" switch        onboard, respond) —
   (board read-only)            no admin nav ever
```

The **backend is the security boundary and barely changes** — it already
supports this exact model:

- `board_api/admin_auth.py::require_admin` already passes on **either** a valid
  signed admin cookie **or** a verified `@databricks.com` Clerk JWT.
- `board_api/admin_auth.py::admin_identity` / `routes_admin.py::whoami` already
  return the Clerk email when Clerk-authed, else `ADMIN_EMAIL`.
- `board_api/clerk_auth.py::require_identity` already gates partner routes on a
  verified Clerk Bearer token.

The work is a **frontend merge**, not a re-architecture of auth.

## Component changes

### Frontend — `portal-frontend/` becomes the one app

**Router (`src/App.tsx`)**
- **Delete** the `window.location.assign("/admin")` redirect effect
  (`App.tsx:24-28`) — this is the change that ends the cross-app jump.
- Introduce a `useRole()` hook (new `src/role.ts`) returning
  `"loading" | "partner" | "admin"` per the Architecture diagram.
- While `"loading"`, render a spinner (no premature partner/admin UI).
- Routes:
  - `"partner"`: existing routes unchanged — `/` board, `/onboarding`,
    `/case/:id`, `/signin/*`. The `me()`/onboarding effect runs for partners
    only (guard on role, replacing today's `dbxEmail` guard at `App.tsx:31`).
  - `"admin"`: default view is the admin cockpit; `/case/:id` and the board
    remain reachable via the "View board" switch. Admin does NOT run the
    partner `me()`/onboarding flow.

**New/moved admin components (ported from `admin-app/frontend/src/`)**
- `components/AdminCases.tsx` — create-case form + case rows (from
  `CreateCaseForm.tsx` + `CaseRow.tsx`).
- `components/AdminPartners.tsx` — partner directory table (from admin `App.tsx`
  partners table).
- `components/AdminLogin.tsx` — the break-glass password form (from admin
  `AdminLogin.tsx`), reachable at route `/admin/login`. Note: today's admin app
  renders this **conditionally by state** (it has no router — `admin-app`'s
  `main.tsx` has no `<BrowserRouter>`). The portal app already has a router, so
  this becomes a real **route**, not a state branch — a genuine behavioral port,
  not a copy.
- Restyle all three to the portal theme (`theme.css`) per decision 6.

**Nav (`components/Chrome.tsx` `Rail`)**
- Role-aware. For `"admin"`: show admin nav items (Use cases, Partners) plus a
  **"View board" / "Back to admin"** toggle, and an identity chip showing the
  real Clerk email (or `ADMIN_EMAIL` for break-glass). For `"partner"`:
  unchanged (no admin items).

**API client (`src/api.ts`)**
- Merge the admin methods (`listCases`, `createCase`, `setStatus`,
  `responsesFor`, `listPartners`, `whoami`, `login`) into the existing
  `makeApi(getToken)` factory.
- Every authed call sends the Clerk Bearer token when present **and**
  `credentials: "include"` so the break-glass cookie also flows. (Today the
  portal client omits `credentials`; the admin client includes it — the merged
  client must include it so break-glass works.)
- Delete the module-singleton `setAdminTokenGetter` pattern from the admin
  client; the merged client takes `getToken` like the portal already does.

**Break-glass login route**
- `/admin/login` renders `AdminLogin` **without** requiring a Clerk session, so
  it works during a Clerk outage and for non-`@databricks.com` admins. On
  success (`POST /api/admin/login` sets the cookie), re-probe `whoami` → role
  becomes `"admin"`.

### Backend — `board_api/` (minimal)

- **No change required** to `require_admin`, `require_identity`,
  `admin_identity`, or `whoami` — verified against the code, they already
  implement the model.
- **Known inherited behavior (not a bug, not changed here):**
  `routes_admin.py` sets a new case's `posted_by` to the bare `ADMIN_EMAIL`
  constant, *not* the Clerk-authed employee's real email — so a case created by
  a signed-in `@databricks.com` user still shows the generic address. This
  predates the merge and is out of scope; flagged only so it isn't mistaken for
  a regression. Changing it (use `admin_identity` for `posted_by`) would be a
  separate, optional follow-up.
- If any other backend change is discovered during implementation it must be
  additive and preserve existing behavior; call it out in the plan rather than
  assuming.

### Build + routing

**`build.sh`**
- Build only `portal-frontend`. Remove the `admin-app/frontend` build step and
  the `dist/admin/` copy. Output is a single `dist/`.

**`vercel.json`**
- Remove **only** the three `/admin*` asset/HTML routes (`/admin/assets/(.*)`,
  `/admin/(.+)`, `/admin`). Keep everything else exactly as-is: `/api/(.*)` →
  the Python function, **`/healthz` → the Python function**, `/assets/(.*)`,
  `handle: filesystem`, and the SPA fallback `/(.*) → /index.html`. The
  client-side router now owns `/admin` and `/admin/login`. **Edit the existing
  file in place — do not reconstruct it from this list**, so no unrelated route
  (e.g. `/healthz`) is accidentally dropped.

**Retire `admin-app/frontend/`**
- Stop building it and remove it from the deployed output. **Decision: leave the
  directory in the tree but drop it from `build.sh`** (rather than `git rm` it),
  and add a one-line deprecation note at the top of its `App.tsx`. Rationale:
  `admin-app/` also holds the Databricks-App backend + `app.yaml` for the
  *original* (non-Vercel) deployment referenced by `main`; leaving the frontend
  in place keeps that variant's tree intact and the change trivially
  reversible. The test is behavioral, not physical: after this change nothing
  under `admin-app/` is built or served on `vercel-neon-deploy`.

## Config

- **No new env vars.** `VITE_CLERK_PUBLISHABLE_KEY` (frontend build),
  `CLERK_JWKS_URL` / `CLERK_ISSUER` (backend verify), `ADMIN_PASSWORD`,
  `ADMIN_SESSION_SECRET`, `SESSION_SECRET`, `DATABASE_URL`, `ADMIN_EMAIL` all
  already exist in Vercel and are reused as-is.
- **Clerk dashboard redirect URLs (verify, may need a one-time change).** Clerk
  redirect URLs are configured per origin/path in the Clerk dashboard, not in
  this repo. Because there is now a single SPA (no `/admin` sub-app), any Clerk
  sign-in/after-sign-in URL that points at an `/admin/...` path must resolve to
  a route the unified app actually serves. The implementation plan must check
  the Clerk instance's configured URLs and either keep them on the portal's
  `/signin/*` or add the matching route — otherwise post-OTP redirects 404. No
  code change if the URLs already target `/` and `/signin/*`.

## Error handling

- Clerk user with **no** email claim → not `isDatabricksEmail` → `whoami`
  (no cookie) 401s → `"partner"`. Safe default.
- `@databricks.com` Clerk token the backend can't verify → `require_admin`
  falls through to the cookie check → 401 if no cookie → UI shows partner or the
  `/admin/login` prompt; never grants admin on a bad token. Fails safe.
- Admin API called with a partner-tier Clerk token → 401 (unchanged backend).
- Clerk fails to load entirely (outage / blocked key) → `useRole()` must not
  spin forever: after a short timeout, fall back to probing `whoami` so
  `/admin/login` (break-glass) stays reachable. Mirrors the existing 4s fallback
  in `admin-app/frontend/src/App.tsx:53-57`.
- All role-dependent redirects/navigation happen in effects, never during
  render (same discipline as the existing onboarding redirect).

## Testing strategy

- **Backend (existing 27 pytest):** must still pass unchanged — the backend
  barely moves. Run `./run_tests.sh` (spins ephemeral local PG).
- **Domain rule:** `isDatabricksEmail` behavior is already covered; keep the
  table cases (`a@databricks.com` yes, `A@Databricks.com` yes,
  `a@sub.databricks.com` no, `a@notdatabricks.com` no,
  `a@databricks.com.evil.com` no, empty no).
- **Frontend:** no unit-test harness exists today. Verification is a **manual
  browser pass** of all three flows on a preview deploy:
  1. Partner OTP sign-in (non-DBX email) → board; onboarding; respond to a case.
  2. DBX OTP sign-in (`@databricks.com`) → lands on admin; create + close a
     case; view responses; view partners; "View board" switch shows the board
     read-only; "Back to admin" returns.
  3. Break-glass: `/admin/login`, enter `ADMIN_PASSWORD` → admin unlocks with no
     Clerk session; identity chip shows `ADMIN_EMAIL`.
  4. Negative: a partner-tier session cannot reach any `/api/admin/*` data
     (network tab shows 401s); no admin nav is rendered for partners.
- **Independent verification:** per working rules, after implementation a
  separate verification agent (different model) independently checks the result
  before it is presented as done.

## Security note

Unchanged from the prior spec and still the crux: only a genuinely
Clerk-**verified** `@databricks.com` address passes the admin gate, and only
someone with access to a `@databricks.com` inbox can complete that OTP. The
backend enforces this on every `/api/admin/*` call; frontend role-gating is
convenience, not the boundary. Folding the apps together does not weaken this —
the same backend dependencies (`require_admin`, `require_identity`) still guard
every route.

## Out of scope

- Retiring the shared password (kept as break-glass per decision 3).
- A new Settings page or any new admin capability (decision 5).
- Per-user Databricks roles beyond "is `@databricks.com`".
- Clerk Organizations.
- Any change to the Databricks-App variant on `main` (only the
  `vercel-neon-deploy` branch is in scope).
- Rate-limiting signup/login (pre-existing gap noted in prior verification; not
  introduced or fixed here).

## Success criteria

1. There is **one** built SPA. `admin-app/frontend/` is no longer built or
   deployed; `dist/` has no `admin/` subtree; `vercel.json` has no `/admin*`
   asset routes.
2. A `@databricks.com` Clerk sign-in lands on the admin sections **without a
   page redirect to a second app** and **without** entering the shared password.
3. From admin, "View board" shows the partner board read-only; "Back to admin"
   returns — all client-side, no full reload.
4. A non-`@databricks.com` Clerk sign-in sees only the partner board (browse,
   onboard, respond) and no admin nav.
5. `/admin/login` + correct `ADMIN_PASSWORD` still unlocks admin with no Clerk
   session (break-glass works), and `/api/admin/*` still accepts either a valid
   `@databricks.com` Clerk token or the password cookie, rejecting everything
   else with 401.
6. All 51 backend tests pass unchanged.
