# Email-Domain Auth Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After Clerk sign-in, route `@databricks.com` (verified) users into the admin cockpit and everyone else to the partner portal — enforced in the backend admin gate AND both frontends, with the shared password kept as a fallback.

**Architecture:** The backend `require_admin` dependency becomes "valid admin cookie OR valid `@databricks.com` Clerk JWT" — this is the security boundary. The portal redirects `@databricks.com` users to `/admin`; the admin SPA gains a `<ClerkProvider>`, auto-recognizes a `@databricks.com` Clerk session (skipping the password screen), and sends the Clerk token as a Bearer header. A single `isDatabricksEmail` rule is defined once per side.

**Tech Stack:** FastAPI + PyJWT (backend, reusing `clerk_auth`), `@clerk/react` v6.12.0 (both SPAs), Vite/React 18, pytest + `unittest.mock`.

## Global Constraints

- **Domain rule (verbatim, one definition per side):** `email.trim().toLowerCase().endsWith("@databricks.com")`. MUST match only exact `...@databricks.com` — reject `a@sub.databricks.com`, `a@notdatabricks.com`, `a@databricks.com.evil.com`, empty/missing. Case-insensitive.
- **Backend is the boundary:** `/api/admin/*` must reject a partner-tier (non-`@databricks.com`) Clerk token with 401. Frontend routing is UX only.
- **Additive / fail-safe:** the existing shared-password cookie path must keep working unchanged. A bad/expired/non-DBX Clerk token must fall through to the cookie check, then 401 — never grant admin on a failed verification.
- **Reuse, don't re-implement:** backend JWT verification reuses `board_api/clerk_auth.py` (`verify_token`, bearer extraction). Do not write new JWT logic.
- **Clerk package:** `@clerk/react` v6.12.0 (already a portal dep). In v6, `SignedIn`/`SignedOut` don't exist — use `<Show when="signed-in|signed-out">` if needed. Confirm any import against `node_modules/@clerk/react` before use.
- **No new env vars:** admin build needs `VITE_CLERK_PUBLISHABLE_KEY` (already set in Vercel); backend already has `CLERK_JWKS_URL` / `CLERK_SECRET_KEY`.
- **No lockfile commits:** `build.sh` deletes lockfiles on Vercel (macOS lockfiles break the Linux build). `git checkout` any `package-lock.json` change before committing; commit only `package.json` + `src`.
- **Redirect discipline:** the portal→/admin redirect must run in a `useEffect`, never during render (matches the existing onboarding-redirect fix).
- **Commit style:** `type(scope): summary`. **Test invocation:** `. .venv/bin/activate && python -m pytest board_api/tests/ -v`. Frontend gate: `npm run build` (`tsc -b && vite build`) with 0 errors — no FE unit harness exists.
- **Do NOT redeploy production** until the whole feature (backend + both frontends) is built, reviewed, and the user approves — a partial deploy could disrupt admin access.

---

### Task 1: Backend — `require_admin` accepts `@databricks.com` Clerk JWT or password cookie

**Files:**
- Modify: `board_api/admin_auth.py`
- Modify: `board_api/routes_admin.py` (`whoami` returns the Clerk email when Clerk-authed)
- Test: `board_api/tests/test_admin_auth.py` (extend)

**Interfaces:**
- Consumes: `board_api/clerk_auth.py` — `verify_token(token) -> claims` and the `Authorization: Bearer` header convention.
- Produces:
  - `is_databricks_email(email: str | None) -> bool` in `admin_auth.py` (backend copy of the rule).
  - `require_admin(request)` passes on a valid admin cookie OR a valid Clerk JWT with a `@databricks.com` email; else 401.
  - `admin_identity(request) -> str` helper returning the effective admin email (Clerk email if Clerk-authed, else `ADMIN_EMAIL`), used by `whoami`.

- [ ] **Step 1: Write failing tests**

