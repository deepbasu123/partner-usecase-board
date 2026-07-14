# Partner Use-Case Board — Vercel + Neon Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the full Partner Use-Case Board (public portal + admin cockpit) to Vercel's free Hobby tier with Neon free-tier Postgres, replacing Databricks Apps + Lakebase.

**Architecture:** One Vercel project serves two React SPAs (portal at `/`, admin at `/admin`) plus one FastAPI Python serverless function under `/api`. The function merges both former backends and talks to Neon via a single `DATABASE_URL`. Admin routes are gated by a shared password + signed cookie, replacing Databricks workspace SSO.

**Tech Stack:** FastAPI, psycopg v3, itsdangerous, Pydantic; React 18 + Vite; Vercel `@vercel/python` + `@vercel/static-build`; Neon Postgres (pooled/PgBouncer connection).

## Global Constraints
- **Neon project:** use the EXISTING project `databricks-partner` (id `ancient-wave-37020806`, org `org-lingering-fog-39386434`, region aws-ap-southeast-2, PG18). Do NOT create a new Neon project.
- **Neon connection:** pooled (`-pooler`) endpoint, `?sslmode=require` ONLY — never `channel_binding=require` (PgBouncer transaction mode rejects it).
- **Vercel tier:** Hobby (free). Avoid the "Services" feature (ambiguous on Hobby); use `builds` + `routes` in `vercel.json`.
- **Secrets:** `DATABASE_URL`, `SESSION_SECRET`, `ADMIN_SESSION_SECRET`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` live ONLY in Vercel env vars + local `.env` (gitignored). Never commit them.
- **Email:** stays a no-op stub. No real sends.
- **Databricks admin app + Lakebase:** left intact as the reference implementation. This plan does not touch or tear them down.
- **GitHub:** repo `deepbasu123/partner-usecase-board`, branch `vercel-neon-deploy`. Push with the PAT from `~/Documents/github token new.rtf` (inline, never stored in git config).
- **Sample data:** port the 10 use cases / 11 partners / 17 responses from `admin-app/seed_sample_data.py` into a portable `db/seed_full.sql`.

---

### Task 1: Provision Neon — schema + full seed

**Files:**
- Create: `db/seed_full.sql` (portable INSERTs for the 10/11/17 sample dataset)
- Use: `db/schema.sql` (unchanged — already portable Postgres)

**Interfaces:**
- Produces: a populated Neon `neondb` database with tables `partners`, `use_cases`, `responses`; a pooled `DATABASE_URL`.

- [ ] **Step 1:** Apply `db/schema.sql` to the Neon project `ancient-wave-37020806` (default DB `neondb`) via the Neon MCP `run_sql` (or psql). Creates `pgcrypto`, the 3 tables, indexes.
- [ ] **Step 2:** Author `db/seed_full.sql` from `admin-app/seed_sample_data.py`: the 8 named USE_CASES (7 open, 1 closed "Marketing attribution & CDP") PLUS the original "Workforce Management solution — ANZ" open case from `db/seed.sql` (= 9 cases... note: live count was 10; include the WFM case to reach the real dataset), 10 PARTNERS from the script (+ any 11th that was added live), and the 17 RESPONSES resolved by title/company via CTEs. Use `WHERE NOT EXISTS` guards so it is idempotent. `posted_by` = `admin@example.com`.
- [ ] **Step 3:** Apply `db/seed_full.sql` to Neon.
- [ ] **Step 4:** Verify counts via `run_sql`: `SELECT (SELECT count(*) FROM use_cases) uc, (SELECT count(*) FROM partners) p, (SELECT count(*) FROM responses) r;` Expected: uc≈10, p≈10–11, r=17.
- [ ] **Step 5:** Capture the pooled connection string (Neon console / MCP) → this becomes `DATABASE_URL`. Confirm host contains `-pooler` and query string is exactly `?sslmode=require`.
- [ ] **Step 6:** Commit `db/seed_full.sql`.

---

### Task 2: Merged backend package `board_api/`

Create one importable package the Vercel function loads, merging both backends onto a Neon `DATABASE_URL`.

**Files:**
- Create: `board_api/__init__.py`, `board_api/db.py`, `board_api/models.py`, `board_api/email.py` (copy of `common/email.py`), `board_api/sessions.py`, `board_api/admin_auth.py`, `board_api/routes_public.py`, `board_api/routes_admin.py`, `board_api/app.py`
- Test: `board_api/tests/conftest.py`, `board_api/tests/test_public.py`, `board_api/tests/test_admin.py`, `board_api/tests/test_admin_auth.py`
- Reference (do not modify): `portal_backend/*`, `admin-app/backend/*`

**Interfaces:**
- Produces:
  - `board_api.app:app` — the merged FastAPI `ASGI` app.
  - `board_api.db` — functions: `list_open_use_cases()`, `get_use_case(uc_id)`, `get_or_create_partner(email, company, contact_name)`, `create_response(use_case_id, partner_id, approach)` (raises `DuplicateResponse`), `get_partner(partner_id)`, `list_all_partners()`, `create_use_case(title, description, industry, region, posted_by)`, `set_status(uc_id, status)`, `list_all_use_cases()`, `list_responses_for(uc_id)`. Connection from `DATABASE_URL` only.
  - `board_api.sessions` — `make_session_cookie(pid)`, `read_session_cookie(token)`, `SESSION_COOKIE_NAME="pub_session"`.
  - `board_api.admin_auth` — `make_admin_cookie()`, `is_valid_admin(token)`, `ADMIN_COOKIE_NAME="admin_session"`, `require_admin` (FastAPI dependency raising 401), `check_password(pw)`.

- [ ] **Step 1: `board_api/db.py`** — one `DATABASE_URL`-based connection. Full code:

```python
"""Neon Postgres access for the merged Partner Board API.

Single connection source: the DATABASE_URL env var (Neon pooled string).
No Databricks SDK, no credential minting — plain Postgres.
"""
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.string import TextLoader

_UUID_OID = 2950  # load uuid columns as str for clean JSON/cookie serialization


class _UuidAsText(TextLoader):
    """Return uuid values as str."""


class DuplicateResponse(Exception):
    """Raised when a partner submits a second EOI for the same use case."""


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required (Neon pooled connection string).")
    return dsn


def get_conn():
    conn = psycopg.connect(_dsn(), row_factory=dict_row, autocommit=True)
    conn.adapters.register_loader(_UUID_OID, _UuidAsText)
    return conn


def list_open_use_cases():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, title, description, industry, region, status, created_at "
                    "FROM use_cases WHERE status='open' ORDER BY created_at DESC")
        return cur.fetchall()


def get_use_case(uc_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, title, description, industry, region, status, posted_by, created_at "
                    "FROM use_cases WHERE id = %s", (uc_id,))
        return cur.fetchone()


def get_or_create_partner(email, company, contact_name):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO partners (email, company, contact_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET company = EXCLUDED.company "
            "RETURNING id, email, company, contact_name, created_at",
            (email, company, contact_name))
        return cur.fetchone()


def create_response(use_case_id, partner_id, approach):
    try:
        with get_conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO responses (use_case_id, partner_id, approach) "
                "VALUES (%s, %s, %s) "
                "RETURNING id, use_case_id, partner_id, approach, created_at",
                (use_case_id, partner_id, approach))
            return cur.fetchone()
    except psycopg.errors.UniqueViolation:
        raise DuplicateResponse(f"partner {partner_id} already responded to {use_case_id}")


def get_partner(partner_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners WHERE id = %s", (partner_id,))
        return cur.fetchone()


def list_all_partners():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners ORDER BY created_at DESC")
        return cur.fetchall()


def create_use_case(title, description, industry, region, posted_by):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO use_cases (title, description, industry, region, posted_by) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, title, description, industry, region, status, posted_by, created_at",
            (title, description, industry, region, posted_by))
        return cur.fetchone()


def set_status(uc_id, status):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE use_cases SET status = %s, "
            "closed_at = CASE WHEN %s = 'closed' THEN now() ELSE NULL END "
            "WHERE id = %s "
            "RETURNING id, title, description, industry, region, status, "
            "posted_by, created_at, closed_at, "
            "(SELECT count(*) FROM responses r WHERE r.use_case_id = use_cases.id) AS response_count",
            (status, status, uc_id))
        return cur.fetchone()


def list_all_use_cases():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.title, u.description, u.industry, u.region, u.status, "
            "u.posted_by, u.created_at, u.closed_at, "
            "(SELECT count(*) FROM responses r WHERE r.use_case_id = u.id) AS response_count "
            "FROM use_cases u ORDER BY u.created_at DESC")
        return cur.fetchall()


def list_responses_for(uc_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.approach, r.created_at, p.company, p.email, p.contact_name "
            "FROM responses r JOIN partners p ON p.id = r.partner_id "
            "WHERE r.use_case_id = %s ORDER BY r.created_at DESC",
            (uc_id,))
        return cur.fetchall()
```

- [ ] **Step 2:** Copy `common/email.py` → `board_api/email.py` verbatim (logger name `board.email`, stub `_send`). Copy `portal_backend/sessions.py` → `board_api/sessions.py` verbatim.
- [ ] **Step 3: `board_api/models.py`** — union of both model files:

```python
"""Request models for the merged Partner Board API."""
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


class SignupIn(BaseModel):
    email: EmailStr
    company: str
    contact_name: str | None = None

    @field_validator("company")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("company is required")
        return v.strip()


class EoiIn(BaseModel):
    approach: str

    @field_validator("approach")
    @classmethod
    def approach_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("approach is required")
        return v.strip()


class UseCaseIn(BaseModel):
    title: str
    description: str
    industry: str | None = None
    region: str | None = None

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required")
        return v.strip()


class StatusIn(BaseModel):
    status: Literal["open", "closed"]


class AdminLoginIn(BaseModel):
    password: str
```

- [ ] **Step 4: `board_api/admin_auth.py`** — shared-password gate. Full code:

```python
"""Shared-password admin gate (replaces Databricks SSO on Vercel).

A correct password mints a signed admin cookie; every /api/admin/* data route
depends on require_admin, which 401s without a valid cookie.
"""
import logging
import os

from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer, BadSignature

log = logging.getLogger("board.admin_auth")

ADMIN_COOKIE_NAME = "admin_session"
_DEV_DEFAULT = "dev-only-not-secret-admin"
_secret = os.environ.get("ADMIN_SESSION_SECRET", _DEV_DEFAULT)
if _secret == _DEV_DEFAULT:
    log.warning("ADMIN_SESSION_SECRET unset — using insecure dev default.")
_serializer = URLSafeSerializer(_secret, salt="partner-admin")

# No password configured => gate is effectively closed (every check fails).
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def check_password(pw: str) -> bool:
    return bool(_ADMIN_PASSWORD) and pw == _ADMIN_PASSWORD


def make_admin_cookie() -> str:
    return _serializer.dumps({"role": "admin"})


def is_valid_admin(token: str) -> bool:
    if not token:
        return False
    try:
        return _serializer.loads(token).get("role") == "admin"
    except (BadSignature, AttributeError, TypeError):
        return False


def require_admin(request: Request) -> None:
    if not is_valid_admin(request.cookies.get(ADMIN_COOKIE_NAME, "")):
        raise HTTPException(401, "admin login required")
```

- [ ] **Step 5: `board_api/routes_public.py`** — merge `routes_partners.py` + `routes_board.py` + `routes_responses.py` (identical logic; `from . import db, email, sessions`). Endpoints: `POST /api/signup`, `GET /api/me`, `GET /api/use-cases`, `GET /api/use-cases/{uc_id}`, `POST /api/use-cases/{uc_id}/responses`.
- [ ] **Step 6: `board_api/routes_admin.py`** — port `admin-app/backend/routes_admin.py` with two changes: (a) add `dependencies=[Depends(require_admin)]` on the router so every admin data route is gated; (b) `posted_by` comes from `os.environ.get("ADMIN_EMAIL", "admin@example.com")` instead of `X-Forwarded-Email`. Add:

```python
@router.post("/api/admin/login")
def login(body: AdminLoginIn, response: Response):
    if not check_password(body.password):
        raise HTTPException(401, "invalid password")
    response.set_cookie(ADMIN_COOKIE_NAME, make_admin_cookie(),
                        httponly=True, secure=_COOKIE_SECURE, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"ok": True}
```

  The `login` route must NOT be behind `require_admin`. Structure the router so `login` is unguarded and the data routes carry the dependency (e.g. put `login` on a separate `APIRouter()` without the dependency, or use `Depends(require_admin)` per-route on the data endpoints). `whoami` returns `{"email": ADMIN_EMAIL}`.
- [ ] **Step 7: `board_api/app.py`** — merged app:

```python
"""Merged FastAPI app: public portal API + gated admin API, on Neon."""
import os

from fastapi import FastAPI

from . import routes_public, routes_admin

app = FastAPI(title="Partner Use-Case Board — API")
app.include_router(routes_public.router)
app.include_router(routes_admin.public_router)   # /api/admin/login (unguarded)
app.include_router(routes_admin.router)          # /api/admin/* (guarded)


@app.get("/healthz")
def healthz():
    return {"ok": True}
```

  (No CORS middleware needed — same-origin on Vercel. No StaticFiles mount — Vercel serves the SPAs.)
- [ ] **Step 8: Tests** — `board_api/tests/conftest.py` yields `board_api.db` against a local Postgres via `DATABASE_URL` (skip if unset), truncating `responses, partners` between tests. Port `test_admin.py` from `admin-app/backend/tests/test_routes_admin.py` but patch `board_api.routes_admin.db.*`, drop the `X-Forwarded-Email` assertion (now `ADMIN_EMAIL`), and add an admin cookie to each guarded call. Add `test_admin_auth.py`:

```python
from fastapi.testclient import TestClient
from board_api.app import app
from board_api import admin_auth

client = TestClient(app)


def test_admin_route_blocked_without_cookie():
    r = client.get("/api/admin/use-cases")
    assert r.status_code == 401


def test_login_wrong_password_401(monkeypatch):
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "secret")
    r = client.post("/api/admin/login", json={"password": "nope"})
    assert r.status_code == 401


def test_login_then_access(monkeypatch):
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "secret")
    r = client.post("/api/admin/login", json={"password": "secret"})
    assert r.status_code == 200
    assert client.cookies.get(admin_auth.ADMIN_COOKIE_NAME)
```

- [ ] **Step 9:** Run `python -m pytest board_api/tests/ -v` against a local PG (see Task 5 harness). Expected: all pass.
- [ ] **Step 10:** Commit `board_api/`.

---

### Task 3: Vercel function entrypoint + config

**Files:**
- Create: `api/index.py`, `requirements.txt` (root), `vercel.json`, `.vercelignore`, `.env.example`
- Modify: `.gitignore` (add `.env`, `.vercel`)

**Interfaces:**
- Consumes: `board_api.app:app`.
- Produces: a deployable Vercel project routing `/api/*` → the function, `/admin*` → admin SPA, `/*` → portal SPA.

- [ ] **Step 1: `api/index.py`:**

```python
"""Vercel Python entrypoint. Exposes the merged FastAPI app as `app`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board_api.app import app  # noqa: E402
```

- [ ] **Step 2: root `requirements.txt`** (no databricks-sdk, no uvicorn needed at runtime — Vercel provides the server):

```
fastapi==0.137.1
psycopg[binary]==3.3.4
itsdangerous==2.2.0
pydantic==2.9.2
pydantic[email]==2.9.2
```

- [ ] **Step 3: `vercel.json`** (builds + routes; `filesystem` handle serves real assets before SPA fallbacks):

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "builds": [
    { "src": "api/index.py", "use": "@vercel/python" },
    { "src": "portal-frontend/package.json", "use": "@vercel/static-build", "config": { "distDir": "dist" } },
    { "src": "admin-app/frontend/package.json", "use": "@vercel/static-build", "config": { "distDir": "dist" } }
  ],
  "routes": [
    { "src": "/api/(.*)", "dest": "api/index.py" },
    { "src": "/healthz", "dest": "api/index.py" },
    { "src": "/admin/assets/(.*)", "dest": "admin-app/frontend/dist/assets/$1" },
    { "src": "/admin(/.*)?", "dest": "admin-app/frontend/dist/index.html" },
    { "handle": "filesystem" },
    { "src": "/(.*)", "dest": "portal-frontend/dist/index.html" }
  ]
}
```

  NOTE: exact static routing may need adjustment after the first `vercel dev` / deploy; the build phase verifies real behavior and tunes these routes. The admin assets route + base path (Task 4) must agree.
- [ ] **Step 4:** `.vercelignore` excludes `admin-app/backend`, `portal_backend`, `common`, `deploy`, `docs`, `*.png`, `.venv`, `board_api/tests` from the deployment bundle (keep it small; the function only needs `api/` + `board_api/`).
- [ ] **Step 5:** `.env.example` documents every env var (no real values). Add `.env` and `.vercel` to `.gitignore`.
- [ ] **Step 6:** Commit.

---

### Task 4: Admin frontend — base path + login screen

**Files:**
- Modify: `admin-app/frontend/vite.config.ts` (add `base: "/admin/"`)
- Modify: `admin-app/frontend/src/api.ts` (add `credentials: "include"` to every call; add `login`)
- Modify: `admin-app/frontend/src/App.tsx` (gate on login; show login screen on 401)
- Create: `admin-app/frontend/src/components/AdminLogin.tsx`

**Interfaces:**
- Consumes: `POST /api/admin/login {password}`, existing `/api/admin/*`.

- [ ] **Step 1:** `vite.config.ts` — add `base: "/admin/"` so built asset URLs resolve under `/admin/`.
- [ ] **Step 2:** `api.ts` — add `credentials: "include"` to every `fetch`; add `login(password)` → `POST /api/admin/login`; make `json<T>` throw an error carrying `status` so the app can detect 401.
- [ ] **Step 3:** `AdminLogin.tsx` — a minimal password form calling `api.login`, styled with existing `theme.css` classes; on success calls `onAuthed()`.
- [ ] **Step 4:** `App.tsx` — on mount call `api.whoami()`; if it 401s, render `<AdminLogin onAuthed={...}>` instead of the cockpit; on success render the existing cockpit. A 401 from any later call bounces back to login.
- [ ] **Step 5:** `npm --prefix admin-app/frontend run build` — expect `dist/` with assets under `/admin/`. Commit.

---

### Task 5: Local end-to-end verification

**Files:** Create: `run_local.sh` (dev harness: local PG + merged app + both Vite builds)

- [ ] **Step 1:** Write `run_local.sh` mirroring `run_tests.sh`: spin ephemeral PG16, apply `schema.sql` + `seed_full.sql`, export `DATABASE_URL=postgresql://postgres:x@/board?host=/tmp&port=5433` (or equivalent), plus `SESSION_SECRET`, `ADMIN_SESSION_SECRET`, `ADMIN_PASSWORD=localtest`, `ADMIN_EMAIL`, `COOKIE_SECURE=false`.
- [ ] **Step 2:** Run `board_api` tests against it: `python -m pytest board_api/tests/ -v`. Expected: all pass.
- [ ] **Step 3:** Run the merged app under uvicorn locally (`uvicorn board_api.app:app --port 8000`, dev only) and curl the smoke path: `/healthz`, `GET /api/use-cases` (returns seeded open cases), `POST /api/signup`, `GET /api/admin/use-cases` (401), `POST /api/admin/login`, then `GET /api/admin/use-cases` (200). Verify each.
- [ ] **Step 4:** Optionally `vercel dev` to confirm routing (portal at `/`, admin at `/admin`). Commit `run_local.sh`.

---

### Task 6: Deploy to Vercel + wire env + smoke

- [ ] **Step 1:** Ensure Vercel CLI present (`npx vercel --version`) or use the Vercel MCP deploy tool. Link/create the Vercel project from the repo root on branch `vercel-neon-deploy`.
- [ ] **Step 2:** Set env vars in Vercel (Production + Preview): `DATABASE_URL` (Neon pooled), `SESSION_SECRET` (random), `ADMIN_SESSION_SECRET` (random), `ADMIN_PASSWORD` (chosen), `ADMIN_EMAIL`, `COOKIE_SECURE=true`. Never commit these.
- [ ] **Step 3:** Deploy (`vercel --prod` or MCP). Capture the deployment URL.
- [ ] **Step 4: Post-deploy smoke** on the live URL: `GET /healthz` → `{"ok":true}`; portal `/` loads and shows seeded cases; `/api/use-cases` returns JSON; signup works; `/admin` shows login; wrong password → 401; correct password → cockpit loads with cases + partners + responses.
- [ ] **Step 5:** Independent verification agent (different model) checks the live deployment against this plan (routes gated, data correct, no secrets leaked). Reconcile any findings.
- [ ] **Step 6:** Push branch to GitHub (PAT inline). Update `README.md` with the Vercel URL, the free-tier/non-commercial note, and the shared-password admin caveat. Commit + push.

---

## Self-Review Notes
- **Spec coverage:** DB→Neon (T1), merged backend + DATABASE_URL (T2), admin password gate replacing SSO (T2 admin_auth + T4 login UI), Vercel config avoiding Services (T3), two-SPA via `/admin/` base path (T3/T4), seeding (T1), env vars (T3/T6), tests incl. auth (T2/T5), deploy + smoke + verify (T6). All spec sections mapped.
- **Type consistency:** `board_api.db` function names match both the routes that call them and the frontends' expected JSON shapes (`response_count`, joined partner fields). `ADMIN_COOKIE_NAME`, `require_admin`, `check_password`, `make_admin_cookie`, `is_valid_admin` used consistently across `admin_auth.py`, `routes_admin.py`, and tests.
- **Placeholders:** none — full code given for DB, auth, models, app, entrypoint, config, and tests. Routing in `vercel.json` is explicitly marked as verify-and-tune during the build phase (I can observe real Vercel behavior via CLI/MCP), which is honest given Vercel's static-routing nuances.
