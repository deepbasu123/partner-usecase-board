# Clerk Partner Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the portal's passwordless signed-cookie sign-in with Clerk email-code auth: the SPA holds a Clerk session, the FastAPI backend verifies Clerk JWTs against the JWKS, and a one-field onboarding step captures `company`.

**Architecture:** Clerk owns identity + email verification. The React SPA wraps in `<ClerkProvider>` and attaches the Clerk session JWT as `Authorization: Bearer` on every API call. A new `board_api/clerk_auth.py` verifies that JWT networklessly against Clerk's JWKS (PyJWT + cached keys) and exposes a `require_identity` dependency that replaces the cookie check in `routes_public.py`. Partner profiles stay in Neon, keyed on email, with a new `clerk_user_id` column so seeded partners link (not duplicate) on first sign-in. Admin's shared-password auth is untouched.

**Tech Stack:** Clerk (`@clerk/react` frontend, JWKS backend verify), `pyjwt[crypto]` (Python), FastAPI, Vite/React 18 + react-router 6, pytest + `unittest.mock`, Neon Postgres.

## Global Constraints

- **BLOCKED until Clerk keys exist.** Nothing here can be wired or tested until the user provisions a Clerk application and supplies: publishable key, secret key, JWKS/issuer URL. See Prerequisites.
- **Clerk session token MUST include `email`.** Clerk's default session JWT carries `sub` (user id) but not email. Email is our join key to link the 10 seeded partners. The Clerk app must be configured (session-token customization) to include `email` (and it's fine to also rely on `sub`). This is a setup prerequisite, not code.
- **Sign-in strategy:** email code (passwordless) only. No password, no social, no Clerk Organizations.
- **Networkless verify:** verify the JWT signature against Clerk's JWKS with cached keys; no per-request call to Clerk. On a cache miss / unknown-kid, refresh the JWKS once.
- **Package name:** frontend SDK is `@clerk/react` (Clerk Core 3, Mar 2026; the pre-Core-3 name was `@clerk/clerk-react` — same exports). Confirm the exact latest name at install time on the Vercel build.
- **No new backend dep beyond PyJWT:** `cryptography` is already in the venv; add only `pyjwt[crypto]` to `requirements.txt`. Local installs go through the PyPI proxy (npm/PyPI direct access is locked down on this machine).
- **Admin auth untouched:** do not modify `board_api/admin_auth.py`, its cookie, or `/api/admin/*`.
- **Publishable key is public; secret key is server-only.** Never ship the secret key to the client; never log either.
- **Real sign-in UI is manual-test-only.** The Clerk email-code flow can't be curl'd; it's verified in a browser on a Vercel preview after keys are set. Automated backend tests use a locally-minted test JWT.
- **Commit style:** `type(scope): summary`, matching git history.
- **Test invocation:** `. .venv/bin/activate && python -m pytest board_api/tests/ -v`. (`run_tests.sh` is stale — points at old `portal_backend/` — don't use it for `board_api`.)

---

## Prerequisites (user + setup, before Task 1)

- [ ] **P1: User creates the Clerk application** with email-code sign-in enabled, and shares: `CLERK_PUBLISHABLE_KEY` (`pk_...`), `CLERK_SECRET_KEY` (`sk_...`), and the JWKS URL (`https://<frontend-api>/.well-known/jwks.json`) or issuer.
- [ ] **P2: User customizes the Clerk session token to include email** (Clerk dashboard → Sessions → customize session token → add `"email": "{{user.primary_email_address}}"`). Required so the backend can read email from the verified JWT.
- [ ] **P3: Install PyJWT locally for TDD** via the PyPI proxy (see `reference_pypi_proxy`): `cryptography` is already present, so only the PyJWT wheel is needed. Confirm with `. .venv/bin/activate && python -c "import jwt; print(jwt.__version__)"`.

---

### Task 1: `clerk_auth.py` — JWKS verification + `require_identity`

**Files:**
- Create: `board_api/clerk_auth.py`
- Test: `board_api/tests/test_clerk_auth.py`

**Interfaces:**
- Consumes: env `CLERK_JWKS_URL`, optional `CLERK_ISSUER`.
- Produces:
  - `verify_token(token: str) -> dict` — returns verified claims or raises.
  - `require_identity(request: Request) -> dict` — FastAPI dependency returning `{"email": str, "clerk_user_id": str}`; raises `HTTPException(401)` on any failure.
  - `_signing_key(token)` — the seam tests patch to inject a test public key (so no network + no real Clerk needed).

- [ ] **Step 1: Write the failing tests**

Create `board_api/tests/test_clerk_auth.py`. It mints a real RS256 JWT with a test key and injects the matching public key via the `_signing_key` seam:

```python
"""clerk_auth tests: mint a local RS256 JWT, inject the public key as the
'signing key', and assert verify_token + require_identity behave. No network,
no real Clerk."""
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from board_api import clerk_auth

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(claims):
    return jwt.encode(claims, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _inject_key(monkeypatch):
    # verify_token calls _signing_key(token) to get the verifying key.
    monkeypatch.setattr(clerk_auth, "_signing_key", lambda token: _KEY.public_key())


def _request_with(auth_header):
    scope = {"type": "http", "headers": []}
    if auth_header is not None:
        scope["headers"] = [(b"authorization", auth_header.encode())]
    return Request(scope)


def test_verify_token_returns_claims():
    tok = _make_token({"sub": "user_123", "email": "a@x.com"})
    claims = clerk_auth.verify_token(tok)
    assert claims["sub"] == "user_123"
    assert claims["email"] == "a@x.com"


def test_require_identity_returns_email_and_id():
    tok = _make_token({"sub": "user_123", "email": "a@x.com"})
    ident = clerk_auth.require_identity(_request_with(f"Bearer {tok}"))
    assert ident == {"email": "a@x.com", "clerk_user_id": "user_123"}


def test_require_identity_401_without_header():
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with(None))
    assert e.value.status_code == 401


def test_require_identity_401_on_garbage_token():
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with("Bearer not.a.jwt"))
    assert e.value.status_code == 401


def test_require_identity_401_when_email_claim_missing():
    tok = _make_token({"sub": "user_123"})  # no email → cannot link partner
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with(f"Bearer {tok}"))
    assert e.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_clerk_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: board_api.clerk_auth`.

- [ ] **Step 3: Implement `clerk_auth.py`**

```python
"""Clerk session-JWT verification for the partner portal.

Networkless: the JWT signature is checked against Clerk's JWKS (public keys),
which PyJWKClient fetches once and caches. No per-request call to Clerk. Replaces
the old signed-cookie session for partner-gated routes. Admin auth is separate.
"""
import os

import jwt
from jwt import PyJWKClient
from fastapi import Request, HTTPException

_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
_ISSUER = os.environ.get("CLERK_ISSUER") or None

_jwks_client = None


def _client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not _JWKS_URL:
            raise RuntimeError("CLERK_JWKS_URL not set")
        _jwks_client = PyJWKClient(_JWKS_URL)  # caches keys internally
    return _jwks_client


def _signing_key(token: str):
    """Resolve the verifying key for this token from the JWKS. Patched in tests."""
    return _client().get_signing_key_from_jwt(token).key


def verify_token(token: str) -> dict:
    """Return verified claims, or raise (bad signature / expired / wrong issuer)."""
    key = _signing_key(token)
    return jwt.decode(
        token, key, algorithms=["RS256"],
        issuer=_ISSUER, options={"verify_aud": False},
    )


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return auth[len("Bearer "):]


def require_identity(request: Request) -> dict:
    """FastAPI dependency: verified {email, clerk_user_id} or 401.

    Email must be present (Clerk session token is configured to include it); it's
    the key we link partner profiles on.
    """
    token = _bearer(request)
    try:
        claims = verify_token(token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "invalid token")
    email = claims.get("email")
    sub = claims.get("sub")
    if not email or not sub:
        raise HTTPException(401, "token missing required claims")
    return {"email": email, "clerk_user_id": sub}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_clerk_auth.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Add PyJWT to requirements and commit**

Add to `requirements.txt`:

```
pyjwt[crypto]==2.10.1
```

```bash
git add board_api/clerk_auth.py board_api/tests/test_clerk_auth.py requirements.txt
git commit -m "feat(auth): Clerk JWT verification via JWKS + require_identity"
```

---

### Task 2: DB — `clerk_user_id` column + link-or-create helper

**Files:**
- Modify: `db/schema.sql:7-14` (partners table — add column)
- Create: `db/migrations/2026-07-15-add-clerk-user-id.sql`
- Modify: `board_api/db.py` (add `link_or_create_partner`)
- Test: `board_api/tests/test_clerk_auth.py` is unit; DB helper is covered by the onboarding route test in Task 3 (mocked). No live-DB test added here (matches existing mocked-route pattern).

**Interfaces:**
- Consumes: nothing.
- Produces: `db.link_or_create_partner(email: str, clerk_user_id: str, company: str) -> dict` — if a partner row with this email exists, set its `clerk_user_id` (and company if it was empty) and return it; else insert a new row. Returns `{id, email, company, contact_name, created_at}`.

- [ ] **Step 1: Add the migration SQL**

Create `db/migrations/2026-07-15-add-clerk-user-id.sql`:

```sql
-- Link Clerk identities to partner profiles. Nullable so existing rows are
-- valid; stamped on first Clerk sign-in (linked by email).
ALTER TABLE partners ADD COLUMN IF NOT EXISTS clerk_user_id text UNIQUE;
```

And add the column to `db/schema.sql` inside the `partners` table (after `contact_name`):

```sql
    clerk_user_id text UNIQUE,
```

- [ ] **Step 2: Write the failing test for the helper**

Add to `board_api/tests/test_public.py` (it already mocks `db`), a test that the onboarding route calls the new helper — but the helper itself is thin SQL, so assert via the route in Task 3. Here, just add a focused unit that the function exists and builds the right call. Create `board_api/tests/test_db_link.py`:

```python
"""Unit for link_or_create_partner's contract via a fake cursor (no real PG)."""
from unittest.mock import MagicMock, patch
from board_api import db


def test_link_or_create_partner_upserts_by_email():
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"id": "p1", "email": "a@x.com",
                                      "company": "Acme", "contact_name": None,
                                      "created_at": "t"}
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_conn.__enter__.return_value = fake_conn
    with patch("board_api.db.get_conn", return_value=fake_conn):
        row = db.link_or_create_partner("a@x.com", "user_123", "Acme")
    assert row["id"] == "p1"
    # the SQL must reference clerk_user_id and use ON CONFLICT (email)
    sql = fake_cur.execute.call_args[0][0]
    assert "clerk_user_id" in sql
    assert "ON CONFLICT (email)" in sql