Add to `board_api/tests/test_admin_auth.py`. Reuse the local-RS256-JWT technique from `test_clerk_auth.py` (mint a token, inject the public key via the `clerk_auth._signing_key` seam):

```python
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from board_api import admin_auth, clerk_auth

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _tok(claims):
    import time
    return jwt.encode({"exp": int(time.time()) + 3600, "sub": "u1", **claims}, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _inject_key(monkeypatch):
    monkeypatch.setattr(clerk_auth, "_signing_key", lambda token: _KEY.public_key())


def _req(headers=None, cookies=None):
    scope = {"type": "http", "headers": []}
    hs = []
    if headers:
        for k, v in headers.items():
            hs.append((k.lower().encode(), v.encode()))
    if cookies:
        cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
        hs.append((b"cookie", cookie.encode()))
    scope["headers"] = hs
    return Request(scope)


# --- domain rule ---
@pytest.mark.parametrize("email,expected", [
    ("a@databricks.com", True),
    ("A@Databricks.COM", True),
    ("  a@databricks.com  ", True),
    ("a@sub.databricks.com", False),
    ("a@notdatabricks.com", False),
    ("a@databricks.com.evil.com", False),
    ("", False),
    (None, False),
])
def test_is_databricks_email(email, expected):
    assert admin_auth.is_databricks_email(email) is expected


# --- require_admin ---
def test_require_admin_accepts_databricks_clerk_token():
    req = _req(headers={"Authorization": f"Bearer {_tok({'email': 'sa@databricks.com'})}"})
    admin_auth.require_admin(req)  # must not raise


def test_require_admin_rejects_non_databricks_clerk_token():
    req = _req(headers={"Authorization": f"Bearer {_tok({'email': 'partner@gmail.com'})}"})
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(req)
    assert e.value.status_code == 401


def test_require_admin_still_accepts_password_cookie():
    cookie = admin_auth.make_admin_cookie()
    req = _req(cookies={admin_auth.ADMIN_COOKIE_NAME: cookie})
    admin_auth.require_admin(req)  # must not raise


def test_require_admin_401_with_neither():
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(_req())
    assert e.value.status_code == 401


def test_require_admin_rejects_garbage_token():
    req = _req(headers={"Authorization": "Bearer not.a.jwt"})
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(req)
    assert e.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_admin_auth.py -v`
Expected: FAIL — `admin_auth.is_databricks_email` doesn't exist; `require_admin` doesn't accept tokens.

- [ ] **Step 3: Implement in `admin_auth.py`**

Add the import and helpers; rewrite `require_admin`:

```python
from . import clerk_auth  # add near the top with other imports


def is_databricks_email(email) -> bool:
    """True only for exact ...@databricks.com addresses (case-insensitive)."""
    if not email:
        return False
    return email.strip().lower().endswith("@databricks.com")


def _databricks_clerk_email(request) -> str | None:
    """Return the verified Clerk email IFF it's a @databricks.com address, else None.

    Any verification failure returns None so require_admin falls through to the
    cookie check and ultimately 401 — never grants admin on a bad token.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    try:
        claims = clerk_auth.verify_token(token)
    except Exception:
        return None
    email = claims.get("email")
    return email if is_databricks_email(email) else None


def require_admin(request: Request) -> None:
    """Pass on a valid admin cookie OR a valid @databricks.com Clerk JWT."""
    if is_valid_admin(request.cookies.get(ADMIN_COOKIE_NAME, "")):
        return
    if _databricks_clerk_email(request):
        return
    raise HTTPException(401, "admin login required")


def admin_identity(request: Request) -> str:
    """Effective admin email: the Clerk email if Clerk-authed, else ADMIN_EMAIL."""
    return _databricks_clerk_email(request) or ADMIN_EMAIL
```

- [ ] **Step 4: Update `whoami` in `routes_admin.py`**

