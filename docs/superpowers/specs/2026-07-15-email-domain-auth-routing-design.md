# Email-Domain Auth Routing — Design Spec

**Date:** 2026-07-15
**Author:** Databricks Solutions Architect
**Status:** Approved design, pending implementation plan
**Builds on:** [2026-07-15-clerk-partner-auth-design.md](2026-07-15-clerk-partner-auth-design.md)

## Problem

After the Clerk migration, everyone who signs in lands on the partner portal
(`/`), and the Databricks-team admin cockpit (`/admin`) is a separate SPA still
gated by a shared password (`ADMIN_PASSWORD`). Databricks staff who sign in with
their real `@databricks.com` identity should not have to also know a shared
password, and they should land in the admin cockpit, not the partner board.

## Goal

Route by verified email domain after Clerk sign-in:

> A Clerk-verified **`@databricks.com`** email → the admin cockpit.
> Any other email → the partner portal (unchanged).

Enforced in BOTH the UI (where you land) and the backend (who `/api/admin/*`
actually trusts). The shared password stays as a fallback — nothing that works
today breaks.

## Decisions locked (from brainstorming)

1. **Destination:** `@databricks.com` users go to the **existing** admin cockpit
   (`/admin`) — Clerk email-domain effectively replaces the shared password for
   staff. No new in-portal "Databricks view" is built.
2. **Backend gate:** admin routes accept **EITHER** the existing shared-password
   cookie **OR** a valid Clerk JWT whose verified email ends in `@databricks.com`
   (additive — password users unaffected).
3. **Admin entry:** the admin SPA **auto-recognizes** a valid `@databricks.com`
   Clerk session and skips the password screen; non-Clerk visitors still see the
   password login exactly as today.
4. **Shared password is retained** as a fallback, not retired.

## The domain rule (one shared definition)

```
isDatabricksEmail(email) := email.trim().toLowerCase().endsWith("@databricks.com")
```

Applied identically in three places: portal routing, admin-frontend skip-login,
and the backend admin gate. The check MUST be anchored on the literal `@` so
`notdatabricks.com`, `databricks.com.evil.com`, and `foo@sub.databricks.com` do
NOT match (only exactly `...@databricks.com`). Case-insensitive.

## Architecture

Three coordinated changes; the backend one is the real security boundary, the two
frontend ones are UX routing on top of it.

```
Clerk sign-in (any email, email-code OTP)
        │  verified email in JWT `email` claim
        ▼
  isDatabricksEmail(email)?
        ├── yes ──► /admin  (portal redirects; admin SPA sees Clerk session,
        │                    skips password; backend trusts the @databricks.com JWT)
        └── no  ──► partner portal: /me → onboarding-or-board (unchanged)
```

## Component changes

### Backend — `board_api/admin_auth.py` (the security boundary)
- `require_admin` currently passes only when `is_valid_admin(admin_cookie)` is
  true. Change it to pass when **either**:
  - the signed admin cookie is valid (unchanged path), **or**
  - the request carries a valid Clerk JWT (via `clerk_auth.verify_token`) whose
    `email` claim satisfies `isDatabricksEmail`.
- Reuse `clerk_auth`'s verification (JWKS, RS256) — do not re-implement JWT
  logic. Extract the bearer token the same way `clerk_auth._bearer` does, or call
  a small shared helper.
- `/api/admin/whoami` (`routes_admin.py`) returns the Clerk email when the caller
  authed via Clerk (so the cockpit header shows the real person), else the
  existing `ADMIN_EMAIL`.
- Failure modes: a Clerk token that is invalid, expired, or non-`@databricks.com`
  does NOT grant admin — it falls through to the cookie check, and if that also
  fails, 401. Fails safe (never open).

### Portal frontend — `portal-frontend/src/App.tsx`
- Once Clerk `useUser()` has loaded, read the primary email
  (`user.primaryEmailAddress.emailAddress`).
- If `isDatabricksEmail(email)`: redirect to `/admin` (full navigation via
  `window.location.assign("/admin")`, since admin is a separate SPA at its own
  base path) INSTEAD of running the partner `me()`/onboarding flow.
