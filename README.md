# Partner Use-Case Board

A lightweight pilot where Databricks posts use cases needing partner help, GT
partners sign up by email and browse a live board, submit a structured
expression of interest (EOI), and Databricks gets notified and compares
responses.

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
# one-time: venv + deps (internal PyPI proxy under the lockdown)
python3.13 -m venv .venv && . .venv/bin/activate
pip install --index-url https://pypi-proxy.dev.databricks.com/simple -r portal_backend/requirements.txt

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