`whoami` currently returns `{"email": ADMIN_EMAIL}`. Make it reflect the Clerk user when Clerk-authed. It needs the request:

```python
from fastapi import Request  # ensure imported
from .admin_auth import admin_identity  # add to the existing admin_auth import

@router.get("/api/admin/whoami")
def whoami(request: Request):
    return {"email": admin_identity(request)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_admin_auth.py -v`
Then the full suite: `python -m pytest board_api/tests/ -v` — all green.

- [ ] **Step 6: Commit**

```bash
git add board_api/admin_auth.py board_api/routes_admin.py board_api/tests/test_admin_auth.py
git commit -m "feat(admin-auth): accept @databricks.com Clerk JWT or password cookie"
```

---

### Task 2: Portal — redirect `@databricks.com` users to `/admin`

**Files:**
- Create: `portal-frontend/src/auth.ts`
- Modify: `portal-frontend/src/App.tsx`

**Interfaces:**
- Consumes: Clerk `useUser()` (`user.primaryEmailAddress?.emailAddress`).
- Produces: `isDatabricksEmail(email?: string | null): boolean` in `auth.ts`; portal redirects DBX users to `/admin` instead of running the partner flow.

- [ ] **Step 1: Create the shared rule `portal-frontend/src/auth.ts`**

```ts
/** True only for exact ...@databricks.com addresses (case-insensitive). */
export function isDatabricksEmail(email?: string | null): boolean {
  if (!email) return false;
  return email.trim().toLowerCase().endsWith("@databricks.com");
}
```

- [ ] **Step 2: Use it in `App.tsx` to redirect (effect, not render)**

Add `useUser`'s user object and a redirect effect. Import the helper. In the component, after the existing hooks:

```tsx
import { useAuth, useUser } from "@clerk/react";
import { isDatabricksEmail } from "./auth";
// ...
  const { user, isLoaded } = useUser();
  const dbxEmail = isDatabricksEmail(user?.primaryEmailAddress?.emailAddress);

  // Databricks staff belong in the admin cockpit, not the partner portal.
  useEffect(() => {
    if (isLoaded && isSignedIn && dbxEmail) {
      window.location.assign("/admin");
    }
  }, [isLoaded, isSignedIn, dbxEmail]);
```

And guard the existing partner `me()` effect so it does NOT run for a DBX user (avoid onboarding a Databricks user as a partner). Change its early-return condition:

```tsx
  useEffect(() => {
    if (!isLoaded || !isSignedIn || dbxEmail) {
      setPartner(null);
      setNeedsOnboarding(false);
      return;
    }
    api().me().then(/* ...unchanged... */).catch(/* ...unchanged... */);
  }, [isLoaded, isSignedIn, dbxEmail, api]);
```

> Note: `useUser()` already provides `isLoaded`; if the file currently destructures `isLoaded` from `useUser()` separately, consolidate to one `useUser()` call returning `{ user, isLoaded }`. Verify the existing destructuring and keep a single source of `isLoaded`.

- [ ] **Step 3: Build to verify**

Run: `cd portal-frontend && npm run build`
Expected: `tsc -b && vite build` exits 0, no TS errors. Then `git checkout package-lock.json`.

- [ ] **Step 4: Commit**

```bash
git add portal-frontend/src/auth.ts portal-frontend/src/App.tsx
git commit -m "feat(portal): redirect @databricks.com users to the admin cockpit"
```

---

### Task 3: Admin SPA — ClerkProvider + auto-recognize `@databricks.com` session

**Files:**
- Modify: `admin-app/frontend/package.json` (add `@clerk/react`)
- Modify: `admin-app/frontend/src/main.tsx` (wrap in `<ClerkProvider>`)
- Create: `admin-app/frontend/src/auth.ts` (same rule)
- Modify: `admin-app/frontend/src/api.ts` (module-level token getter + optional Bearer)
- Modify: `admin-app/frontend/src/App.tsx` (wire token getter, gate probe on Clerk load)
- Unchanged: `components/AdminLogin.tsx`, `CaseRow.tsx`, `CreateCaseForm.tsx` keep `import { api }` — the module-level token getter means no prop-threading refactor.

