# Partner Use-Case Board — Vercel + Neon Deployment Design

**Date:** 2026-07-14
**Branch:** `vercel-neon-deploy` (off `build-pilot`, in `github.com/deepbasu123/partner-usecase-board`)
**Goal:** Deploy the whole board (public portal + admin cockpit) to **Vercel free (Hobby)** tier with **Neon free** tier as the Postgres backend, replacing Databricks Apps + Lakebase.

## Decisions locked with the user
- **Both surfaces on Vercel**, admin gated by a **shared password** (no Databricks SSO on Vercel).
- Code lives in the **existing repo, new branch** (`vercel-neon-deploy`).
- **Proceed on the free tier** despite Vercel Hobby's non-commercial ToS (accepted as low-risk for a personal pilot/demo).
- **Seed Neon with the existing sample data** (10 cases / 11 partners / 17 responses — all fictional, already scrubbed).

## Verified technical facts (checked against official Vercel + Neon docs, Sonnet verifier, 2026-07-14)
1. **Vercel Hobby runs Python serverless functions** and installs from a root `requirements.txt`. FastAPI (ASGI) exposes an `app` variable. ✓
2. **Single-function + rewrite pattern works** on Hobby: one Python function handles all FastAPI routes internally; `vercel.json` rewrites `/api/(.*)` to it. The newer "Services" feature is *ambiguous* on Hobby (docs show a "Permissions Required" badge), so we deliberately **avoid Services** and use the classic single-function pattern.
3. **Hobby function limits:** 300 s max duration, 2 GB memory, 500 MB bundle. FastAPI + psycopg is well under. ✓
4. **Hobby = non-commercial use only** per Vercel ToS. Accepted by user for this pilot.
5. **Two separate SPAs at `/` and `/admin` with two build outputs is NOT cleanly supported** (can't set two `outputDirectory` values). → We build the admin SPA into a **`/admin/` subfolder** of the portal's single output dir (Vite `base: '/admin/'`).
6. **Neon free tier:** 0.5 GB storage, 100 CU-hours/mo, **autosuspends after 5 min idle** (cold-start latency on first request; cannot be disabled on free tier). Fine for a demo. ✓
7. **Neon pooled connection string** (PgBouncer, transaction mode) works with **psycopg v3**. **CRITICAL:** use `?sslmode=require` ONLY on the `-pooler` endpoint — **do NOT include `channel_binding=require`** (PgBouncer transaction mode rejects SCRAM channel binding, even though Neon's copy-paste string includes it).
8. **psycopg[binary]** ships manylinux wheels compatible with Vercel's runtime. Use module-level connection reuse where possible; open per-request connections via context managers and rely on the Neon pooler.

## Architecture

One Vercel project, one Neon database:

```
Vercel project (connected to repo branch vercel-neon-deploy)
├─ /              → portal SPA        (portal-frontend build → dist/)
├─ /admin         → admin SPA         (admin build → dist/admin/, Vite base=/admin/)
├─ /api/*         → ONE FastAPI function (api/index.py) merging BOTH backends
└─ Neon Postgres  ← function connects via DATABASE_URL (pooled, sslmode=require)
```

Same-origin for everything → CORS is no longer needed; session cookies are naturally first-party.

## Components

### 1. Database (Neon)
- Plain Postgres. Existing `db/schema.sql` ports **as-is** — `pgcrypto` (for `gen_random_uuid()`), `uuid`, `timestamptz` all supported on Neon.
- Apply `db/schema.sql` then `db/seed.sql` to the Neon `partner_board` (or default `neondb`) database via `psql`/SDK once, at setup.

### 2. Backend — one merged FastAPI app (`api/index.py` + a backend package)
- Merge `portal_backend` (public routes) and `admin-app/backend` (admin routes) into a **single FastAPI `app`** the Vercel function serves.
- **New DB module** reads a single `DATABASE_URL` env var (Neon pooled string) and connects with psycopg v3. **Delete** the Databricks SDK / Lakebase-credential-minting path from both old `db.py` files. Keep the UUID-as-text loader (OID 2950) and `dict_row` — still needed for clean JSON/cookie serialization.
- Public routes unchanged in behavior: `POST /api/signup`, `GET /api/me`, `GET /api/use-cases`, `GET /api/use-cases/{id}`, `POST /api/use-cases/{id}/responses`.
- Admin routes gated (see auth). Paths unchanged: `/api/admin/use-cases` (GET/POST), `/api/admin/use-cases/{id}` (PATCH), `/api/admin/use-cases/{id}/responses`, `/api/admin/partners`, `/api/admin/whoami`, plus new `/api/admin/login`.

### 3. Admin auth (replaces Databricks SSO)
- `POST /api/admin/login` — compares submitted password to `ADMIN_PASSWORD` env var; on match, sets a **signed admin cookie** (itsdangerous, distinct salt from the portal session).
- A FastAPI dependency guards **all** `/api/admin/*` data routes: valid admin cookie → allow, else `401`. (The admin JS being publicly downloadable is harmless — every data call is server-gated.)
- `posted_by` (was the SSO `X-Forwarded-Email` header) becomes a configurable fixed value from `ADMIN_EMAIL` env var, since a shared password carries no per-user identity.
- Admin SPA gets a minimal login screen that calls `/api/admin/login`, then loads the existing cockpit on success; a `401` from any admin call bounces back to login.

### 4. Frontends (minimal change)
- **Portal:** unchanged. Already uses relative `/api` calls and `credentials:"include"`.
- **Admin:** set Vite `base: '/admin/'` so asset URLs resolve under `/admin/`; add the login screen + wrap existing API calls with `credentials:"include"`. Existing design/branding untouched.

### 5. Vercel config
- Root `requirements.txt`: `fastapi`, `psycopg[binary]`, `itsdangerous`, `pydantic[email]` (+ `uvicorn` only for local dev).
- `api/index.py`: imports the merged `app`.
- `vercel.json`:
  - `buildCommand`: build portal → `dist/`, build admin → `dist/admin/`.
  - `outputDirectory`: `dist`.
  - `rewrites` (ordered): `/api/(.*)` → `/api` (Python function); `/admin/(.*)` and `/admin` → `/admin/index.html`; `/(.*)` → `/index.html` (portal SPA fallback, last).

## Environment variables (set in Vercel dashboard, never committed)
- `DATABASE_URL` — Neon **pooled** connection string, `?sslmode=require` (no `channel_binding`).
- `SESSION_SECRET` — random secret for partner session cookies.
- `ADMIN_SESSION_SECRET` — random secret for admin cookies (separate from above).
- `ADMIN_PASSWORD` — the shared admin login password.
- `ADMIN_EMAIL` — value used for `posted_by` on new cases.
- `COOKIE_SECURE=true` (Vercel is https).

## Data flow
1. Partner visits `/` → portal SPA → `GET /api/use-cases` → function → Neon.
2. Signup → `POST /api/signup` → upsert partner in Neon → signed session cookie.
3. EOI → `POST /api/use-cases/{id}/responses` (session required) → insert → email stub no-ops.
4. Admin visits `/admin` → login screen → `POST /api/admin/login` → admin cookie → cockpit calls succeed.

## Error handling
- Missing `DATABASE_URL` at runtime → function raises a clear config error (mirrors the old explicit-config guard).
- Duplicate EOI → `409` (existing `DuplicateResponse` path preserved).
- Admin route without valid cookie → `401` → SPA shows login.
- Neon cold start after autosuspend → first request slow (accepted); nothing to code.
- Email transport stays a safe no-op stub (no sends without explicit approval).

## Testing
- Keep existing pytest suites (portal 30 + admin 7). Update fixtures to point at a local Postgres via `DATABASE_URL` instead of the Lakebase-shaped `PG*` vars.
- Add tests for the new admin login/guard: correct password → cookie → admin call `200`; no/blank cookie → `401`.
- Local end-to-end smoke: `vercel dev` (or run the merged app under uvicorn + Vite proxies) against a local or Neon dev database, exercise signup → board → EOI → admin login → view responses.
- Post-deploy smoke on the live Vercel URL: `/healthz`, board loads, signup works, admin login gates correctly.

## Out of scope (unchanged from prior state)
- Real email sending (stub only; needs separate approval).
- The Databricks admin app / Lakebase (left intact as the reference implementation; not torn down by this work).
- GitHub Pages landing page (untouched; can be re-pointed to the Vercel URL later).

## Non-goals / risks noted
- Non-commercial ToS on Hobby (accepted).
- Shared-password admin is weaker than SSO — acceptable for a pilot; documented in the README.
- Free-tier autosuspend cold starts.