```

- [ ] **Step 3: Run test to verify it fails**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_db_link.py -v`
Expected: FAIL — `AttributeError: module 'board_api.db' has no attribute 'link_or_create_partner'`.

- [ ] **Step 4: Implement the helper in `db.py`**

Add to `board_api/db.py` (near `get_or_create_partner`):

```python
def link_or_create_partner(email, clerk_user_id, company):
    """Link a Clerk identity to a partner by email, or create the row.

    On email conflict (e.g. a seeded partner signing in for the first time), keep
    the existing id/responses and stamp clerk_user_id; fill company only if the
    existing value is blank so we never clobber a real one with an onboarding entry.
    """
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO partners (email, company, clerk_user_id) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET "
            "  clerk_user_id = EXCLUDED.clerk_user_id, "
            "  company = CASE WHEN partners.company IS NULL OR partners.company = '' "
            "                 THEN EXCLUDED.company ELSE partners.company END "
            "RETURNING id, email, company, contact_name, created_at",
            (email, company, clerk_user_id))
        return cur.fetchone()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_db_link.py -v`
Expected: PASS.

- [ ] **Step 6: Apply the migration to Neon**

Run the migration against the live Neon DB (project `ancient-wave-37020806`) using the Neon MCP `run_sql` or psql. The `ADD COLUMN IF NOT EXISTS` is idempotent and non-destructive.