**Interfaces:**
- Consumes: `VITE_CLERK_PUBLISHABLE_KEY` (build-time), Clerk `useAuth().getToken()`, `useUser()`.
- Produces: admin SPA authed via Clerk for `@databricks.com` sessions; password path unchanged for everyone else.

- [ ] **Step 1: Add the dependency and provider**

In `admin-app/frontend/package.json` dependencies add `"@clerk/react": "^6.12.0"`. Rewrite `admin-app/frontend/src/main.tsx` to mirror the portal:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import App from "./App";
import "./theme.css";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;
if (!PUBLISHABLE_KEY) throw new Error("VITE_CLERK_PUBLISHABLE_KEY is not set");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <App />
    </ClerkProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 2: Add the shared rule `admin-app/frontend/src/auth.ts`**

```ts
/** True only for exact ...@databricks.com addresses (case-insensitive). */
export function isDatabricksEmail(email?: string | null): boolean {
  if (!email) return false;
  return email.trim().toLowerCase().endsWith("@databricks.com");
}
```

- [ ] **Step 3: Make the singleton `api` send an optional Bearer token via a module-level token getter**

IMPORTANT (from plan self-review): the child components `AdminLogin`, `CaseRow`, and `CreateCaseForm` all `import { api } from "../api"` and call it directly (`api.login`, `api.responsesFor`, `api.setStatus`, `api.createCase`). So DO NOT convert `api` to a prop-threaded factory — that would force refactoring every child. Instead keep the singleton `api` object and give the module a settable token getter that every call reads. This keeps all existing imports working untouched.

Add to the top of `api.ts` and route every call through an `authInit` helper (keep `credentials: "include"`):

```ts
// A Clerk token getter, wired up once by App.tsx. Until set, calls are
// password-cookie only (existing behavior). When set, calls also send a Bearer
// token so a @databricks.com Clerk session authenticates without the password.
let _getToken: (() => Promise<string | null>) | null = null;
export function setAdminTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

async function authInit(init: RequestInit = {}): Promise<RequestInit> {
  const headers = new Headers(init.headers);
  const t = _getToken ? await _getToken() : null;
  if (t) headers.set("Authorization", `Bearer ${t}`);
  return { ...init, credentials: "include", headers };
}
```

Then change each `api` method to `await authInit(...)` instead of the `cred` constant / inline init, preserving each call's method + content-type. E.g.:

```ts
export const api = {
  login: (password: string) =>
    fetch(`${BASE}/api/admin/login`, {
      method: "POST", credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    }).then(json<{ ok: boolean }>),  // login stays as-is (no token needed)
  whoami: async () => fetch(`${BASE}/api/admin/whoami`, await authInit()).then(json<{ email: string }>),
  listCases: async () => fetch(`${BASE}/api/admin/use-cases`, await authInit()).then(json<AdminCase[]>),
  createCase: async (body: { title: string; description: string; industry?: string; region?: string }) =>
    fetch(`${BASE}/api/admin/use-cases`, await authInit({ method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).then(json<AdminCase>),
  setStatus: async (id: string, status: "open" | "closed") =>
    fetch(`${BASE}/api/admin/use-cases/${id}`, await authInit({ method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ status }) })).then(json<AdminCase>),
  responsesFor: async (id: string) => fetch(`${BASE}/api/admin/use-cases/${id}/responses`, await authInit()).then(json<AdminResponse[]>),
  listPartners: async () => fetch(`${BASE}/api/admin/partners`, await authInit()).then(json<AdminPartner[]>),
};
```

The `cred` constant can be removed once every call uses `authInit`. Child components keep importing `{ api }` unchanged.

