# Partner Auth (Clerk) + Notification Email (Resend) — Design Spec

**Date:** 2026-07-15
**Author:** Databricks Solutions Architect
**Status:** Approved design (auth); email section pending final review
**Builds on:** [2026-07-10-partner-usecase-board-design.md](2026-07-10-partner-usecase-board-design.md)

> Two related but independent changes to partner-facing comms:
> **(A) Clerk** replaces the passwordless-cookie sign-in;
> **(B) Resend** becomes the real transport for the board's notification emails
> (welcome / new use case / new EOI), which were previously stubbed.
> They share no code dependency — Clerk gates identity; Resend sends mail — and
> can be implemented in either order. Section A is the original approved design;
> Section B was added when Resend was chosen as the transport.

## Problem

The partner portal signs people in with a passwordless model of our own: enter an
email + company, we upsert a `partners` row and sign the id into a cookie
(`board_api/sessions.py`). There is no proof the email is real — anyone can type
any address. Separately, the board's own notification emails (welcome, new use
case, new EOI) are stubbed and never send (`board_api/email.py::_send` raises
`NotImplementedError`, swallowed by `_safe`).

We want partners to sign in against a real identity provider so their email is
actually verified, and so we stop maintaining hand-rolled session code. Clerk is
the chosen provider.

## Goal & scope

Two independent changes. **(A)** Replace the portal's passwordless-cookie auth
with **Clerk**, using **email-code (passwordless) sign-in** — every partner ends
up with a Clerk-verified email. **(B)** Wire **Resend** as the real transport so
the board's notification emails (welcome / new-case / new-EOI), previously
stubbed, actually send. The board's data model and the "raise your hand" loop are
unchanged; auth changes *how a partner proves who they are*, and Resend changes
*whether notification mail leaves the building*.

**In scope**
- Clerk sign-in for the partner portal (email code, no password).
- Capturing `company` in a one-field onboarding step after first sign-in.
- Backend verification of Clerk session JWTs (networkless, against Clerk's JWKS).
- Migrating the existing EOI/session gate from the cookie to the Clerk identity.
- **Resend as the real transport for the board's notification emails** — wiring
  `board_api/email.py::_send()` to Resend so the welcome / new-use-case / new-EOI
  messages actually send (see Section B). Note: Clerk's *auth* emails (the
  verification code, reset) are sent by Clerk itself and are unrelated to Resend.

**Explicitly out of scope**
- A custom/verified sending domain. Per decision, we send only from Resend's
  shared `onboarding@resend.dev`. This has a hard deliverability ceiling — see
  Section B and Risks.
- Admin cockpit auth — the shared-password gate (`board_api/admin_auth.py`) is
  untouched. This is partner-side only.
- Clerk Organizations. Company is a single text field on the partner, as today.
- Resend audiences / broadcasts / contacts — we use only transactional
  single-message sends.

## Decisions locked (from brainstorming)

1. **Email-code passwordless** Clerk sign-in (no password, no social for the pilot).
2. **Company via onboarding** — a one-field screen after first sign-in, not a
   Clerk custom field and not Clerk Organizations.
3. **Networkless JWT verification** on the backend — verify the Clerk session
   JWT against Clerk's published JWKS (PyJWT + cached keys), no per-request call
   to Clerk.
4. **User provisions the Clerk account** and supplies the publishable + secret
   keys before implementation/testing.
5. **Resend is the notification-email transport**, called from the backend via
   its HTTP API (not the MCP — see Section B).
6. **No custom sending domain — ever.** Always send from Resend's shared
   `onboarding@resend.dev`. Accepted consequence: mail only reliably reaches the
   Resend account-owner address until/unless a domain is verified (which we are
   not doing).