- [ ] **Step 7: Commit**

```bash
git add db/schema.sql db/migrations/2026-07-15-add-clerk-user-id.sql board_api/db.py board_api/tests/test_db_link.py
git commit -m "feat(db): clerk_user_id column + link_or_create_partner (link seeded by email)"
```

---

### Task 3: Rework `routes_public.py` — Clerk gate, `/api/me`, `/api/onboarding`

**Files:**
- Modify: `board_api/routes_public.py` (signup→onboarding, me, EOI gate)
- Modify: `board_api/models.py` (add `OnboardingIn`)
- Modify: `board_api/tests/test_public.py` (cookie → Bearer)
- Modify: `board_api/app.py` only if router wiring changes (it doesn't — same router)

**Interfaces:**
- Consumes: `clerk_auth.require_identity` (Task 1), `db.link_or_create_partner` + `db.get_partner`/a new `db.get_partner_by_email` (Task 2).
- Produces:
  - `GET /api/me` → `200 {id,email,company}` if profile exists for the verified email, else `200 {onboarding_required: true}`.
  - `POST /api/onboarding {company}` → `201 {id,email,company}`; links/creates the partner.
  - `POST /api/use-cases/{id}/responses` → gated on `require_identity`; resolve the partner by verified email; behaviour otherwise unchanged (201 / 409 dup / 409 closed / 404 missing).
  - `OnboardingIn(BaseModel)` with a non-blank `company` validator.

- [ ] **Step 1: Add `OnboardingIn` and a by-email lookup**

In `board_api/models.py`, add:

```python
class OnboardingIn(BaseModel):
    company: str

    @field_validator("company")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("company is required")
        return v.strip()
```

In `board_api/db.py`, add:

```python
def get_partner_by_email(email):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners WHERE email = %s", (email,))
        return cur.fetchone()
```

- [ ] **Step 2: Rewrite the failing tests (cookie → Bearer)**

Replace the session-cookie helpers/tests in `board_api/tests/test_public.py`. Key changes: drop `from board_api import sessions`; override the `require_identity` dependency instead of setting a cookie. Full new auth-related test section:

```python
from board_api.app import app
from board_api import clerk_auth

def _auth(email="a@x.com", uid="user_1"):
    """Override require_identity so routes see a verified partner."""
    app.dependency_overrides[clerk_auth.require_identity] = \
        lambda: {"email": email, "clerk_user_id": uid}

def _noauth():
    app.dependency_overrides.pop(clerk_auth.require_identity, None)


def test_me_onboarding_required_when_no_profile(client):
    _auth("new@x.com")
    with patch("board_api.routes_public.db.get_partner_by_email", return_value=None):
        r = client.get("/api/me")
    _noauth()
    assert r.status_code == 200
    assert r.json() == {"onboarding_required": True}


def test_me_returns_profile_when_exists(client):
    _auth("z@x.com")
    with patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p9", "email": "z@x.com", "company": "Zeta GT",
                             "contact_name": None, "created_at": "t"}):
        r = client.get("/api/me")
    _noauth()
    assert r.status_code == 200
    assert r.json()["company"] == "Zeta GT"


def test_me_401_without_token(client):
    r = client.get("/api/me")   # no dependency override, no header
    assert r.status_code == 401


def test_onboarding_creates_profile(client):
    _auth("new@x.com", "user_9")
    with patch("board_api.routes_public.db.link_or_create_partner",
               return_value={"id": "p2", "email": "new@x.com", "company": "Acme GT",
                             "contact_name": None, "created_at": "t"}), \
         patch("board_api.routes_public.email.send_welcome"):
        r = client.post("/api/onboarding", json={"company": "Acme GT"})
    _noauth()
    assert r.status_code == 201
    assert r.json()["company"] == "Acme GT"


def test_onboarding_rejects_blank_company(client):
    _auth("new@x.com")
    r = client.post("/api/onboarding", json={"company": "  "})
    _noauth()
    assert r.status_code == 422


def test_response_requires_token(client):
    r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 401


def test_response_created_201(client):
    _auth("a@x.com", "user_1")
    with patch("board_api.routes_public.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "open",
                             "posted_by": "admin@example.com"}), \
         patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT"}), \
         patch("board_api.routes_public.db.create_response",
               return_value={"id": "r1", "use_case_id": "uc1", "partner_id": "p1",
                             "approach": "x", "created_at": "t"}), \
         patch("board_api.routes_public.email.send_new_eoi"):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 201
```

Delete the old cookie-based tests they replace: `test_signup_sets_cookie_and_returns_partner`, `test_me_401_without_session`, `test_me_returns_partner_with_session`, `test_me_401_when_partner_gone`, `test_response_requires_session`, and update `test_duplicate_response_returns_409` / `test_response_404_when_case_missing` / `test_response_rejected_on_closed_case` to use `_auth()` + `db.get_partner_by_email` instead of `client.cookies.set`/`sessions`. Keep the no-auth board tests (`test_list_cases`, `test_get_case_404`, `test_get_case_hides_closed_from_public`, `test_board_endpoints_need_no_session`, `test_signup_rejects_bad_email` → move to onboarding validation) as-is where they don't touch auth.

- [ ] **Step 3: Run tests to verify they fail**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_public.py -v`
Expected: FAIL — routes still reference `sessions`/`/api/signup`; `db.get_partner_by_email`/`link_or_create_partner` not wired into routes; `/api/onboarding` 404.

- [ ] **Step 4: Rewrite `routes_public.py`**

Replace the signup/me/EOI section. Remove the `sessions` import and cookie logic; gate on `require_identity`:

```python
import os
from fastapi import APIRouter, Request, HTTPException, Depends

from . import db, email
from .clerk_auth import require_identity
from .models import OnboardingIn, EoiIn

router = APIRouter()

_NOTIFY = [e.strip() for e in os.environ.get("EOI_NOTIFY_EMAILS", "").split(",") if e.strip()]


@router.get("/api/me")
def me(identity: dict = Depends(require_identity)):
    partner = db.get_partner_by_email(identity["email"])
    if not partner:
        return {"onboarding_required": True}
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


@router.post("/api/onboarding", status_code=201)
def onboarding(body: OnboardingIn, identity: dict = Depends(require_identity)):
    partner = db.link_or_create_partner(identity["email"], identity["clerk_user_id"], body.company)
    email.send_welcome(partner["email"], partner["company"])
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


@router.get("/api/use-cases")
def list_cases():
    return db.list_open_use_cases()


@router.get("/api/use-cases/{uc_id}")
def get_case(uc_id: str):
    uc = db.get_use_case(uc_id)
    if not uc or uc.get("status") != "open":
        raise HTTPException(404, "use case not found")
    return uc


@router.post("/api/use-cases/{uc_id}/responses", status_code=201)
def respond(uc_id: str, body: EoiIn, identity: dict = Depends(require_identity)):
    partner = db.get_partner_by_email(identity["email"])
    if not partner:
        raise HTTPException(401, "complete onboarding first")

    uc = db.get_use_case(uc_id)
    if not uc:
        raise HTTPException(404, "no such use case")
    if uc.get("status") != "open":
        raise HTTPException(409, "this use case is closed")

    try:
        response_row = db.create_response(uc_id, partner["id"], body.approach)
    except db.DuplicateResponse:
        raise HTTPException(409, "you've already responded to this use case")

    recipients = list(_NOTIFY)
    poster = uc.get("posted_by") or os.environ.get("EMAIL_FROM")
    if poster and poster not in recipients:
        recipients.append(poster)
    if recipients:
        email.send_new_eoi(recipients, partner["company"], uc["title"], body.approach)
    return response_row
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_public.py -v`
Expected: PASS. Then run the whole suite: `python -m pytest board_api/tests/ -v` — expect all green (Task 1 + 2 + reworked public + admin + email tests).

- [ ] **Step 6: Retire the portal cookie module**

`board_api/sessions.py` is now unused by routes. Confirm nothing imports it: `grep -rn "import sessions\|from . import sessions\|board_api.sessions" board_api/`. Expected: only its own file (and maybe deleted tests). Delete `board_api/sessions.py`. Leave `SESSION_SECRET` env var alone for now (harmless).

- [ ] **Step 7: Commit**

```bash
git add board_api/routes_public.py board_api/models.py board_api/db.py board_api/tests/test_public.py
git rm board_api/sessions.py
git commit -m "feat(auth): gate portal on Clerk identity; add /api/onboarding, retire cookie"
```

---

### Task 4: Frontend — ClerkProvider + Bearer-token API client

**Files:**
- Modify: `portal-frontend/package.json` (add `@clerk/react`)
- Modify: `portal-frontend/src/main.tsx` (wrap in `<ClerkProvider>`)
- Modify: `portal-frontend/src/api.ts` (attach Bearer token)
- Modify: `.env.example` (VITE var)

**Interfaces:**
- Consumes: `VITE_CLERK_PUBLISHABLE_KEY` at build time; a `getToken()` provided by Clerk.
- Produces: every `api.*` call sends `Authorization: Bearer <clerk-jwt>`; `api.onboarding(company)` and `api.me()` typed for the new backend contract.

- [ ] **Step 1: Add the dependency**

In `portal-frontend/package.json` dependencies, add (confirm latest at install):

```json
    "@clerk/react": "^2.0.0",
```

- [ ] **Step 2: Wrap the app in `<ClerkProvider>`**

Rewrite `portal-frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ClerkProvider } from "@clerk/react";
import App from "./App";
import "./theme.css";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;
if (!PUBLISHABLE_KEY) throw new Error("VITE_CLERK_PUBLISHABLE_KEY is not set");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ClerkProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 3: Make the API client send the Clerk token**