- [ ] **Step 4: `App.tsx` — wire the token getter and skip password for a DBX Clerk session**

Register the Clerk token getter once, and gate the initial `probe()` on Clerk being loaded so the token is available when `whoami` runs. Because `whoami` now carries the Bearer token, a `@databricks.com` Clerk session returns 200 and `probe()` sets `authed = true`, skipping `<AdminLogin>` automatically — no other logic changes.

```tsx
import { useAuth, useUser } from "@clerk/react";
import { api, setAdminTokenGetter, ApiError, type AdminCase, type AdminPartner } from "./api";
// inside App(), before probe() is defined/used:
const { getToken } = useAuth();
const { isLoaded: clerkLoaded } = useUser();
setAdminTokenGetter(() => getToken());   // idempotent; safe to call each render

// replace the existing `useEffect(() => { probe(); }, [])` with one gated on Clerk:
useEffect(() => { if (clerkLoaded) probe(); }, [clerkLoaded]);
```

`<AdminLogin>` still calls `api.login(password)` for non-Clerk visitors — unchanged.

> The password path is fully preserved: a visitor with no Clerk session has `getToken()` → null, so `authInit` sends no Authorization header, `whoami` 401s, and `<AdminLogin>` shows exactly as today. `AdminLogin`, `CaseRow`, `CreateCaseForm` need NO changes — they still `import { api }`.

- [ ] **Step 5: Build to verify**

Run: `cd admin-app/frontend && npm install && npm run build`
Expected: exits 0, no TS errors. Then `git checkout package-lock.json`.

- [ ] **Step 6: Commit**

```bash
git add admin-app/frontend/package.json admin-app/frontend/src/main.tsx admin-app/frontend/src/auth.ts admin-app/frontend/src/api.ts admin-app/frontend/src/App.tsx
git commit -m "feat(admin): auto-recognize @databricks.com Clerk session, skip password gate"
```

---

### Task 4: Deploy + live verification (gated on user approval)

**Files:** none (platform + browser verification).

**Interfaces:** consumes Tasks 1-3; Clerk env vars already in Vercel.

- [ ] **Step 1: Push and deploy to production** (only after the user approves, per Global Constraints). Push `vercel-neon-deploy`, trigger a production git-source deploy at HEAD, poll to READY, confirm alias promoted.

- [ ] **Step 2: API-level checks (curl)**

```bash
NEW=https://databricks-gt-partner.vercel.app
curl -s -o /dev/null -w "admin whoami no-auth: %{http_code}\n" $NEW/api/admin/whoami   # 401
curl -s -o /dev/null -w "use-cases public:     %{http_code}\n" $NEW/api/use-cases        # 200
```

- [ ] **Step 3: Browser verification (Clerk sign-in can't be curled)**
- Sign in with a `@databricks.com` email → lands in the admin cockpit with NO password prompt.
- Sign in with a non-DBX email → partner board (onboarding or board), no admin access.
- Confirm the password login still works for a fresh (no-Clerk) session at `/admin`.

- [ ] **Step 4: No commit** (platform + already-committed code).

---

## Self-review checklist (plan author)
- Spec Section coverage: backend gate (Task 1), portal routing (Task 2), admin auto-recognize (Task 3), live verification (Task 4) — all mapped. ✓
- No placeholders; every code step shows real code anchored to real files/symbols (`require_admin`, `is_valid_admin`, `make_admin_cookie`, `ADMIN_COOKIE_NAME`, `whoami`, `makeApi`, `probe`, `AdminLogin`). ✓
- Type/name consistency: `is_databricks_email` (backend) / `isDatabricksEmail` (frontend) used consistently; `admin_identity` defined in Task 1 and consumed by `whoami` in the same task; `makeApi`/`Api` defined and consumed in Task 3. ✓
- Fail-safe verified: every Clerk-verification failure path returns None/401, never grants admin. ✓