7. **No email is sent without an approved draft** (per user's standing rule),
   including test sends.

# Section A — Clerk authentication

## Architecture

One new trust boundary. Clerk owns identity and email verification. Our FastAPI
backend trusts Clerk-signed JWTs (verified locally against Clerk's public keys).
Neon remains the source of truth for the partner *profile* (`company`) and all
board data (use cases, responses). The SPA holds a Clerk session and attaches its
JWT to every API call.

```
Partner
  │
  ├─ Clerk <SignIn/>  (enter email → 6-digit code emailed by Clerk → verified)
  │        └─ Clerk issues a session JWT (held by the SPA)
  │
  ├─ SPA calls  GET /api/me   with  Authorization: Bearer <clerk-jwt>
  │        backend verifies JWT vs Clerk JWKS (cached), reads email + sub
  │        ├─ partners row for this email/clerk_user_id exists → return profile
  │        └─ none → 200 { onboarding_required: true }
  │
  ├─ if onboarding_required →  <Onboarding/>  one field: "What firm are you with?"
  │        └─ POST /api/onboarding { company }
  │              creates or links the partners row, stamps clerk_user_id
  │
  └─ browse board + POST EOIs, gated on the verified Clerk identity
```

## Component changes

### Frontend (`portal-frontend/`, Vite React SPA)
- Add `@clerk/react` (the current Vite/React SDK as of Clerk Core 3, Mar 2026;
  the pre-Core-3 name was `@clerk/clerk-react` — same exports, rename only). Wrap
  the app in `<ClerkProvider>` (publishable key from build-time env). Confirm the
  exact latest package name at install time via the Vercel build.
- Replace `components/SignupForm.tsx` with a Clerk sign-in surface
  (`SignInPage.tsx`) using Clerk's drop-in `<SignIn/>` configured for email code.
- New `components/Onboarding.tsx` — single "company" field, shown only when
  `/api/me` reports `onboarding_required`.
- `api.ts` — attach the Clerk session token as `Authorization: Bearer <jwt>` on
  every request; stop relying on the `credentials:"include"` cookie. The token is
  read from Clerk's SDK (`getToken()`), not from a cookie we manage.
- `App.tsx` — derive auth state from Clerk (`useAuth`/`useUser`) plus a
  `/api/me` profile fetch, replacing the cookie-restore `useEffect`.

### Backend (`board_api/`, FastAPI)
- New `clerk_auth.py`:
  - Fetch and cache Clerk's JWKS (public keys). Verify the incoming session JWT's
    signature, issuer, and expiry with PyJWT. No network call per request once
    keys are cached; refresh on key-not-found / cache miss.
  - Expose a `require_partner` dependency that returns the verified identity
    (email + Clerk `sub`) or raises 401. This replaces
    `sessions.read_session_cookie(...)` in `routes_public.py`.
- `routes_public.py`:
  - `GET /api/me` — verify token; return the partner profile if one exists, else
    `{ onboarding_required: true }`.
  - `POST /api/onboarding { company }` — new; create or link the `partners` row
    for the verified email, stamp `clerk_user_id`, return the profile. Reuses the
    existing non-blank `company` validation.
  - `POST /api/use-cases/{id}/responses` and any other partner-gated route swap
    the cookie check for the `require_partner` dependency. EOI behaviour
    (duplicate → 409, closed case → 409, missing → 404) is otherwise unchanged.
- Retire `board_api/sessions.py` (portal signed-cookie) once nothing imports it.
  **`admin_auth.py` is untouched.**

### Data model (`db/`)
- `ALTER TABLE partners ADD COLUMN clerk_user_id text UNIQUE;` — nullable.
- Partner rows are keyed on `email` (already `UNIQUE`). Because the 10 seeded
  partners have real emails, the first time such a partner signs in with a
  matching Clerk email, onboarding **links** the existing row (and stamps
  `clerk_user_id`) rather than creating a duplicate — so their historical
  responses are preserved.
- `company` stays `NOT NULL`; it is populated at onboarding for new partners and
  already present for seeded ones. The legacy `verified` column becomes
  redundant (Clerk guarantees a verified email) but is left in place to avoid a
  destructive change; new rows default it to `true`.

### Environment / config (Vercel prod)
- Add `CLERK_PUBLISHABLE_KEY` (exposed to the frontend build; Clerk publishable
  keys are non-secret by design).
- Add `CLERK_SECRET_KEY` (backend only, never shipped to the client).
- Add the Clerk **issuer / JWKS URL** for this app (backend), used to fetch the
  verification keys. Shape is either the per-instance Frontend API
  `https://<frontend-api>/.well-known/jwks.json` or the Backend API
  `https://api.clerk.com/v1/jwks`; exact value comes from the Clerk dashboard
  once the app exists.
- `SESSION_SECRET` — retained only if any portal cookie remains; removed if the
  cookie path is fully retired. `ADMIN_*` env vars are unchanged.

## Error handling
- Missing / malformed / expired / bad-signature JWT → **401**; the SPA reopens
  the Clerk sign-in surface.
- Valid token but no partner profile yet → **not an error**: `/api/me` returns
  `{ onboarding_required: true }` and the SPA routes to onboarding.
- Onboarding with blank/whitespace company → **422** (reuses the existing
  `company_not_blank` validator).
- Clerk JWKS fetch failure with no cached key → **503** (transient); a cached key
  is used whenever available so a brief Clerk/network blip doesn't break sign-in
  for already-issued tokens.

## Testing strategy
- **Backend (automated):** unit-test `clerk_auth` verification and
  `require_partner` with a **locally minted test JWT** signed by a test key
  injected as the JWKS — no network, no real Clerk call. Rework the existing EOI /
  duplicate / validation tests to authenticate with a Bearer token instead of the
  signed cookie. Add tests for `POST /api/onboarding` (new partner creates a row;
  seeded email links the existing row without duplicating).
- **Frontend / real sign-in (manual):** the actual Clerk email-code sign-in UI
  **cannot be exercised by curl** the way the current join flow was. It is
  verified manually in a browser against a Vercel **preview** deployment once the
  Clerk keys are set. This is called out because it is the one part not covered by
  the automated suite.
- **Regression:** the read-only API checks (`/healthz`, `/api/use-cases`) and the
  admin shared-password gate must still pass unchanged.

# Section B — Notification email via Resend

## What sends, and from where
Resend replaces the stubbed transport in `board_api/email.py`. The three existing
notification functions keep their signatures and callers; only `_send()` is
implemented:
- `send_welcome` — to a partner after they onboard.
- `send_new_use_case` — to registered partners when the admin posts a case.
- `send_new_eoi` — to the poster / notify list when a partner submits an EOI.

**Runtime path is the Resend HTTP API, not the MCP.** The MCP server is an
*agent-time* tool (for me, to test sends and manage domains during
development/verification). The running app on Vercel cannot use an MCP; its
backend calls Resend's REST API (`POST https://api.resend.com/emails`) with the
`re_…` key read from an env var. So `_send()` becomes a small HTTPS call
(via the `resend` Python SDK or plain `httpx`/`urllib`), preserving the
best-effort `_safe()` wrapper so a mail failure never breaks the HTTP request.

## From-address & the deliverability ceiling (decision)
No custom domain will be verified. All mail is sent from Resend's shared
**`onboarding@resend.dev`**. Consequence, verified live against this account
(`GET /domains` → zero verified domains):

> With no verified domain, Resend only reliably delivers to the **Resend
> account-owner's own email address**. Mail to arbitrary partner inboxes is not
> deliverable until a domain is verified.

This is acceptable for the pilot and for proving the wiring, but it means the
"notify all partners when a case is posted" fan-out **will not actually reach
external partners** yet. The spec records this as a known, accepted limitation
rather than implying full delivery. `EMAIL_FROM` defaults to
`onboarding@resend.dev`.

## Component changes (email)
- `board_api/email.py::_send()` — implement against Resend: build the payload
  (`from`, `to`, `subject`, `text`), POST to the Resend API, raise on non-2xx
  (caught by `_safe`). `FROM_ADDR`/`EMAIL_FROM` default to `onboarding@resend.dev`.
- No change to `send_welcome` / `send_new_use_case` / `send_new_eoi` or their
  call sites — they already exist and are wired into signup, admin case-create,
  and EOI submission.
- The canonical copy note in `email.py` still applies (edit in one place).

## Environment / config (email)
- Add `RESEND_API_KEY` (backend only, secret) to Vercel prod.
- `EMAIL_FROM` — optional; defaults to `onboarding@resend.dev`.
- Optionally `EOI_NOTIFY_EMAILS` (already read by `routes_public.py`) set to the
  Resend account-owner address so EOI notifications are actually deliverable in
  the pilot.

## Testing strategy (email)
- **Unit:** mock the Resend HTTP call; assert `_send` posts the right payload and
  that `_safe` still swallows a simulated non-2xx so signup/EOI never 500.
- **Live send (gated on approval):** exactly one real test send from
  `onboarding@resend.dev` to the Resend account-owner address, to confirm the key
  + payload work end-to-end. **Per the standing rule, I will show the exact draft
  (from/to/subject/body) and get explicit approval before sending it** — this
  applies even though it's a test to your own address. The MCP or a one-off API
  call can drive this test.
- I will **not** attempt sends to the seeded fictional partner addresses (they're
  fake and, per the ceiling above, undeliverable anyway).

## Prerequisites & external dependencies
- **Clerk account + application (user-provided).** Cannot be created on the
  user's behalf. Needs: an application with **email-code** sign-in enabled, and
  the **publishable key** + **secret key** + issuer/JWKS URL handed over before
  any wiring or testing. This is the blocking prerequisite for Section A —
  analogous to an interactive `gcloud auth login`.
- **Resend API key (present).** Found at `~/Documents/resend token.rtf`
  (`re_…`, verified live: key works, account has **no** verified domain). Goes
  into Vercel as `RESEND_API_KEY`. No further user action needed for Section B
  beyond approving the one test send.

## Risks & caveats
- **Supply-chain lockdown.** Vercel's cloud build installs `@clerk/react` and the
  backend JWT + Resend dependencies without issue, but **local** install/test
  hits the npm/PyPI lockdown on this machine. Plan to lean on the Vercel build +
  preview for anything that needs the real packages, and mock/inject for local
  unit tests.
- **Two-system-of-record care.** Identity now lives in Clerk; profile lives in
  Neon. The email is the join key. If a partner changes their email in Clerk, the
  link is by `clerk_user_id` (stamped at onboarding), so the profile follows the
  Clerk user, not the email string.
- **Email deliverability ceiling.** With Resend's shared `onboarding@resend.dev`
  and no verified domain, only the account-owner address reliably receives mail;
  external-partner notifications won't actually deliver until a domain is verified
  (out of scope). See Section B.
- **Approval gate on sends.** No email — including test sends — goes out without
  showing the draft and getting explicit approval first.

## Success criteria
1. A partner signs in with only an email + a Clerk-emailed code (no password, no
   self-declared unverified email).
2. A first-time partner is asked for their company once, then can browse and
   submit EOIs; a returning partner skips onboarding.
3. A seeded partner signing in with their existing email keeps their prior
   responses (row linked, not duplicated).
4. The backend rejects any request without a valid Clerk JWT (401), and the admin
   cockpit is entirely unaffected.
5. The automated backend suite passes with token-based auth; the real sign-in UI
   is manually verified on a Vercel preview.
6. `board_api/email.py::_send()` sends through Resend; one approved test send from
   `onboarding@resend.dev` to the account-owner address is received; a Resend
   failure is still swallowed by `_safe` so signup/EOI never error.
