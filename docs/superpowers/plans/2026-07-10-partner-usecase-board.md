# Partner Use-Case Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pilot where Databricks posts use cases needing partner help, GT partners sign up by email and browse a live board, submit a structured expression of interest (EOI), and Databricks gets notified and compares responses.

**Architecture:** Two surfaces sharing one Lakebase (Postgres) source of truth. (1) A **public partner portal** — React SPA + FastAPI backend on GCP Cloud Run (Databricks Apps can't be public). (2) An **admin cockpit** — a Databricks App (React + FastAPI) behind workspace SSO. Both talk only to their own FastAPI; credentials stay server-side. Email fires on signup, new posting, and new EOI.

**Tech Stack:** React 18 + Vite + TypeScript (both UIs, Node/JS per request) · FastAPI + `psycopg` v3 + `databricks-sdk` (both backends, Python) · Lakebase Postgres · GCP Cloud Run (portal) · Databricks Apps (admin) · email via a verified sender (decided in Task 0).

## Global Constraints

- **Databricks Apps cannot be public** — the partner surface must NOT be a Databricks App. Verified: docs.databricks.com/en/dev-tools/databricks-apps/permissions.html.
- **Portal reaches Lakebase from outside Databricks** via a **service principal (M2M OAuth)**, minting a short-lived Lakebase credential with `WorkspaceClient(...).database.generate_database_credential(...)`. The SPA NEVER connects to Lakebase directly.
- **No partner password** in the pilot — signup is email + company; a signed session cookie remembers them.
- **Responses are private to Databricks** — no partner-to-partner visibility.
- **NPM/PyPI lockdown** in this environment — pin every dependency to an exact version; use the internal PyPI proxy (`pypi-proxy.dev.databricks.com`) and the internal npm registry; use Homebrew `python3.13` (system python3 LibreSSL fails proxy TLS). Verify installs in Task 0, don't assume.
- **Follow the house pattern** from `~/tritium-trip-planner` (backend/db.py dual-mode auth, Vite frontend, `app.yaml` for the Databricks App).
- **Python** preferred for all backend logic; Databricks-native features where they fit.
- **Verification** — every deliverable is exercised against the running system, then independently checked by a verification agent on a different model before it is called done (per CLAUDE.md).
- **No PII** in committed code, config, seed data, or docs — use role-based references and placeholder emails only.

---

## File Structure

```
partner-usecase-board/
├── db/
│   ├── schema.sql            # 3 tables: partners, use_cases, responses
│   └── seed.sql              # 1 sample open use case (no PII)
├── portal-backend/           # FastAPI on Cloud Run (public partner API)
│   ├── main.py               # app factory, routes wired, CORS, static SPA mount
│   ├── db.py                 # Lakebase access via M2M SP (adapted from tritium)
│   ├── sessions.py           # signed-cookie session (itsdangerous), no password
│   ├── email.py              # send welcome / new-case / new-EOI emails
│   ├── models.py             # pydantic request/response models
│   ├── routes_partners.py    # POST /api/signup, GET /api/me
│   ├── routes_board.py       # GET /api/use-cases, GET /api/use-cases/{id}
│   ├── routes_responses.py   # POST /api/use-cases/{id}/responses
│   ├── requirements.txt      # pinned
│   ├── Dockerfile            # Cloud Run container
│   └── tests/
│       ├── conftest.py       # in-memory/sqlite or test-db fixtures
│       ├── test_sessions.py
│       ├── test_routes_partners.py
│       ├── test_routes_board.py
│       └── test_routes_responses.py
├── portal-frontend/          # React SPA (partner-facing)
│   ├── package.json          # pinned deps
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx           # routes: /, /signup, /case/:id
│       ├── api.ts            # typed fetch client to portal-backend
│       ├── theme.css         # Databricks-neutral, accessible tokens
│       └── components/
│           ├── SignupForm.tsx
│           ├── BoardPage.tsx      # list of open use cases
│           ├── UseCaseCard.tsx
│           ├── CaseDetail.tsx     # single case + EOI form
│           └── EoiForm.tsx
├── admin-app/                # Databricks App (SSO) — post/manage, view EOIs
│   ├── app.yaml              # uvicorn command + Lakebase resource env
│   ├── backend/
│   │   ├── main.py
│   │   ├── db.py             # tritium-style injected-SP auth
│   │   ├── models.py
│   │   └── routes_admin.py   # CRUD use cases, list responses, list partners
│   ├── requirements.txt
│   ├── frontend/             # small React admin UI (built to backend/static)
│   │   └── src/ ...          # CaseForm, CaseList, ResponsesTable, PartnersTable
│   └── tests/
│       └── test_routes_admin.py
├── deploy/
│   ├── portal_cloudrun.sh    # build + deploy portal to Cloud Run
│   ├── admin_deploy.sh       # databricks apps deploy for admin
│   └── provision_lakebase.sh # create instance + apply schema/seed
└── docs/superpowers/
    ├── specs/2026-07-10-partner-usecase-board-design.md   # (done)
    └── plans/2026-07-10-partner-usecase-board.md          # (this file)
```

---

## Task 0: De-risking spike (BLOCKS ALL OTHER TASKS)

Prove the three unverified assumptions before building on them. No production code — a throwaway spike whose only output is GO/NO-GO evidence and the exact config values later tasks depend on. If any leg fails, stop and report to the user with the failing evidence and the fallback option; do not proceed.

**Files:**
- Create: `spike/check_lakebase_from_outside.py`, `spike/check_email.py`, `spike/npm_probe/` (throwaway), `spike/SPIKE_RESULTS.md`

**Interfaces:**
- Produces: `SPIKE_RESULTS.md` documenting (a) confirmed cross-cloud Lakebase connectivity from a non-Databricks host + the exact SP/env-var recipe, (b) which email path sends cleanly, (c) that the pinned npm+pip installs succeed under lockdown. Later tasks consume these as settled facts.

- [ ] **Step 1: Confirm the deep-test workspace + a Lakebase instance are reachable**

Run (authenticate first per the `databricks-authentication` skill):
```bash
databricks auth profiles
databricks apps list -p <deep-test-profile> | head
databricks database list-database-instances -p <deep-test-profile>
```
Expected: a usable profile and either an existing Lakebase instance or confirmation we can create one. Record instance name.

- [ ] **Step 2: Create a service principal for the portal backend (M2M OAuth)**

The portal runs OUTSIDE Databricks, so it can't rely on injected creds. Create an SP and an OAuth secret:
```bash
databricks service-principals create --display-name "partner-portal-backend" -p <profile>
# note the application_id (client_id)
databricks service-principals create-secret <sp-id> -p <profile>   # returns client_secret ONCE
```
Grant the SP: `CAN_USE` is not relevant here; it needs Lakebase access — a Postgres role + `SELECT/INSERT` on the target schema, and permission to `generate_database_credential`. Record client_id, client_secret (store as a secret, never commit).

- [ ] **Step 3: Prove Lakebase connectivity from a non-Databricks host using the SP**

Write `spike/check_lakebase_from_outside.py`:
```python
import os
import psycopg
from databricks.sdk import WorkspaceClient

# M2M: these three env vars let WorkspaceClient authenticate as the SP.
# DATABRICKS_HOST, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET
w = WorkspaceClient()  # picks up the env vars above
inst = os.environ["LAKEBASE_INSTANCE"]
host = w.database.get_database_instance(inst).read_write_dns
cred = w.database.generate_database_credential(
    request_id="spike-probe", instance_names=[inst]).token
with psycopg.connect(host=host, port=5432, dbname=os.environ["PGDATABASE"],
                     user=os.environ["DATABRICKS_CLIENT_ID"], password=cred,
                     sslmode="require") as conn, conn.cursor() as cur:
    cur.execute("SELECT 1")
    print("LAKEBASE OK:", cur.fetchone())
```
Run it with ONLY the M2M env vars set (no CLI profile), ideally from a network egress that mimics Cloud Run:
```bash
DATABRICKS_HOST=... DATABRICKS_CLIENT_ID=... DATABRICKS_CLIENT_SECRET=... \
LAKEBASE_INSTANCE=... PGDATABASE=databricks_postgres \
python3.13 spike/check_lakebase_from_outside.py
```
Expected: `LAKEBASE OK: (1,)`.
If it fails on network egress: fallback is to host the portal backend in the **one-env AWS** account (spec Section 3 alt) — STOP and surface this to the user.

- [ ] **Step 4: Confirm the email path**

Try the lowest-friction sender first. Write `spike/check_email.py` that sends one test message to a placeholder address you own. Candidates in order:
1. Gmail API via the `/gmail` skill's auth (pilot volume is tiny).
2. A transactional API (e.g. SMTP relay) if Gmail can't send from Cloud Run's egress.
Run it, confirm receipt.
Expected: test email arrives. Record the working mechanism + any env/secret it needs.
If none send from Cloud Run egress: fallback is enqueue-to-Databricks (write a `notifications` row, a Lakeflow Job emails) — STOP and surface.

- [ ] **Step 5: Prove the pinned installs work under lockdown**

```bash
# Python (portal-backend deps), using internal proxy + Homebrew python
python3.13 -m venv /tmp/spikevenv && . /tmp/spikevenv/bin/activate
pip install --index-url https://pypi-proxy.dev.databricks.com/simple \
  fastapi==0.137.1 "uvicorn[standard]==0.49.0" "psycopg[binary]==3.3.4" \
  httpx==0.28.1 databricks-sdk==0.118.0 itsdangerous==2.2.0
# Node (portal-frontend) — scaffold a throwaway vite app and install
cd spike/npm_probe && npm create vite@latest . -- --template react-ts && npm install && npm run build
```
Expected: both complete without network errors and the vite build emits `dist/`.
If npm hits the lockdown: record the internal registry that works (or set `.npmrc`) — this becomes a Global Constraint the frontend tasks rely on.

- [ ] **Step 6: Write SPIKE_RESULTS.md and commit**

Document each leg: GO/NO-GO, exact working commands, env var names, instance name, chosen email mechanism, npm registry. This file is the source of truth for later tasks.
```bash
git add spike/ && git commit -m "spike: verify cross-cloud Lakebase, email, and locked-down installs"
```

- [ ] **Step 7: Verification gate**

Spawn a verification agent (different model) to re-run the connectivity + email probes independently and confirm SPIKE_RESULTS.md matches reality. Only proceed to Task 1 on GO for all three legs.

---

## Task 1: Database schema

**Files:**
- Create: `db/schema.sql`, `db/seed.sql`, `deploy/provision_lakebase.sh`

**Interfaces:**
- Produces: three tables (`partners`, `use_cases`, `responses`) with the columns and constraints below. All later backend tasks read/write these exact names.

- [ ] **Step 1: Write `db/schema.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS partners (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email        text NOT NULL UNIQUE,
    company      text NOT NULL,
    contact_name text,
    verified     boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS use_cases (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title       text NOT NULL,
    description text NOT NULL,
    industry    text,
    region      text,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    posted_by   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz
);

CREATE TABLE IF NOT EXISTS responses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    use_case_id  uuid NOT NULL REFERENCES use_cases(id) ON DELETE CASCADE,
    partner_id   uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    approach     text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (use_case_id, partner_id)
);

CREATE INDEX IF NOT EXISTS idx_use_cases_status ON use_cases(status);
CREATE INDEX IF NOT EXISTS idx_responses_use_case ON responses(use_case_id);
```

- [ ] **Step 2: Write `db/seed.sql` (no PII)**

```sql
INSERT INTO use_cases (title, description, industry, region, status, posted_by)
VALUES (
  'Workforce Management solution — ANZ',
  'Seeking a partner with a proven Workforce Management solution deployable on Databricks for an ANZ customer. Looking for accelerators, prior implementations, and a delivery team.',
  'Cross-industry', 'ANZ', 'open', 'admin@example.com'
);
```

- [ ] **Step 3: Write `deploy/provision_lakebase.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
PROFILE="${1:?usage: provision_lakebase.sh <cli-profile> <instance-name>}"
INSTANCE="${2:?}"
# Apply schema then seed using psql via a minted credential (see spike recipe).
# Assumes PGHOST/PGUSER/PGPASSWORD exported from the spike helper.
psql "sslmode=require host=$PGHOST dbname=databricks_postgres user=$PGUSER" -f db/schema.sql
psql "sslmode=require host=$PGHOST dbname=databricks_postgres user=$PGUSER" -f db/seed.sql
echo "schema + seed applied to $INSTANCE"
```

- [ ] **Step 4: Apply to the Lakebase instance and verify**

Run the script against the spike instance. Then verify:
```bash
psql "..." -c "\dt"                         # expect 3 tables
psql "..." -c "SELECT title,status FROM use_cases;"   # expect the seeded row
psql "..." -c "INSERT INTO responses (use_case_id,partner_id,approach) VALUES ((SELECT id FROM use_cases LIMIT 1),(SELECT id FROM partners LIMIT 1),'x');" # expect FK error (no partners yet) — proves FK works
```
Expected: 3 tables; seeded row present; FK violation on the bad insert.

- [ ] **Step 5: Commit**

```bash
git add db/ deploy/provision_lakebase.sh
git commit -m "feat(db): partners/use_cases/responses schema + seed"
```

---

## Task 2: Portal backend — Lakebase access module

**Files:**
- Create: `portal-backend/db.py`, `portal-backend/requirements.txt`, `portal-backend/tests/conftest.py`, `portal-backend/tests/test_db.py`

**Interfaces:**
- Consumes: the M2M env recipe from Task 0; the schema from Task 1.
- Produces:
  - `get_conn() -> psycopg.Connection` — a connection minted via the SP.
  - `list_open_use_cases() -> list[dict]`
  - `get_use_case(uc_id: str) -> dict | None`
  - `get_or_create_partner(email: str, company: str, contact_name: str | None) -> dict`
  - `create_response(use_case_id: str, partner_id: str, approach: str) -> dict` (raises `DuplicateResponse` on unique violation)
  - `list_all_partners() -> list[dict]`

- [ ] **Step 1: Write `portal-backend/requirements.txt` (pinned; confirmed in Task 0)**

```
fastapi==0.137.1
uvicorn[standard]==0.49.0
psycopg[binary]==3.3.4
databricks-sdk==0.118.0
itsdangerous==2.2.0
pydantic==2.9.2
httpx==0.28.1
pytest==8.3.3
```

- [ ] **Step 2: Write the failing test `tests/test_db.py`**

Use a real test Postgres (or the Lakebase spike instance with a `test_` schema). Keep it minimal:
```python
from portal_backend import db

def test_get_or_create_partner_is_idempotent():
    p1 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    p2 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    assert p1["id"] == p2["id"]
    assert p1["email"] == "p@example.com"

def test_create_response_then_duplicate_raises():
    p = db.get_or_create_partner("dup@example.com", "Acme GT", None)
    uc = db.list_open_use_cases()[0]
    r = db.create_response(uc["id"], p["id"], "we'd do X")
    assert r["approach"] == "we'd do X"
    import pytest
    with pytest.raises(db.DuplicateResponse):
        db.create_response(uc["id"], p["id"], "again")
```

- [ ] **Step 3: Run test, verify it fails**

Run: `cd portal-backend && pytest tests/test_db.py -v`
Expected: FAIL (module/functions not defined).

- [ ] **Step 4: Implement `portal-backend/db.py`**

```python
"""Lakebase access for the public partner portal.

Runs OUTSIDE Databricks (Cloud Run), so it authenticates as a service
principal via M2M OAuth env vars: DATABRICKS_HOST, DATABRICKS_CLIENT_ID,
DATABRICKS_CLIENT_SECRET. WorkspaceClient() picks those up automatically.
"""
import os
import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

INSTANCE = os.environ["LAKEBASE_INSTANCE"]
DATABASE = os.environ.get("PGDATABASE", "databricks_postgres")


class DuplicateResponse(Exception):
    """Raised when a partner submits a second EOI for the same use case."""


def _conn_params():
    w = WorkspaceClient()
    host = os.environ.get("PGHOST") or w.database.get_database_instance(INSTANCE).read_write_dns
    user = os.environ.get("PGUSER") or os.environ["DATABRICKS_CLIENT_ID"]
    pwd = os.environ.get("PGPASSWORD") or w.database.generate_database_credential(
        request_id="partner-portal", instance_names=[INSTANCE]).token
    return dict(host=host, port=int(os.environ.get("PGPORT", "5432")),
                dbname=DATABASE, user=user, password=pwd, sslmode="require")


def get_conn():
    return psycopg.connect(**_conn_params(), row_factory=dict_row)


def list_open_use_cases():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id,title,description,industry,region,status,created_at "
                    "FROM use_cases WHERE status='open' ORDER BY created_at DESC")
        return cur.fetchall()


def get_use_case(uc_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id,title,description,industry,region,status,created_at "
                    "FROM use_cases WHERE id=%s", (uc_id,))
        return cur.fetchone()


def get_or_create_partner(email, company, contact_name):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("INSERT INTO partners (email,company,contact_name) VALUES (%s,%s,%s) "
                    "ON CONFLICT (email) DO UPDATE SET company=EXCLUDED.company "
                    "RETURNING id,email,company,contact_name,created_at",
                    (email, company, contact_name))
        return cur.fetchone()


def create_response(use_case_id, partner_id, approach):
    try:
        with get_conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO responses (use_case_id,partner_id,approach) "
                        "VALUES (%s,%s,%s) RETURNING id,use_case_id,partner_id,approach,created_at",
                        (use_case_id, partner_id, approach))
            return cur.fetchone()
    except psycopg.errors.UniqueViolation:
        raise DuplicateResponse(f"partner {partner_id} already responded to {use_case_id}")


def list_all_partners():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id,email,company,contact_name,created_at FROM partners ORDER BY created_at DESC")
        return cur.fetchall()
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd portal-backend && pytest tests/test_db.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add portal-backend/db.py portal-backend/requirements.txt portal-backend/tests/
git commit -m "feat(portal): Lakebase access module (M2M SP auth)"
```

---

## Task 3: Portal backend — sessions (no password)

**Files:**
- Create: `portal-backend/sessions.py`, `portal-backend/tests/test_sessions.py`

**Interfaces:**
- Produces:
  - `make_session_cookie(partner_id: str) -> str` — signed token.
  - `read_session_cookie(token: str) -> str | None` — returns partner_id or None if invalid/tampered.
  - `SESSION_COOKIE_NAME = "pub_session"`

- [ ] **Step 1: Write the failing test**

```python
from portal_backend import sessions

def test_roundtrip():
    tok = sessions.make_session_cookie("abc-123")
    assert sessions.read_session_cookie(tok) == "abc-123"

def test_tampered_returns_none():
    tok = sessions.make_session_cookie("abc-123")
    assert sessions.read_session_cookie(tok + "x") is None

def test_garbage_returns_none():
    assert sessions.read_session_cookie("not-a-token") is None
```

- [ ] **Step 2: Run test, verify fails**

Run: `pytest tests/test_sessions.py -v` → FAIL.

- [ ] **Step 3: Implement `sessions.py`**

```python
"""Signed-cookie sessions for the passwordless partner portal.

No password: identity is the partner_id we sign into a cookie after signup.
Secret comes from SESSION_SECRET env (set as a Cloud Run secret).
"""
import os
from itsdangerous import URLSafeSerializer, BadSignature

SESSION_COOKIE_NAME = "pub_session"
_serializer = URLSafeSerializer(os.environ.get("SESSION_SECRET", "dev-only-not-secret"), salt="partner-portal")


def make_session_cookie(partner_id: str) -> str:
    return _serializer.dumps({"pid": partner_id})


def read_session_cookie(token: str):
    try:
        return _serializer.loads(token)["pid"]
    except (BadSignature, KeyError, TypeError):
        return None
```

- [ ] **Step 4: Run tests, verify pass** → `pytest tests/test_sessions.py -v` PASS.

- [ ] **Step 5: Commit**

```bash
git add portal-backend/sessions.py portal-backend/tests/test_sessions.py
git commit -m "feat(portal): passwordless signed-cookie sessions"
```

---

## Task 4: Portal backend — email module

**Files:**
- Create: `common/email.py` (authored here; copied into `portal-backend/email.py` and `admin-app/backend/email.py` so both import `from . import email`), `portal-backend/tests/test_email.py`

**Interfaces:**
- Consumes: the email mechanism chosen in Task 0.
- Produces:
  - `send_welcome(to_email: str, company: str) -> None`
  - `send_new_use_case(to_emails: list[str], title: str, description: str, board_url: str) -> None`
  - `send_new_eoi(to_emails: list[str], company: str, title: str, approach: str) -> None`
  - All routed through one private `_send(to, subject, body)` so the transport is swappable. Sends are best-effort: a transport failure is logged, never raised into the request path.

- [ ] **Step 1: Write the failing test (transport mocked)**

```python
from unittest.mock import patch
from portal_backend import email

def test_welcome_calls_send_with_company():
    with patch.object(email, "_send") as m:
        email.send_welcome("p@example.com", "Acme GT")
        assert m.called
        args = m.call_args[0]
        assert args[0] == ["p@example.com"]
        assert "Acme GT" in args[2]  # body mentions company

def test_send_failure_is_swallowed():
    with patch.object(email, "_send", side_effect=RuntimeError("smtp down")):
        # must NOT raise into caller
        email.send_welcome("p@example.com", "Acme GT")
```

- [ ] **Step 2: Run test, verify fails** → FAIL.

- [ ] **Step 3: Implement `email.py`** (transport body filled from Task 0's chosen mechanism)

```python
"""Outbound notifications for the partner portal. Best-effort: never raises."""
import logging, os
log = logging.getLogger("portal.email")

FROM_ADDR = os.environ.get("EMAIL_FROM", "partner-board@example.com")

def _send(to: list[str], subject: str, body: str) -> None:
    """Transport chosen in Task 0 (Gmail API or SMTP relay). Fill in here."""
    # <<< Task 0 decides the concrete call; keep the signature stable. >>>
    raise NotImplementedError("wire Task 0 transport")

def _safe(to, subject, body):
    try:
        _send(to, subject, body)
    except Exception as e:                       # best-effort
        log.warning("email send failed to %s: %s", to, e)

def send_welcome(to_email, company):
    _safe([to_email], "You're in — Databricks Partner Use-Case Board",
          f"Thanks for joining as {company}. We'll email you when new use cases are posted.")

def send_new_use_case(to_emails, title, description, board_url):
    _safe(to_emails, f"New partner use case: {title}",
          f"{title}\n\n{description}\n\nSee the board: {board_url}")

def send_new_eoi(to_emails, company, title, approach):
    _safe(to_emails, f"New response to “{title}” from {company}",
          f"{company} expressed interest in: {title}\n\nTheir approach:\n{approach}")
```
Note: keep `_send` raising NotImplementedError until Task 0's transport is pasted in; the tests mock `_send`, so they pass regardless. Wiring the real transport is the final sub-step here, verified by an actual send.

- [ ] **Step 4: Run tests, verify pass** → PASS.

- [ ] **Step 5: Wire real transport + send one live email**

Paste the Task-0 transport into `_send`, run a one-off that calls `send_welcome` to a placeholder address you control, confirm receipt.

- [ ] **Step 6: Commit**

```bash
git add portal-backend/email.py portal-backend/tests/test_email.py
git commit -m "feat(portal): email notifications (welcome/new-case/new-EOI)"
```

---

## Task 5: Portal backend — API routes + app factory

**Files:**
- Create: `portal-backend/models.py`, `portal-backend/routes_partners.py`, `portal-backend/routes_board.py`, `portal-backend/routes_responses.py`, `portal-backend/main.py`, `portal-backend/tests/test_routes.py`

**Interfaces:**
- Consumes: `db`, `sessions`, `email` from Tasks 2–4.
- Produces the HTTP contract the frontend (Task 6) consumes:
  - `POST /api/signup` `{email, company, contact_name?}` → sets session cookie → `{id,email,company}`
  - `GET /api/me` → `{id,email,company}` or 401
  - `GET /api/use-cases` → `[{id,title,description,industry,region,created_at}]`
  - `GET /api/use-cases/{id}` → one use case or 404
  - `POST /api/use-cases/{id}/responses` `{approach}` (requires session) → 201 `{id,...}`; 409 if duplicate; 401 if no session

- [ ] **Step 1: Write `models.py`**

```python
from pydantic import BaseModel, EmailStr

class SignupIn(BaseModel):
    email: EmailStr
    company: str
    contact_name: str | None = None

class EoiIn(BaseModel):
    approach: str
```

- [ ] **Step 2: Write the failing route tests (TestClient, deps mocked)**

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from portal_backend.main import app

client = TestClient(app)

def test_signup_sets_cookie_and_returns_partner():
    with patch("portal_backend.routes_partners.db.get_or_create_partner",
               return_value={"id":"p1","email":"a@x.com","company":"Acme","contact_name":None,"created_at":"t"}), \
         patch("portal_backend.routes_partners.email.send_welcome"):
        r = client.post("/api/signup", json={"email":"a@x.com","company":"Acme"})
    assert r.status_code == 200
    assert r.json()["id"] == "p1"
    assert "pub_session" in r.cookies

def test_response_requires_session():
    r = client.post("/api/use-cases/uc1/responses", json={"approach":"x"})
    assert r.status_code == 401

def test_duplicate_response_returns_409():
    from portal_backend import db as dbmod
    with patch("portal_backend.routes_responses.db.get_use_case", return_value={"id":"uc1","title":"T"}), \
         patch("portal_backend.routes_responses.db.create_response", side_effect=dbmod.DuplicateResponse()), \
         patch("portal_backend.routes_responses.email.send_new_eoi"):
        client.cookies.set("pub_session", __import__("portal_backend.sessions", fromlist=["x"]).make_session_cookie("p1"))
        r = client.post("/api/use-cases/uc1/responses", json={"approach":"x"})
    assert r.status_code == 409
```

- [ ] **Step 3: Run tests, verify fail** → FAIL (app/routes undefined).

- [ ] **Step 4: Implement the routers**

`routes_partners.py`:
```python
from fastapi import APIRouter, Response, Request, HTTPException
from . import db, email, sessions
from .models import SignupIn

router = APIRouter()

@router.post("/api/signup")
def signup(body: SignupIn, response: Response):
    p = db.get_or_create_partner(str(body.email), body.company, body.contact_name)
    response.set_cookie(sessions.SESSION_COOKIE_NAME, sessions.make_session_cookie(p["id"]),
                        httponly=True, secure=True, samesite="lax", max_age=60*60*24*30)
    email.send_welcome(p["email"], p["company"])
    return {"id": p["id"], "email": p["email"], "company": p["company"]}

@router.get("/api/me")
def me(request: Request):
    pid = sessions.read_session_cookie(request.cookies.get(sessions.SESSION_COOKIE_NAME, ""))
    if not pid:
        raise HTTPException(401, "not signed in")
    return {"id": pid}
```

`routes_board.py`:
```python
from fastapi import APIRouter, HTTPException
from . import db
router = APIRouter()

@router.get("/api/use-cases")
def list_cases():
    return db.list_open_use_cases()

@router.get("/api/use-cases/{uc_id}")
def get_case(uc_id: str):
    uc = db.get_use_case(uc_id)
    if not uc:
        raise HTTPException(404, "not found")
    return uc
```

`routes_responses.py`:
```python
import os
from fastapi import APIRouter, Request, HTTPException
from . import db, email, sessions
from .models import EoiIn
router = APIRouter()

NOTIFY = [e for e in os.environ.get("EOI_NOTIFY_EMAILS", "").split(",") if e]

@router.post("/api/use-cases/{uc_id}/responses", status_code=201)
def respond(uc_id: str, body: EoiIn, request: Request):
    pid = sessions.read_session_cookie(request.cookies.get(sessions.SESSION_COOKIE_NAME, ""))
    if not pid:
        raise HTTPException(401, "sign up first")
    uc = db.get_use_case(uc_id)
    if not uc:
        raise HTTPException(404, "no such use case")
    try:
        r = db.create_response(uc_id, pid, body.approach)
    except db.DuplicateResponse:
        raise HTTPException(409, "you've already responded to this use case")
    # notify: poster + shared list. company looked up for the email body.
    partner = next((p for p in db.list_all_partners() if p["id"] == pid), {"company": "A partner"})
    email.send_new_eoi(NOTIFY or [uc.get("posted_by", os.environ.get("EMAIL_FROM"))],
                       partner["company"], uc["title"], body.approach)
    return r
```

`main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from . import routes_partners, routes_board, routes_responses

app = FastAPI(title="Partner Use-Case Board — Portal API")
app.add_middleware(CORSMiddleware, allow_origins=[os.environ.get("PORTAL_ORIGIN","*")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(routes_partners.router)
app.include_router(routes_board.router)
app.include_router(routes_responses.router)

# Serve the built SPA (portal-frontend/dist copied to ./static in the Docker build)
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="spa")
```

- [ ] **Step 5: Run tests, verify pass** → `pytest tests/test_routes.py -v` PASS.

- [ ] **Step 6: Run the API locally against the spike Lakebase and smoke-test**

```bash
uvicorn portal_backend.main:app --port 8000 &
curl -s localhost:8000/api/use-cases | python3 -m json.tool   # expect the seeded case
curl -si -X POST localhost:8000/api/signup -H 'content-type: application/json' \
  -d '{"email":"probe@example.com","company":"Probe GT"}'     # expect 200 + Set-Cookie
```
Expected: seeded case listed; signup returns 200 with a `pub_session` cookie.

- [ ] **Step 7: Commit**

```bash
git add portal-backend/models.py portal-backend/routes_*.py portal-backend/main.py portal-backend/tests/test_routes.py
git commit -m "feat(portal): signup/board/EOI API + app factory"
```

---

## Task 6: Portal frontend — React SPA

**Files:**
- Create all of `portal-frontend/` (Vite React-TS), key files: `src/api.ts`, `src/App.tsx`, `src/theme.css`, `src/components/{SignupForm,BoardPage,UseCaseCard,CaseDetail,EoiForm}.tsx`, `package.json`.

**Interfaces:**
- Consumes: the Task-5 HTTP contract.
- Produces: a built SPA in `portal-frontend/dist` (copied into the backend image as `static/`).

> **Design intent (per user):** neat, easy, good UX. Use the `frontend-design` skill for the visual pass. Keep it a clean 2-view flow — a board of cards and a case detail with an inline EOI form — accessible (labels, focus states, keyboard), responsive, and calm. Follow the `dataviz`/theme conventions used in the other hubs. Signup is a single low-friction step (email + company), no password field.

- [ ] **Step 1: Scaffold with pinned deps (registry from Task 0)**

```bash
cd portal-frontend
npm create vite@latest . -- --template react-ts
# pin: react 18.3.1, react-dom 18.3.1, react-router-dom 6.x, vite 5.x — edit package.json to exact versions
npm install
```

- [ ] **Step 2: Write `src/api.ts` (typed client, credentials included)**

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "";
async function j<T>(r: Response): Promise<T> { if (!r.ok) throw await r.json().catch(()=>({detail:r.statusText})); return r.json(); }
export type UseCase = { id:string; title:string; description:string; industry?:string; region?:string; created_at:string };
export const api = {
  signup: (email:string, company:string, contact_name?:string) =>
    fetch(`${BASE}/api/signup`, {method:"POST", credentials:"include",
      headers:{"content-type":"application/json"}, body:JSON.stringify({email,company,contact_name})}).then(j),
  me: () => fetch(`${BASE}/api/me`, {credentials:"include"}),
  listCases: () => fetch(`${BASE}/api/use-cases`, {credentials:"include"}).then(j<UseCase[]>),
  getCase: (id:string) => fetch(`${BASE}/api/use-cases/${id}`, {credentials:"include"}).then(j<UseCase>),
  respond: (id:string, approach:string) =>
    fetch(`${BASE}/api/use-cases/${id}/responses`, {method:"POST", credentials:"include",
      headers:{"content-type":"application/json"}, body:JSON.stringify({approach})}),
};
```

- [ ] **Step 3: Build the views** (`App.tsx` routes `/` board, `/case/:id` detail; components render cards + forms). Full component code written during implementation following the frontend-design skill; each shows loading/empty/error states and disables the submit button while pending.

- [ ] **Step 4: Build the SPA and eyeball it**

```bash
npm run build            # emits dist/
npm run dev              # local check against the running backend
```
Use the `web-devloop-tester` agent to drive the flow in a browser: signup → see the seeded case → open it → submit an EOI → see the confirmation; and the duplicate-EOI 409 shows a friendly message. Check the console is clean and the layout is responsive.

- [ ] **Step 5: Commit**

```bash
git add portal-frontend/
git commit -m "feat(portal): React SPA — board, signup, EOI (neat UX)"
```

---

## Task 7: Portal deployment to Cloud Run

**Files:**
- Create: `portal-backend/Dockerfile`, `deploy/portal_cloudrun.sh`

**Interfaces:**
- Consumes: everything above; the Task-0 GCP project + SP secrets.
- Produces: a public HTTPS URL serving the SPA + API.

- [ ] **Step 1: Write `Dockerfile` (multi-stage: build SPA, then serve from FastAPI)**

```dockerfile
# --- build SPA ---
FROM node:20-slim AS web
WORKDIR /web
COPY portal-frontend/package*.json ./
RUN npm ci
COPY portal-frontend/ ./
RUN npm run build
# --- backend ---
FROM python:3.13-slim
WORKDIR /app
COPY portal-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY portal-backend/ ./portal_backend/
COPY --from=web /web/dist ./static
ENV PORT=8080
CMD ["sh","-c","uvicorn portal_backend.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Write `deploy/portal_cloudrun.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
PROJECT="${1:?gcp project}"; REGION="${2:-us-central1}"; SVC="partner-portal"
gcloud builds submit --project "$PROJECT" --tag "gcr.io/$PROJECT/$SVC" -f portal-backend/Dockerfile .
gcloud run deploy "$SVC" --project "$PROJECT" --region "$REGION" --image "gcr.io/$PROJECT/$SVC" \
  --allow-unauthenticated --port 8080 \
  --set-secrets "DATABRICKS_CLIENT_SECRET=portal-sp-secret:latest,SESSION_SECRET=portal-session:latest" \
  --set-env-vars "DATABRICKS_HOST=...,DATABRICKS_CLIENT_ID=...,LAKEBASE_INSTANCE=...,PGDATABASE=databricks_postgres,EOI_NOTIFY_EMAILS=...,EMAIL_FROM=...,PORTAL_ORIGIN=..."
```

- [ ] **Step 3: Deploy and verify the public URL**

Run the script. Then from a browser with NO Databricks login, hit the Cloud Run URL: the board loads and lists the seeded case; signup works; EOI submits. This is the moment that proves "public, no Databricks account" works.
Expected: full partner flow works unauthenticated against live Lakebase.

- [ ] **Step 4: Commit**

```bash
git add portal-backend/Dockerfile deploy/portal_cloudrun.sh
git commit -m "feat(portal): Cloud Run deployment (public)"
```

---

## Task 8: Admin app (Databricks App, SSO)

**Files:**
- Create all of `admin-app/`: `app.yaml`, `backend/{main,db,models,routes_admin}.py`, `requirements.txt`, `frontend/` (small React), `tests/test_routes_admin.py`.

**Interfaces:**
- Consumes: same Lakebase (via the tritium-style injected-SP auth — this side IS a Databricks App).
- Produces admin HTTP contract:
  - `POST /api/admin/use-cases` `{title,description,industry?,region?}` → creates a case (posted_by = SSO user) → emails all partners → `{id,...}`
  - `PATCH /api/admin/use-cases/{id}` `{status}` → open/close
  - `GET /api/admin/use-cases` → all cases (any status)
  - `GET /api/admin/use-cases/{id}/responses` → responses joined to partner company/email
  - `GET /api/admin/partners` → registered partners

- [ ] **Step 1: `app.yaml`** (mirror tritium; attach the Lakebase Database resource so PGHOST/PGUSER are injected)

```yaml
command: ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]
env:
  - name: LAKEBASE_INSTANCE
    value: "<instance-from-task0>"
  - name: PGDATABASE
    value: "databricks_postgres"
  - name: EMAIL_FROM
    value: "partner-board@example.com"
```

- [ ] **Step 2: `backend/db.py`** — copy the tritium dual-mode helper; add: `create_use_case`, `set_status`, `list_all_use_cases`, `list_responses_for(uc_id)` (JOIN partners), `list_partners`. The `posted_by` value comes from the SSO-forwarded user header (`X-Forwarded-Email` / SDK `current_user`).

- [ ] **Step 3: Write failing route tests** (TestClient, db mocked) for create→emails-partners, patch status, and responses-join shape. Run → FAIL.

- [ ] **Step 4: Implement `routes_admin.py` + `main.py`.** On create, call `email.send_new_use_case` to every partner from `list_partners()`. **DRY note:** the email module is authored once in Task 4 as `common/email.py` (not `portal-backend/email.py`), and both `portal-backend` and `admin-app/backend` import it via a copy in each package (the lockdown makes a shared installable package heavier than it's worth for the pilot). Task 4's paths below reflect this. Run tests → PASS.

- [ ] **Step 5: Build the small admin React UI** — a form to post a case, a table of cases with an open/close toggle, and per-case a responses table (company · contact · approach · date) plus a partners table. Same neat/accessible bar as the portal.

- [ ] **Step 6: Deploy to the target Databricks workspace and verify SSO gate**

```bash
databricks apps deploy partner-admin -p <profile> --source-code-path .
```
Verify: reachable only when logged into the workspace; posting a case writes to Lakebase and the portal board (Task 7) shows it; partners receive the new-case email.

- [ ] **Step 7: Commit**

```bash
git add admin-app/ common/email.py
git commit -m "feat(admin): Databricks App — post/manage cases, view responses (SSO)"
```

---

## Task 9: End-to-end verification

**Files:** Create `docs/VERIFICATION.md`.

- [ ] **Step 1: Run the full loop live, once**

Admin (SSO) posts a new use case → confirm the seeded + new cases show on the public portal → a partner (no Databricks login, via the Cloud Run URL) signs up (welcome email arrives) → opens the new case → submits an EOI → the admin responses table shows it AND the notify list gets the EOI email → a second EOI from the same partner is rejected with a friendly 409.

- [ ] **Step 2: Record evidence in `docs/VERIFICATION.md`** — each step, what was observed, screenshots/curl output, the Lakebase rows created.

- [ ] **Step 3: Independent verification agent (different model)**

Dispatch a verification agent to independently re-drive the public flow and inspect the Lakebase rows, confirming behavior matches this plan and the spec. Reconcile any discrepancy before declaring done.

- [ ] **Step 4: Commit**

```bash
git add docs/VERIFICATION.md
git commit -m "docs: end-to-end verification evidence"
```

---

## Self-Review (against the spec)

**Spec coverage:**
- Two surfaces / one Lakebase → Tasks 2–8. ✓
- Apps-can't-be-public constraint → portal is Cloud Run (Task 7), admin is the only Databricks App (Task 8). ✓
- 3-table data model → Task 1 matches spec columns/constraints exactly. ✓
- Passwordless partner signup + session → Task 3, Task 5 `/api/signup`. ✓
- Admin SSO → Task 8 (Databricks App). ✓
- 3 email triggers (signup, new case, new EOI) → Tasks 4, 5 (signup+EOI), 8 (new case). ✓
- Responses private to Databricks → no partner-facing response endpoints; only admin lists them. ✓
- Neat UX / Node+JS UI → Tasks 6 & 8 React, frontend-design skill. ✓
- Verification on different model → Task 0 Step 7, Task 9 Step 3, plus per-task. ✓
- Known risks (cross-cloud, npm lockdown, email) → Task 0 spike gates all three. ✓

**Placeholder scan:** The only intentional deferral is `email._send`'s transport body, which is explicitly resolved in Task 0 and wired in Task 4 Step 5 with a live send — not a silent TODO. Cloud Run env values (`DATABRICKS_HOST=...`) are deployment secrets filled at deploy time, not code placeholders.

**Type consistency:** `DuplicateResponse` defined in Task 2, caught in Task 5. Session functions `make_session_cookie`/`read_session_cookie`/`SESSION_COOKIE_NAME` consistent across Tasks 3 and 5. `UseCase` shape in `api.ts` (Task 6) matches `/api/use-cases` fields (Task 5). Email function names consistent across Tasks 4, 5, 8.

**Gaps:** GT-partner gating is intentionally OUT (spec) — noted, not a gap. Email module is shared between both apps via `common/email.py` (Task 8 Step 4) to stay DRY.