The token is per-request and comes from Clerk's `useAuth().getToken()`, so `api.ts` must accept a token getter rather than reading a cookie. Change the exported `api` to a factory and update callers via a hook. Rewrite `portal-frontend/src/api.ts`:

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "";

export type UseCase = {
  id: string; title: string; description: string;
  industry?: string | null; region?: string | null;
  status: string; created_at: string;
};
export type Partner = { id: string; email: string; company: string };
export type Me = Partner | { onboarding_required: true };

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(r.status, (detail as any).detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

// getToken comes from Clerk's useAuth(); null token → no auth header (public reads).
export function makeApi(getToken: () => Promise<string | null>) {
  const auth = async (): Promise<HeadersInit> => {
    const t = await getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  };
  return {
    me: async (): Promise<Me | null> => {
      const r = await fetch(`${BASE}/api/me`, { headers: await auth() });
      return r.ok ? ((await r.json()) as Me) : null;
    },
    onboarding: async (company: string) =>
      fetch(`${BASE}/api/onboarding`, {
        method: "POST",
        headers: { "content-type": "application/json", ...(await auth()) },
        body: JSON.stringify({ company }),
      }).then(json<Partner>),
    listCases: () => fetch(`${BASE}/api/use-cases`).then(json<UseCase[]>),
    getCase: (id: string) => fetch(`${BASE}/api/use-cases/${id}`).then(json<UseCase>),
    respond: async (id: string, approach: string) =>
      fetch(`${BASE}/api/use-cases/${id}/responses`, {
        method: "POST",
        headers: { "content-type": "application/json", ...(await auth()) },
        body: JSON.stringify({ approach }),
      }).then(json<{ id: string }>),
  };
}
export type Api = ReturnType<typeof makeApi>;
export { ApiError };
```

- [ ] **Step 4: Document the VITE var**

Append to `.env.example`:

```
# Clerk (partner auth) — publishable key is public; set in Vercel for the build.
VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxxx
```

- [ ] **Step 5: Commit**

```bash
git add portal-frontend/package.json portal-frontend/src/main.tsx portal-frontend/src/api.ts .env.example
git commit -m "feat(portal): ClerkProvider + Bearer-token API client"
```

> No unit test here — the frontend has no test harness (verified: `portal-frontend` has only build scripts). This task is verified by the build (Task 7) and manual sign-in (Task 8).

---

### Task 5: Frontend — SignIn page replaces SignupForm

**Files:**
- Create: `portal-frontend/src/components/SignInPage.tsx`
- Delete: `portal-frontend/src/components/SignupForm.tsx`
- Modify: `portal-frontend/src/App.tsx` (routes + Clerk session state)
- Modify: `portal-frontend/src/components/Chrome.tsx` (the "Join as a partner" link → sign-in; sign-out control)

**Interfaces:**
- Consumes: Clerk `<SignIn/>`, `useAuth`, `useUser`; `makeApi` from Task 4.
- Produces: `/signin` route rendering Clerk's email-code UI; `App` derives `partner`/`onboarding` state from Clerk + `/api/me`.

- [ ] **Step 1: Create `SignInPage.tsx`**

```tsx
import { SignIn } from "@clerk/react";
import { TopBar } from "./Chrome";

export function SignInPage() {
  return (
    <>
      <TopBar title="Sign in" sub="We'll email you a code — no password" partner={null} />
      <main className="main">
        <div className="main-wrap" style={{ maxWidth: 460 }}>
          <SignIn routing="path" path="/signin" signUpUrl="/signin" />
        </div>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Rewrite `App.tsx` to use Clerk session + onboarding gate**

```tsx
import { useEffect, useState, useCallback } from "react";
import { Routes, Route } from "react-router-dom";
import { useAuth, useUser } from "@clerk/react";
import { makeApi, type Partner } from "./api";
import { Rail } from "./components/Chrome";
import { BoardPage } from "./components/BoardPage";
import { SignInPage } from "./components/SignInPage";
import { Onboarding } from "./components/Onboarding";
import { CaseDetail } from "./components/CaseDetail";

export default function App() {
  const { getToken, isSignedIn } = useAuth();
  const { isLoaded } = useUser();
  const [partner, setPartner] = useState<Partner | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  const api = useCallback(() => makeApi(() => getToken()), [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) { setPartner(null); return; }
    api().me().then((m) => {
      if (m && "onboarding_required" in m) { setNeedsOnboarding(true); setPartner(null); }
      else if (m) { setPartner(m); setNeedsOnboarding(false); }
    });
  }, [isLoaded, isSignedIn, api]);

  return (
    <div className="app">
      <Rail partner={partner} />
      <div className="content">
        <Routes>
          <Route path="/" element={<BoardPage partner={partner} api={api} />} />
          <Route path="/signin/*" element={<SignInPage />} />
          <Route path="/onboarding" element={
            <Onboarding api={api} onDone={(p) => { setPartner(p); setNeedsOnboarding(false); }} />
          } />
          <Route path="/case/:id" element={<CaseDetail partner={partner} api={api} />} />
        </Routes>
      </div>
      {needsOnboarding && window.location.pathname !== "/onboarding" &&
        (window.location.href = "/onboarding")}
    </div>
  );
}
```

> Note for implementer: `BoardPage`, `CaseDetail`, and `Chrome` currently take `partner` and call the old singleton `api`. Thread the `api` factory (a `() => Api`) into `BoardPage`/`CaseDetail` and replace their `api.listCases()` etc. with `api().listCases()`. This is mechanical; do it in this task and adjust their prop types.

- [ ] **Step 3: Update `Chrome.tsx` sign-in / sign-out**

Replace the "Join as a partner" link target `/signup` with `/signin`, and add Clerk's `<UserButton/>` or a `useClerk().signOut()` control when signed in. Minimal change to the existing `<Link to="/signup">`:

```tsx
import { SignedIn, SignedOut, UserButton } from "@clerk/react";
// ...
<SignedOut>
  <Link to="/signin" className={`navitem ${onJoin ? "active" : ""}`}>
    <JoinIcon /> Sign in as a partner
  </Link>
</SignedOut>
<SignedIn>
  <div className="navitem"><UserButton /> Account</div>
</SignedIn>
```

- [ ] **Step 4: Delete `SignupForm.tsx`**

```bash
git rm portal-frontend/src/components/SignupForm.tsx
```

- [ ] **Step 5: Commit**

```bash
git add portal-frontend/src/
git commit -m "feat(portal): Clerk SignIn page + onboarding routing, drop SignupForm"
```

---

### Task 6: Frontend — Onboarding component

**Files:**
- Create: `portal-frontend/src/components/Onboarding.tsx`

**Interfaces:**
- Consumes: `api().onboarding(company)` from Task 4.
- Produces: a one-field form that posts company then calls `onDone(partner)`.

- [ ] **Step 1: Create `Onboarding.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Api, Partner } from "../api";
import { TopBar } from "./Chrome";

export function Onboarding({ api, onDone }: { api: () => Api; onDone: (p: Partner) => void }) {
  const nav = useNavigate();
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const p = await api().onboarding(company.trim());
      onDone(p); nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <>
      <TopBar title="One more thing" sub="Tell us who you're with" partner={null} />
      <main className="main">
        <div className="main-wrap" style={{ maxWidth: 460 }}>
          <form className="card" onSubmit={submit} noValidate>
            {error && <div className="notice notice-err" role="alert">{error}</div>}
            <div className="field">
              <label htmlFor="company">What firm are you with?</label>
              <input id="company" value={company} autoComplete="organization"
                     onChange={(e) => setCompany(e.target.value)} placeholder="Your firm's name" required />
            </div>
            <button className="btn btn-primary btn-block" type="submit" disabled={busy || !company.trim()}>
              {busy ? "Saving…" : "Continue"}
            </button>
          </form>
        </div>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add portal-frontend/src/components/Onboarding.tsx
git commit -m "feat(portal): company onboarding step after Clerk sign-in"
```

---

### Task 7: Build + set Vercel env, deploy to a preview

**Files:** none (build/platform).

**Interfaces:**
- Consumes: all prior tasks; Clerk keys (P1).
- Produces: a Vercel preview URL serving the Clerk-authed portal.

- [ ] **Step 1: Set the Clerk env vars in Vercel**

Via the REST API (CLI absent, npm locked), add to the `partner-usecase-board` project (production + preview): `CLERK_SECRET_KEY` (encrypted), `CLERK_JWKS_URL` (or `CLERK_ISSUER`), `VITE_CLERK_PUBLISHABLE_KEY`. Pattern (repeat per key):

```bash
cd ~/partner-usecase-board
TOK=$(cat .vercel/.token); TEAM=team_L4jxliMIfSnjK5ls5ucK2HYP
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  "https://api.vercel.com/v10/projects/partner-usecase-board/env?teamId=$TEAM" \
  -d '{"key":"VITE_CLERK_PUBLISHABLE_KEY","value":"pk_...","type":"plain","target":["production","preview"]}'
```

- [ ] **Step 2: Trigger a build and confirm the bundle compiles**

Push the branch (or use the deploy path already in use). Watch the Vercel build log: confirm `@clerk/react` resolves and `npm run build` (`tsc -b && vite build`) succeeds. If the Vercel build fails on the package name, correct to the exact current package (`@clerk/clerk-react` if Core 3 rename differs) and re-push.

- [ ] **Step 3: Smoke the API through the preview**

```bash
PREVIEW=<preview-url>
curl -s -o /dev/null -w "healthz %{http_code}\n" $PREVIEW/healthz
curl -s -o /dev/null -w "use-cases %{http_code}\n" $PREVIEW/api/use-cases   # public → 200
curl -s -o /dev/null -w "me-no-token %{http_code}\n" $PREVIEW/api/me         # → 401
```

Expected: `200`, `200`, `401`.

- [ ] **Step 4: No commit** (platform + already-committed code).

---

### Task 8: Manual sign-in verification (browser, gated on Clerk keys)

**Files:** none.

**Interfaces:** consumes the Task 7 preview.

- [ ] **Step 1: Drive the real email-code flow**

In a browser on the preview URL: click "Sign in as a partner" → enter `deep.basu@databricks.com` → receive the Clerk email code → enter it → land on onboarding → enter a company → reach the board. Confirm you can open a case and submit an EOI.

- [ ] **Step 2: Verify the seeded-partner link (no duplicate)**

Sign in with the email of one seeded partner (from `db/seed_full.sql`). Confirm onboarding links the existing row (their prior responses still show in admin) rather than creating a duplicate — check via Neon: `SELECT count(*) FROM partners WHERE email = '<seed-email>';` → 1.

- [ ] **Step 3: Record results**

Note pass/fail per success criterion in the spec. This is the one flow the automated suite can't cover.

---

## Self-review checklist (done by plan author)
- Spec Section A requirements → Tasks 1–8 all mapped (JWKS verify, onboarding, EOI gate, clerk_user_id link, retire cookie, env, manual test). ✓
- No placeholders; every code step shows real code. ✓
- Type consistency: `require_identity` returns `{email, clerk_user_id}` (Task 1) and is consumed identically in Task 3; `makeApi`/`Api` (Task 4) consumed in Tasks 5–6; `link_or_create_partner` signature matches between Task 2 and Task 3. ✓
- Known follow-up threaded to implementer: `BoardPage`/`CaseDetail`/`Chrome` prop-threading for the `api` factory (Task 5 note). ✓
