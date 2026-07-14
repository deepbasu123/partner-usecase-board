# Partner Use-Case Board

A lightweight pilot where Databricks posts use cases needing partner help, GT
partners sign up by email and browse a live board, submit a structured
expression of interest (EOI), and Databricks gets notified and compares
responses.

## 🚀 Live on Vercel + Neon (this branch)

This branch (`vercel-neon-deploy`) runs the whole app on **Vercel free (Hobby)**
tier with **Neon free** tier Postgres — no Databricks account needed.

- **Live URL:** https://partner-usecase-board.vercel.app
  - Public partner portal at `/`
  - Admin portal at `/admin` (password-gated; see below)
- **One Vercel project** serves both React SPAs (portal at `/`, admin under
  `/admin/`) plus one FastAPI Python serverless function at `/api/*`
  (`board_api/`, entry `api/index.py`).
- **Neon** is plain Postgres — the function connects via a single `DATABASE_URL`
  (Neon **pooled** connection string, `?sslmode=require` only; do **not** include
  `channel_binding=require` — PgBouncer transaction mode rejects it).

### Admin access (replaces Databricks SSO)

On Vercel there is no workspace SSO, so the admin portal is gated by a
**shared password** (`ADMIN_PASSWORD` env var). `POST /api/admin/login` mints a
signed cookie and every `/api/admin/*` data route requires it (401 otherwise).
This is fine for a pilot but weaker than SSO — rotate the password in the Vercel
dashboard and treat it as a shared secret.

### Environment variables (set in Vercel, never committed)

See `.env.example`. Required: `DATABASE_URL`, `SESSION_SECRET`,
`ADMIN_SESSION_SECRET`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` (+ `COOKIE_SECURE=true`).

### Free-tier notes

- **Vercel Hobby is non-commercial/personal use only** per Vercel's ToS. This is
  deployed as a personal pilot; a real/commercial deployment needs Vercel Pro.
- **Neon free autosuspends after ~5 min idle**, so the first request after a
  quiet spell is a few seconds slow (cold start). Normal for this tier.

### Known limitations (harden before real partner data)

An independent verification pass (all core security checks passed — admin routes
are properly gated, no data/secret leaks, no SSO wall) flagged two items to
harden before a broad rollout:

- **No rate limiting on `POST /api/signup`** — anyone can create partner rows in
  bulk (email namespace is open; no verification). Add throttling / email
  verification before public promotion.
- **No brute-force protection on `POST /api/admin/login`** — a short shared
  password with no lockout. Use a strong password and add rate limiting.

Neither is critical for an internal demo; both matter for production.

### Deploy

```bash
npx vercel link --project partner-usecase-board --scope <team>   # once
# set the 5 env vars: npx vercel env add <NAME> production
npx vercel deploy --prod
```

`build.sh` builds both frontends into one `dist/` (portal at root, admin under
`/admin/`); `vercel.json` wires the routes. Seed a fresh Neon DB with
`db/schema.sql` then `db/seed_full.sql` (9 cases / 10 partners / 17 responses).

---

The rest of this README describes the original **Databricks Apps + Lakebase**
architecture (still the reference implementation on `main`).

## Architecture — two surfaces, one Lakebase

Databricks Apps **cannot be public**
([docs](https://docs.databricks.com/en/dev-tools/databricks-apps/permissions.html):
*"You can't make Databricks apps public. Anonymous access and bypassing SSO are
not supported."*). So the partner-facing surface is hosted **outside** Databricks
Apps, and only the admin surface is a Databricks App. Both share one Lakebase.

```
 PARTNERS (no Databricks account)        DATABRICKS (account + partner team)
        │                                          │
        ▼                                          ▼
 PUBLIC PARTNER PORTAL                     ADMIN COCKPIT
 React SPA + FastAPI on Cloud Run          Databricks App (workspace SSO)
 • sign up (email + company, no pw)        • post / close use cases
 • browse open use cases                   • view responses per case
 • submit EOI                              • partner directory
        │                                          │
        └──────────────┬───────────────────────────┘
                       ▼
              LAKEBASE (Postgres) — single source of truth
              partners · use_cases · responses
                       │
                       ▼  email on: signup · new case · new EOI
```

## Layout

| Path | What |
|---|---|
| `db/` | `schema.sql` (3 tables) + idempotent `seed.sql` |
| `portal_backend/` | FastAPI: public API, Lakebase (M2M SP auth), sessions, email → Cloud Run |
| `portal-frontend/` | React SPA (board, signup, EOI) |
| `admin-app/` | Databricks App: FastAPI + React (post/manage cases, responses, partners) |
| `common/email.py` | Canonical email module (copied into each backend) |
| `deploy/` | Provision + deploy scripts |
| `docs/superpowers/` | Design spec + implementation plan |

## Local development

```bash
# one-time: venv + deps
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r portal_backend/requirements.txt

# run the full backend test suite against an ephemeral Postgres 16
./run_tests.sh

# portal frontend
cd portal-frontend && npm install && npm run dev     # :5173, proxies /api to :8000
# admin frontend
cd admin-app/frontend && npm install && npm run dev  # :5174, proxies /api to :8001
```

**Test status:** portal 30 tests, admin 7 tests — all green. Full cross-app loop
verified live against local Postgres and in a browser.

## Status

| Piece | State |
|---|---|
| DB schema + seed | ✅ built, verified on Postgres 16 |
| Portal backend (API, sessions, Lakebase, email) | ✅ built + tested |
| Portal frontend (React SPA) | ✅ built + browser-tested |
| Admin app (backend + React) | ✅ built + browser-tested |
| Email transport | ⛔ stub (`NotImplementedError`) — pending decision + approval |
| Cross-cloud Lakebase connectivity | ⚠️ NOT proven — needs the Task 0 spike |
| Cloud Run deploy | ⚠️ not done — needs GCP auth + go-ahead |
| Admin Databricks App deploy | ⚠️ not done — needs workspace + permissions block |

See `DEPLOY.md` for the go-live checklist and the open decisions.