- If not: the existing partner flow (me → onboarding-or-board) runs unchanged.
- Add `isDatabricksEmail` in one small shared module (e.g.
  `portal-frontend/src/auth.ts`) so the rule isn't duplicated inline.

### Admin frontend — `admin-app/frontend/`
- Wrap the admin app in `<ClerkProvider>` (same `VITE_CLERK_PUBLISHABLE_KEY`),
  mirroring the portal's `main.tsx`.
- Change the mount `probe()` in `App.tsx`: if a Clerk session exists AND its email
  is `@databricks.com`, attach `Authorization: Bearer <clerk token>` to admin API
  calls (extend `admin-app/frontend/src/api.ts` the way the portal's `makeApi`
  does) and treat the user as authed — skip the password screen.
- If there is no valid Clerk session, `whoami` 401s and `<AdminLogin>` shows
  exactly as today. The shared-password path is untouched.

### Config
- No new env vars. Admin frontend build needs `VITE_CLERK_PUBLISHABLE_KEY`
  (already set in Vercel) exposed to its build; `CLERK_JWKS_URL` /
  `CLERK_SECRET_KEY` are already present for the backend.

## Error handling
- Clerk user with **no** email claim → treated as non-Databricks → partner flow.
- `@databricks.com` Clerk token the backend can't verify → falls through to the
  password gate (fails safe).
- Admin API called with a partner-tier (non-`@databricks.com`) Clerk token →
  401.
- Portal redirect to `/admin` must happen as an effect, not during render (same
  discipline as the existing onboarding redirect).

## Testing strategy
- **Backend (unit, extends `board_api/tests/test_admin_auth.py`):** using the
  locally-minted-JWT technique from `test_clerk_auth.py`, assert `require_admin`:
  (a) accepts a valid `@databricks.com` JWT, (b) rejects a `@gmail.com` JWT (401),
  (c) still accepts the valid shared-password cookie, (d) 401s with neither,
  (e) rejects a malformed/expired token. Add a `whoami` test that returns the
  Clerk email when Clerk-authed.
- **Domain-rule unit:** table-test `isDatabricksEmail` against
  `a@databricks.com` (yes), `A@Databricks.com` (yes), `a@sub.databricks.com`
  (no), `a@notdatabricks.com` (no), `a@databricks.com.evil.com` (no),
  empty/missing (no).
- **Live (manual, browser — Clerk sign-in can't be curled):** sign in with a
  `@databricks.com` email → lands in the admin cockpit with NO password prompt;
  sign in with a non-DBX email → partner board. Confirm a partner-tier token
  cannot reach `/api/admin/*`.

## Security note (why email-domain gating is trustworthy here)
Self-serve Clerk sign-up (`withSignUp`) lets anyone create an account with any
email **they can receive an OTP at**. Only a genuinely Clerk-**verified**
`@databricks.com` address passes the gate, and only someone with access to a
`@databricks.com` inbox can complete that OTP. So the domain check is as strong as
Clerk's email verification — an outsider cannot self-assign `@databricks.com`.
The backend enforces this on every `/api/admin/*` call; the frontend routing is
convenience, not the boundary.

## Out of scope
- Retiring the shared password (kept as fallback per decision 2).
- Any change to what the admin cockpit does once you are in it.
- Per-user Databricks roles/permissions beyond "is `@databricks.com`".
- Clerk Organizations.

## Success criteria
1. A `@databricks.com` Clerk sign-in lands in the admin cockpit without entering
   the shared password.
2. A non-`@databricks.com` Clerk sign-in lands on the partner portal (onboarding
   or board), exactly as today.
3. `/api/admin/*` accepts a valid `@databricks.com` Clerk token OR the shared
   password cookie, and rejects everything else with 401.
4. The shared-password login still works unchanged for anyone using it.
5. `isDatabricksEmail` matches only exact `...@databricks.com` addresses,
   case-insensitively, and is defined once per frontend/backend (not duplicated
   inline).
