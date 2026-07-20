# Unified Clerk Auth — One App, Role-Gated — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two separate React SPAs (partner portal + admin cockpit) into one role-gated app so a `@databricks.com` Clerk sign-in lands on the admin sections (with a "View board" switch) and everyone else sees only the partner board — with the shared admin password kept as a break-glass fallback.

**Architecture:** `portal-frontend/` becomes the single SPA. The admin screens are ported in as role-gated routes; the cross-app `/admin` redirect is deleted. A `useRole()` hook resolves `loading | partner | admin` from the Clerk email domain (with a `whoami` probe that also honours the break-glass cookie). The backend is unchanged — `require_admin` already accepts either a `@databricks.com` Clerk JWT or the password cookie. `build.sh`/`vercel.json` stop producing the second bundle.

**Tech Stack:** React 18.3 + TypeScript 5.6 + Vite 5.4, `@clerk/react` ^6.12, react-router-dom 6.26 (frontend); FastAPI + psycopg on Vercel Python function (backend); Neon Postgres; pytest (backend tests).

**Spec:** [docs/superpowers/specs/2026-07-20-unified-clerk-auth-design.md](../specs/2026-07-20-unified-clerk-auth-design.md)

## Global Constraints

- **Branch:** all work on `vercel-neon-deploy`. Do NOT touch the Databricks-App variant on `main`.
- **No new env vars.** Reuse `VITE_CLERK_PUBLISHABLE_KEY`, `CLERK_JWKS_URL`, `CLERK_ISSUER`, `ADMIN_PASSWORD`, `ADMIN_SESSION_SECRET`, `SESSION_SECRET`, `DATABASE_URL`, `ADMIN_EMAIL`.
- **No new npm dependencies.** No new frontend test harness (none exists today; frontend is verified by `npm run build` typecheck + a manual browser pass, per the approved spec). Rationale is the supply-chain lockdown: npm installs go through a proxy, so adding deps is friction we don't need for this UI merge.
- **The domain rule is defined once per surface, never inline:** `isDatabricksEmail(email) := email.trim().toLowerCase().endsWith("@databricks.com")`. Frontend copy lives in `portal-frontend/src/auth.ts` (already present); backend copy is `board_api/admin_auth.py::is_databricks_email` (unchanged). Matches only exact `...@databricks.com`, case-insensitive.
- **Security boundary is the backend, not the UI.** Frontend role-gating is convenience; every `/api/admin/*` route stays guarded by `require_admin`. No task may weaken a backend dependency.
- **Backend test suite (51 tests) must stay green** after every backend-touching task. Canonical command: `./run_tests.sh` (spins an ephemeral local PG16). Route/auth tests that mock the DB can also run directly with `.venv/bin/pytest`.
- **Fails safe:** any auth ambiguity (missing email claim, unverifiable token, Clerk outage) resolves to partner / login, never to admin.
- **All role-driven navigation happens in effects, never during render** (matches the existing onboarding-redirect discipline).
- **`vercel.json` is edited in place** — never reconstructed from prose — so `/healthz` and other routes are not accidentally dropped.

---

### Task 1: Unified API client

Merge the admin API methods into the portal's `makeApi(getToken)` factory and make every authed call send BOTH the Clerk Bearer token (when present) AND `credentials: "include"` (so the break-glass cookie also authenticates). This is the foundation every later frontend task consumes.

**Files:**
- Modify: `portal-frontend/src/api.ts` (whole file rewritten below)

**Interfaces:**
- Consumes: `getToken: () => Promise<string | null>` from Clerk's `useAuth()` (already how the portal builds its client).
- Produces: `makeApi(getToken)` returning an object with the existing partner methods **plus** `adminWhoami()`, `adminLogin(password)`, `listAllCases()`, `createCase(body)`, `setCaseStatus(id, status)`, `responsesFor(id)`, `listPartners()`. Exported types: `UseCase`, `Partner`, `Me`, `AdminCase`, `AdminResponse`, `AdminPartner`, `Api`, `ApiError`.

- [ ] **Step 1: Rewrite `portal-frontend/src/api.ts`**

```ts
// Typed client for the board backend. Same-origin in prod (SPA served by the
// Vercel Python function); dev uses Vite's proxy. Auth carries BOTH a Clerk
// Bearer token (partner + @databricks.com admin) AND the cookie
// (break-glass admin password) so either path authenticates.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export type UseCase = {
  id: string;
  title: string;
  description: string;
  industry?: string | null;
  region?: string | null;
  status: string;
  created_at: string;
};

export type Partner = { id: string; email: string; company: string };
export type Me = Partner | { onboarding_required: true };

export type AdminCase = {
  id: string;
  title: string;
  description: string;
  industry?: string | null;
  region?: string | null;
  status: "open" | "closed";
  posted_by: string;
  created_at: string;
  closed_at?: string | null;
  response_count: number;
};

export type AdminResponse = {
  id: string;
  approach: string;
  created_at: string;
  company: string;
  email: string;
  contact_name?: string | null;
};

export type AdminPartner = {
  id: string;
  email: string;
  company: string;
  contact_name?: string | null;
  created_at: string;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(r.status, (detail as { detail?: string }).detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

// getToken comes from Clerk's useAuth(); null token => no auth header (public
// reads still work). credentials:"include" is ALWAYS set so the break-glass
// admin cookie flows even when there is no Clerk token.
export function makeApi(getToken: () => Promise<string | null>) {
  const authInit = async (init: RequestInit = {}): Promise<RequestInit> => {
    const headers = new Headers(init.headers);
    const t = await getToken();
    if (t) headers.set("Authorization", `Bearer ${t}`);
    return { ...init, credentials: "include", headers };
  };

  return {
    // ── partner ──────────────────────────────────────────────────────────
    me: async (): Promise<Me | null> => {
      const r = await fetch(`${BASE}/api/me`, await authInit());
      return r.ok ? ((await r.json()) as Me) : null;
    },
    onboarding: async (company: string) =>
      fetch(`${BASE}/api/onboarding`, await authInit({
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ company }),
      })).then(json<Partner>),
    listCases: () => fetch(`${BASE}/api/use-cases`).then(json<UseCase[]>),
    getCase: (id: string) => fetch(`${BASE}/api/use-cases/${id}`).then(json<UseCase>),
    respond: async (id: string, approach: string) =>
      fetch(`${BASE}/api/use-cases/${id}/responses`, await authInit({
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approach }),
      })).then(json<{ id: string }>),

    // ── admin ────────────────────────────────────────────────────────────
    // login needs no token — it MINTS the cookie; still same-origin credentials.
    adminLogin: (password: string) =>
      fetch(`${BASE}/api/admin/login`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password }),
      }).then(json<{ ok: boolean }>),
    adminWhoami: async () =>
      fetch(`${BASE}/api/admin/whoami`, await authInit()).then(json<{ email: string }>),
    listAllCases: async () =>
      fetch(`${BASE}/api/admin/use-cases`, await authInit()).then(json<AdminCase[]>),
    createCase: async (body: {
      title: string;
      description: string;
      industry?: string;
      region?: string;
    }) =>
      fetch(`${BASE}/api/admin/use-cases`, await authInit({
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      })).then(json<AdminCase>),
    setCaseStatus: async (id: string, status: "open" | "closed") =>
      fetch(`${BASE}/api/admin/use-cases/${id}`, await authInit({
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status }),
      })).then(json<AdminCase>),
    responsesFor: async (id: string) =>
      fetch(`${BASE}/api/admin/use-cases/${id}/responses`, await authInit()).then(json<AdminResponse[]>),
    listPartners: async () =>
      fetch(`${BASE}/api/admin/partners`, await authInit()).then(json<AdminPartner[]>),
  };
}
export type Api = ReturnType<typeof makeApi>;
```

- [ ] **Step 2: Typecheck**

Run: `cd portal-frontend && npm run build`
Expected: FAILS — `BoardPage.tsx`, `CaseDetail.tsx` still compile (they use `listCases`/`getCase`/`respond`, unchanged), but this is the moment other imports of the old admin singleton would break. Since no portal file yet imports the admin methods, the build should actually SUCCEED here. If it fails, it means a consumer references a renamed symbol — fix the consumer, do not re-add the old export.

- [ ] **Step 3: Commit**

```bash
git add portal-frontend/src/api.ts
git commit -m "feat(api): unified client with admin methods + credentials for break-glass

Co-authored-by: Isaac"
```

---

### Task 2: `useRole()` hook

The single source of truth for what the signed-in user is. Pure-ish decision logic with a Clerk-load fallback so a Clerk outage can't lock out the break-glass login.

**Files:**
- Create: `portal-frontend/src/role.ts`

**Interfaces:**
- Consumes: `useAuth`, `useUser` from `@clerk/react`; `isDatabricksEmail` from `./auth`; `makeApi` from `./api`.
- Produces: `useRole(): { role: "loading" | "partner" | "admin"; email: string | null; refresh: () => void }`. `email` is the admin identity string when admin (Clerk email or the backend's `ADMIN_EMAIL` for break-glass), else null. `refresh()` re-probes after a break-glass login.

- [ ] **Step 1: Create `portal-frontend/src/role.ts`**

```ts
import { useCallback, useEffect, useState } from "react";
import { useAuth, useUser } from "@clerk/react";
import { isDatabricksEmail } from "./auth";
import { makeApi } from "./api";

export type Role = "loading" | "partner" | "admin";

// Resolve the caller's role. Order (all fail-safe — ambiguity => not admin):
//   1. Clerk still loading                -> "loading"
//   2. signed-in @databricks.com email    -> "admin"  (email from Clerk)
//   3. else GET /api/admin/whoami == 200   -> "admin"  (break-glass cookie)
//   4. else                                -> "partner"
// A 4s fallback covers Clerk never loading (outage / blocked key) so the
// break-glass whoami probe still runs and /admin/login stays reachable.
export function useRole() {
  const { getToken, isSignedIn } = useAuth();
  const { user, isLoaded } = useUser();
  const [role, setRole] = useState<Role>("loading");
  const [email, setEmail] = useState<string | null>(null);
  const [clerkTimedOut, setClerkTimedOut] = useState(false);

  const dbxEmail = isDatabricksEmail(user?.primaryEmailAddress?.emailAddress);

  useEffect(() => {
    if (isLoaded) return;
    const t = setTimeout(() => setClerkTimedOut(true), 4000);
    return () => clearTimeout(t);
  }, [isLoaded]);

  const resolve = useCallback(async () => {
    if (!isLoaded && !clerkTimedOut) {
      setRole("loading");
      return;
    }
    if (isLoaded && isSignedIn && dbxEmail) {
      setRole("admin");
      setEmail(user?.primaryEmailAddress?.emailAddress ?? null);
      return;
    }
    // Probe the break-glass cookie (and, harmlessly, a dbx token if present).
    try {
      const who = await makeApi(() => getToken()).adminWhoami();
      setRole("admin");
      setEmail(who.email);
    } catch {
      setRole("partner");
      setEmail(null);
    }
  }, [isLoaded, clerkTimedOut, isSignedIn, dbxEmail, user, getToken]);

  useEffect(() => {
    void resolve();
  }, [resolve]);

  return { role, email, refresh: () => void resolve() };
}
```

- [ ] **Step 2: Typecheck**

Run: `cd portal-frontend && npm run build`
Expected: PASS (nothing imports `role.ts` yet, but it must compile).

- [ ] **Step 3: Commit**

```bash
git add portal-frontend/src/role.ts
git commit -m "feat(auth): useRole hook — domain-gated role with break-glass probe + Clerk-outage fallback

Co-authored-by: Isaac"
```

---

### Task 3: Port the admin sections (components + styles)

Bring the three admin screens into the portal app, rewritten to use the `makeApi(getToken)` instance (via an `api: () => Api` prop, exactly like `BoardPage`) instead of the old module singleton, and port their CSS so they render styled inside the portal theme.

**Files:**
- Create: `portal-frontend/src/components/AdminCases.tsx`
- Create: `portal-frontend/src/components/AdminPartners.tsx`
- Create: `portal-frontend/src/components/AdminLogin.tsx`
- Modify: `portal-frontend/src/theme.css` (append ported admin rules + token harmonisation)

**Interfaces:**
- Consumes: `Api`, `AdminCase`, `AdminResponse`, `AdminPartner`, `ApiError` from `../api` (Task 1).
- Produces: `<AdminCases api={() => Api} />`, `<AdminPartners api={() => Api} />`, `<AdminLogin api={() => Api} onAuthed={() => void} />`.

- [ ] **Step 1: Create `portal-frontend/src/components/AdminCases.tsx`**

```tsx
import { useEffect, useState } from "react";
import type { Api, AdminCase, AdminResponse } from "../api";

export function AdminCases({ api }: { api: () => Api }) {
  const [cases, setCases] = useState<AdminCase[] | null>(null);

  useEffect(() => {
    api().listAllCases().then(setCases).catch(() => setCases([]));
  }, [api]);

  function onCreated(c: AdminCase) {
    setCases((prev) => [{ ...c, response_count: 0 }, ...(prev ?? [])]);
  }
  function onChanged(u: AdminCase) {
    setCases((prev) => (prev ?? []).map((c) => (c.id === u.id ? u : c)));
  }

  return (
    <div className="cols">
      <div>
        <CreateCaseForm api={api} onCreated={onCreated} />
      </div>
      <div>
        <p className="section-label">Posted use cases</p>
        {cases === null ? (
          <div className="center-state"><div className="spinner" />Loading…</div>
        ) : cases.length === 0 ? (
          <div className="center-state">No use cases yet. Post your first one on the left.</div>
        ) : (
          cases.map((c) => <CaseRow key={c.id} api={api} c={c} onChanged={onChanged} />)
        )}
      </div>
    </div>
  );
}

function CreateCaseForm({ api, onCreated }: { api: () => Api; onCreated: (c: AdminCase) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [industry, setIndustry] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const c = await api().createCase({
        title: title.trim(),
        description: description.trim(),
        industry: industry.trim() || undefined,
        region: region.trim() || undefined,
      });
      onCreated(c);
      setMsg({ ok: true, text: "Posted. Registered partners have been emailed." });
      setTitle(""); setDescription(""); setIndustry(""); setRegion("");
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed to post." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Post a use case</h2>
      <p className="card-hint">Registered partners are emailed when you post.</p>
      {msg && <div className={`notice ${msg.ok ? "notice-ok" : "notice-err"}`}>{msg.text}</div>}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="e.g. Workforce Management — ANZ" required />
        </div>
        <div className="field">
          <label htmlFor="desc">The ask</label>
          <textarea id="desc" value={description} onChange={(e) => setDescription(e.target.value)}
                    placeholder="What you need help with, context, and what a good partner looks like." required />
        </div>
        <div className="row2">
          <div className="field">
            <label htmlFor="industry">Industry (optional)</label>
            <input id="industry" value={industry} onChange={(e) => setIndustry(e.target.value)}
                   placeholder="e.g. Utilities" />
          </div>
          <div className="field">
            <label htmlFor="region">Region (optional)</label>
            <input id="region" value={region} onChange={(e) => setRegion(e.target.value)}
                   placeholder="e.g. ANZ" />
          </div>
        </div>
        <button className="btn btn-primary btn-block" type="submit"
                disabled={busy || !title.trim() || !description.trim()}>
          {busy ? "Posting…" : "Post & notify partners"}
        </button>
      </form>
    </div>
  );
}

function CaseRow({ api, c, onChanged }: { api: () => Api; c: AdminCase; onChanged: (c: AdminCase) => void }) {
  const [open, setOpen] = useState(false);
  const [responses, setResponses] = useState<AdminResponse[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggleResponses() {
    const next = !open;
    setOpen(next);
    if (next && responses === null) setResponses(await api().responsesFor(c.id));
  }
  async function toggleStatus() {
    setBusy(true);
    try {
      const u = await api().setCaseStatus(c.id, c.status === "open" ? "closed" : "open");
      onChanged({ ...c, status: u.status, closed_at: u.closed_at });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="case-row">
      <div className="hd">
        <div className="htxt">
          <h3>{c.title}</h3>
          <div className="meta">
            {c.region ? `${c.region} · ` : ""}{c.industry ? `${c.industry} · ` : ""}posted by {c.posted_by}
          </div>
        </div>
        <span className={`pill ${c.status === "open" ? "pill-open" : "pill-closed"}`}>{c.status}</span>
      </div>
      <div className="row-actions">
        <button className="count-chip" onClick={toggleResponses}>
          {c.response_count} response{c.response_count === 1 ? "" : "s"} {open ? "▲" : "▼"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={toggleStatus} disabled={busy}>
          {c.status === "open" ? "Close" : "Reopen"}
        </button>
      </div>
      {open && (
        <div className="responses">
          {responses === null ? (
            <div className="muted">Loading responses…</div>
          ) : responses.length === 0 ? (
            <div className="muted">No responses yet.</div>
          ) : (
            responses.map((r) => (
              <div className="resp" key={r.id}>
                <div className="rhd"><b>{r.company}</b><a href={`mailto:${r.email}`}>{r.email}</a></div>
                {r.contact_name && <div className="who-name">{r.contact_name}</div>}
                <div className="approach">{r.approach}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `portal-frontend/src/components/AdminPartners.tsx`**

```tsx
import { useEffect, useState } from "react";
import type { Api, AdminPartner } from "../api";

export function AdminPartners({ api }: { api: () => Api }) {
  const [partners, setPartners] = useState<AdminPartner[] | null>(null);

  useEffect(() => {
    api().listPartners().then(setPartners).catch(() => setPartners([]));
  }, [api]);

  return (
    <div className="card">
      {partners === null ? (
        <div className="center-state"><div className="spinner" />Loading…</div>
      ) : partners.length === 0 ? (
        <div className="center-state">No partners have signed up yet.</div>
      ) : (
        <div className="table-wrap">
          <table className="ptable">
            <thead>
              <tr><th>Company</th><th>Email</th><th>Contact</th><th>Joined</th></tr>
            </thead>
            <tbody>
              {partners.map((p) => (
                <tr key={p.id}>
                  <td><b>{p.company}</b></td>
                  <td><a href={`mailto:${p.email}`}>{p.email}</a></td>
                  <td>{p.contact_name ?? "—"}</td>
                  <td className="muted nowrap">{new Date(p.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `portal-frontend/src/components/AdminLogin.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { ApiError, type Api } from "../api";
import { DatabricksLogo } from "./Chrome";

// Break-glass password gate. Reachable at /admin/login WITHOUT a Clerk session,
// so it works during a Clerk outage and for a non-@databricks.com admin. On
// success the backend sets the admin cookie; onAuthed() re-probes the role.
export function AdminLogin({ api, onAuthed }: { api: () => Api; onAuthed: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api().adminLogin(password);
      onAuthed();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Incorrect password."
          : "Couldn't sign in. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">
          <DatabricksLogo />
          <div className="login-wordmark">Partner Board</div>
        </div>
        <h1 className="login-title">Admin sign in</h1>
        <p className="login-sub">Break-glass password for the Databricks team. Employees normally sign in with their @databricks.com email instead.</p>
        <label className="login-label" htmlFor="pw">Password</label>
        <input id="pw" className="login-input" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)} autoFocus
               autoComplete="current-password" placeholder="••••••••••" />
        {error && <div className="login-error">{error}</div>}
        <button className="login-btn" type="submit" disabled={busy || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Append the ported admin CSS to `portal-frontend/src/theme.css`**

Copy the following class-block rules verbatim from `admin-app/frontend/src/theme.css` into the end of `portal-frontend/src/theme.css` (these class names were verified absent from the portal theme, so there are no collisions): `.cols`, `.row2`, `.card-hint`, `.case-row`, `.hd`, `.htxt`, `.meta`, `.row-actions`, `.count-chip`, `.responses`, `.resp`, `.rhd`, `.who-name`, `.approach`, `.pill-closed`, `.table-wrap`, `.ptable`, `.nowrap`, `.notice`, `.notice-ok`, `.notice-err`, `.login-shell`, `.login-card`, `.login-logo`, `.login-wordmark`, `.login-title`, `.login-sub`, `.login-label`, `.login-input`, `.login-error`, `.login-btn`, `.btn-ghost`, `.btn-sm`, `.spinner`. Then append this harmonisation block so the admin surface reads in the portal's warm/coral palette rather than the admin cockpit's grey (adjust only if the portal theme's variable names differ — check the `:root` block at the top of `portal-frontend/src/theme.css` first):

```css
/* ── admin sections harmonised to the portal (editorial) palette ─────────── */
.login-shell { background: var(--paper, #f6f2ea); }
.login-btn, .btn-primary { background: var(--coral, #d94f36); color: #fff; }
.count-chip { border-color: var(--coral, #d94f36); color: var(--coral, #d94f36); }
.case-row { background: #fff; border: 1px solid var(--line, #e6ddcd); }
.pill-open { background: #e9f6ee; color: #1a7f45; }
.pill-closed { background: #efe9e0; color: #7a6f5c; }
```

- [ ] **Step 5: Typecheck**

Run: `cd portal-frontend && npm run build`
Expected: FAILS — `AdminLogin.tsx` imports `DatabricksLogo` from `./Chrome`, which is already exported (verified). If any admin component references a symbol not exported by `api.ts`, fix the reference. Iterate until PASS.

- [ ] **Step 6: Commit**

```bash
git add portal-frontend/src/components/AdminCases.tsx \
        portal-frontend/src/components/AdminPartners.tsx \
        portal-frontend/src/components/AdminLogin.tsx \
        portal-frontend/src/theme.css
git commit -m "feat(portal): port admin sections (cases, partners, break-glass login) + styles

Co-authored-by: Isaac"
```

---

### Task 4: Role-aware navigation (`Chrome.tsx` Rail)

Replace the hard `<a href="/admin">` (which triggers the cross-app jump) with role-aware nav: admin items + a "View board"/"Back to admin" toggle for admins; the unchanged partner nav otherwise.

**Files:**
- Modify: `portal-frontend/src/components/Chrome.tsx` (the `Rail` function, lines 55-91)

**Interfaces:**
- Consumes: `Role` from `../role`.
- Produces: `<Rail role={Role} partner={Partner | null} adminEmail={string | null} />`.

- [ ] **Step 1: Replace the `Rail` function in `portal-frontend/src/components/Chrome.tsx`**

Replace the entire existing `Rail` export (currently lines 55-91) with:

```tsx
/** Sidebar rail. Role-aware: partners see Browse + sign-in; admins see the
 *  admin sections plus a "View board" toggle. */
export function Rail({
  role,
  partner,
  adminEmail,
}: {
  role: import("../role").Role;
  partner: Partner | null;
  adminEmail: string | null;
}) {
  const { pathname } = useLocation();
  const onBoard = pathname === "/" || pathname.startsWith("/case");
  const onJoin = pathname.startsWith("/signin");
  const onAdmin = pathname.startsWith("/admin");

  return (
    <nav className="rail">
      <Link to={role === "admin" ? "/admin" : "/"} className="logo">
        <DatabricksLogo />
        <div className="wordmark">Partner Board</div>
      </Link>

      {role === "admin" ? (
        <>
          <div className="navlabel">Manage</div>
          <Link to="/admin" className={`navitem ${onAdmin && pathname === "/admin" ? "active" : ""}`}>
            <AdminIcon /> Use cases
          </Link>
          <Link to="/admin/partners" className={`navitem ${pathname === "/admin/partners" ? "active" : ""}`}>
            <JoinIcon /> Partners
          </Link>
          <Link to="/" className={`navitem ${onBoard ? "active" : ""}`}>
            <BoardIcon /> {onBoard ? "Back to admin" : "View board"}
          </Link>
          <div className="spacer" />
          {adminEmail && (
            <div className="navitem" title={adminEmail}>
              <span className="avatar">{initials(adminEmail)}</span>
              <span className="who-txt">{adminEmail}</span>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="navlabel">Browse</div>
          <Link to="/" className={`navitem ${onBoard ? "active" : ""}`}>
            <BoardIcon /> Open use cases
          </Link>
          <Show when="signed-out">
            <Link to="/signin" className={`navitem ${onJoin ? "active" : ""}`}>
              <JoinIcon /> Sign in as a partner
            </Link>
          </Show>
          <Show when="signed-in">
            <div className="navitem">
              <UserButton /> {partner?.company ?? "Account"}
            </div>
          </Show>
          <div className="spacer" />
        </>
      )}
    </nav>
  );
}
```

Note: `initials()` currently splits on whitespace (built for a company name). An email like `jane.doe@databricks.com` has no space, so it yields one letter. That is acceptable for the avatar; do NOT change `initials` here (it's shared with the partner chip).

- [ ] **Step 2: Typecheck**

Run: `cd portal-frontend && npm run build`
Expected: FAILS — `App.tsx` still calls `<Rail partner={partner} />` without the new required `role`/`adminEmail` props. That is fixed in Task 5. To verify THIS task in isolation, confirm the only remaining error is in `App.tsx` at the `<Rail .../>` call site. If there are errors inside `Chrome.tsx` itself, fix them.

- [ ] **Step 3: Commit**

```bash
git add portal-frontend/src/components/Chrome.tsx
git commit -m "feat(nav): role-aware Rail with View board / Back to admin toggle

Co-authored-by: Isaac"
```

---

### Task 5: Rewire `App.tsx` — delete the redirect, add role routing

The keystone. Delete the `window.location.assign("/admin")` redirect; drive the app from `useRole()`; add `/admin`, `/admin/login`, and the admin board-view.

**Files:**
- Modify: `portal-frontend/src/App.tsx` (whole file rewritten below)

**Interfaces:**
- Consumes: `useRole` (Task 2), `makeApi`/`Api`/`Partner` (Task 1), `Rail` (Task 4), `AdminCases`/`AdminPartners`/`AdminLogin` (Task 3), existing `BoardPage`/`SignInPage`/`Onboarding`/`CaseDetail`.
- Produces: the single-app route tree.

- [ ] **Step 1: Rewrite `portal-frontend/src/App.tsx`**

```tsx
import { useEffect, useState, useCallback } from "react";
import { Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import { useAuth, useUser } from "@clerk/react";
import { makeApi, type Partner } from "./api";
import { useRole } from "./role";
import { Rail } from "./components/Chrome";
import { BoardPage } from "./components/BoardPage";
import { SignInPage } from "./components/SignInPage";
import { Onboarding } from "./components/Onboarding";
import { CaseDetail } from "./components/CaseDetail";
import { AdminCases } from "./components/AdminCases";
import { AdminPartners } from "./components/AdminPartners";
import { AdminLogin } from "./components/AdminLogin";

export default function App() {
  const { getToken, isSignedIn } = useAuth();
  const { isLoaded } = useUser();
  const { role, email: adminEmail, refresh } = useRole();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [partner, setPartner] = useState<Partner | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  const api = useCallback(() => makeApi(() => getToken()), [getToken]);

  // Partner profile lookup runs for partners only (not admins, not while loading).
  useEffect(() => {
    if (role !== "partner" || !isLoaded || !isSignedIn) {
      setPartner(null);
      setNeedsOnboarding(false);
      return;
    }
    api().me().then((m) => {
      if (m && "onboarding_required" in m) { setNeedsOnboarding(true); setPartner(null); }
      else if (m) { setPartner(m); setNeedsOnboarding(false); }
    }).catch(() => { /* transient: keep state; board is public anyway */ });
  }, [role, isLoaded, isSignedIn, api]);

  // Onboarding redirect — effect, never during render.
  useEffect(() => {
    if (needsOnboarding && pathname !== "/onboarding") navigate("/onboarding");
  }, [needsOnboarding, pathname, navigate]);

  if (role === "loading") {
    return <div className="login-shell"><div className="spinner" /></div>;
  }

  return (
    <div className="app">
      <Rail role={role} partner={partner} adminEmail={adminEmail} />
      <div className="content">
        <Routes>
          <Route path="/" element={<BoardPage partner={partner} api={api} />} />
          <Route path="/signin/*" element={<SignInPage />} />
          <Route path="/case/:id" element={<CaseDetail partner={partner} api={api} />} />
          <Route
            path="/onboarding"
            element={<Onboarding api={api} onDone={(p) => { setPartner(p); setNeedsOnboarding(false); }} />}
          />
          {/* Break-glass login is always reachable (even with no Clerk session). */}
          <Route path="/admin/login" element={<AdminLogin api={api} onAuthed={refresh} />} />
          {/* Admin cockpit — gated in the UI by role; the backend gates the data. */}
          <Route
            path="/admin"
            element={role === "admin" ? <AdminCases api={api} /> : <Navigate to="/admin/login" replace />}
          />
          <Route
            path="/admin/partners"
            element={role === "admin" ? <AdminPartners api={api} /> : <Navigate to="/admin/login" replace />}
          />
        </Routes>
      </div>
    </div>
  );
}
```

Note: the admin "Use cases" (`/admin`) and "Partners" (`/admin/partners`) nav links are already provided by the role-aware Rail from Task 4 (using the portal's existing `AdminIcon`/`JoinIcon`/`BoardIcon` — no new icon components needed). No extra nav wiring is required here.

- [ ] **Step 2: Full typecheck + build**

Run: `cd portal-frontend && npm run build`
Expected: PASS. All prior tasks reconcile here. Fix any remaining type/prop mismatches.

- [ ] **Step 3: Manual smoke (dev server)**

Run the backend + this frontend locally (see `run_local.sh`; backend on :8000, `npm run dev` on :5173). Verify in a browser:
- `/` with no session → partner board renders, Rail shows Browse + "Sign in as a partner".
- `/admin` with no session → redirects to `/admin/login`, break-glass form renders.

- [ ] **Step 4: Commit**

```bash
git add portal-frontend/src/App.tsx portal-frontend/src/components/Chrome.tsx
git commit -m "feat(app): single role-gated app — delete cross-app redirect, add /admin routes

Co-authored-by: Isaac"
```

---

### Task 6: Build + routing + retire the admin bundle

Stop producing the second SPA and remove the `/admin*` static routes so the client router owns those paths.

**Files:**
- Modify: `build.sh`
- Modify: `vercel.json`
- Modify: `admin-app/frontend/src/App.tsx` (add a one-line deprecation banner comment at the top)
- Modify: `run_local.sh` (drop the admin-frontend dev process if it starts one)

**Interfaces:** none (build/deploy config).

- [ ] **Step 1: Simplify `build.sh` to build one SPA**

Replace the build/assemble section so only `portal-frontend` is built and copied:

```bash
echo "── building portal-frontend (single unified app) ──"
( cd portal-frontend && rm -f package-lock.json && npm install --no-audit --no-fund && npm run build )

echo "── assembling dist/ ──"
rm -rf dist
cp -r portal-frontend/dist dist

echo "── dist/ contents ──"
ls -la dist
```

Delete the `admin-app/frontend` build step and the `dist/admin` copy lines.

- [ ] **Step 2: Edit `vercel.json` in place — remove ONLY the three `/admin*` routes**

Delete exactly these three lines (keep every other route, including `/healthz`):

```json
{ "src": "/admin/assets/(.*)", "dest": "/admin/assets/$1" },
{ "src": "/admin/(.+)", "dest": "/admin/$1" },
{ "src": "/admin", "dest": "/admin/index.html" },
```

The remaining `handle: filesystem` + `/(.*) → /index.html` fallback now serves `/admin` and `/admin/login` to the SPA. Verify the file still parses (it is small — re-read it).

- [ ] **Step 3: Mark the old admin frontend deprecated**

Add as the very first line of `admin-app/frontend/src/App.tsx`:

```tsx
// DEPRECATED (2026-07-20): the admin cockpit now lives inside portal-frontend/
// as role-gated routes. This file is no longer built or deployed on
// vercel-neon-deploy. Kept only for the Databricks-App variant referenced by main.
```

- [ ] **Step 4: Fix `run_local.sh`**

Read `run_local.sh`; if it launches the admin frontend (port 5174) or a second backend (8001), remove those lines so it runs one backend (:8000) + one frontend (`portal-frontend` on :5173). If it already runs only the portal, no change.

- [ ] **Step 5: Full build from repo root**

Run: `./build.sh`
Expected: PASS; `dist/` exists with `index.html` + `assets/`, and **no `dist/admin/` directory**. Confirm: `test ! -d dist/admin && echo "no admin subtree OK"`.

- [ ] **Step 6: Commit**

```bash
git add build.sh vercel.json admin-app/frontend/src/App.tsx run_local.sh
git commit -m "build: single-SPA output; drop /admin* routes; deprecate old admin frontend

Co-authored-by: Isaac"
```

---

### Task 7: Backend regression guard for the security boundary

The backend needs no functional change, but the entire design rests on `require_admin` accepting exactly two paths and nothing else. Pin that with an explicit test so a future edit can't silently open or close the gate. (Most coverage already exists in `test_admin_auth.py`; this task adds the one combined-matrix assertion if absent and confirms the suite is green.)

**Files:**
- Modify: `board_api/tests/test_admin_auth.py` (add a matrix test if not already present)

**Interfaces:** none (test-only).

- [ ] **Step 1: Inspect existing coverage**

Run: `.venv/bin/pytest board_api/tests/test_admin_auth.py -v`
Read the test names. If a test already asserts all four of {valid dbx JWT → allow, non-dbx JWT → 401, valid cookie → allow, neither → 401}, skip Steps 2-3 and go to Step 4.

- [ ] **Step 2: Write the failing matrix test**

Append to `board_api/tests/test_admin_auth.py` (mirror the locally-minted-JWT helper already used in that file / `test_clerk_auth.py`; if the helper is named differently, reuse the existing one rather than redefining):

```python
def test_require_admin_matrix(monkeypatch):
    """require_admin allows exactly: valid @databricks.com JWT OR valid cookie."""
    from board_api import admin_auth
    from fastapi import HTTPException

    # (reuse the module's existing JWT-minting + JWKS-patch helpers here)
    dbx = _make_request(bearer=_mint({"email": "a@databricks.com", "sub": "u1"}))
    ext = _make_request(bearer=_mint({"email": "a@gmail.com", "sub": "u2"}))
    cookie = _make_request(cookie=admin_auth.make_admin_cookie())
    none = _make_request()

    assert admin_auth.require_admin(dbx) is None            # dbx JWT allowed
    assert admin_auth.require_admin(cookie) is None          # break-glass allowed
    for bad in (ext, none):
        try:
            admin_auth.require_admin(bad)
            assert False, "should have 401'd"
        except HTTPException as e:
            assert e.status_code == 401
```

If `test_admin_auth.py` lacks `_make_request`/`_mint` helpers, adapt to whatever pattern the file already uses (e.g. building a `Request` scope dict and patching `clerk_auth._signing_key`). Do NOT invent a networked call — verification must stay offline like the existing tests.

- [ ] **Step 3: Run it red, then confirm the code already satisfies it**

Run: `.venv/bin/pytest board_api/tests/test_admin_auth.py::test_require_admin_matrix -v`
Expected: PASS immediately (the behaviour already exists — this is a regression pin, not new behaviour). If it FAILS, the test harness helpers are wired wrong (not the app) — fix the test.

- [ ] **Step 4: Full suite green**

Run: `./run_tests.sh`
Expected: all 51 (or 52 with the new test) pass.

- [ ] **Step 5: Commit**

```bash
git add board_api/tests/test_admin_auth.py
git commit -m "test(auth): pin require_admin two-path matrix as a regression guard

Co-authored-by: Isaac"
```

---

### Task 8: End-to-end verification + independent check

The frontend has no unit harness (per the approved spec), so the acceptance gate is a manual browser pass on a preview deploy plus an independent verification agent — matching the project's verification rule.

**Files:** none (verification only).

- [ ] **Step 1: Deploy a Vercel preview**

Push the branch and let Vercel build a preview, or `vercel` (preview). Confirm the build log shows one SPA and no `dist/admin`.

- [ ] **Step 2: Manual browser matrix (record pass/fail for each)**

1. Partner OTP: sign in with a **non**-`@databricks.com` email → lands on the board; complete onboarding; respond to an open case; confirm no admin nav is ever shown.
2. Employee OTP: sign in with a `@databricks.com` email → lands on the **admin cockpit** with **no** password prompt and **no** full-page redirect; create a case; close/reopen it; open a case's responses; open Partners; click "View board" → board renders read-only (no EOI form / cannot respond, since there's no partner profile); "Back to admin" returns.
3. Break-glass: in a fresh session (signed out of Clerk) go to `/admin/login`, enter `ADMIN_PASSWORD` → admin unlocks; identity chip shows `ADMIN_EMAIL`.
4. Negative: as the partner session from (1), in devtools call `/api/admin/use-cases` → **401**. Confirm no admin data is reachable.

- [ ] **Step 3: Independent verification agent (different model)**

Dispatch one verification agent on a different model (e.g. Sonnet) to independently confirm: (a) `dist/` has no `admin/` subtree and `vercel.json` has no `/admin*` routes; (b) `App.tsx` contains no `window.location.assign`; (c) the merged `api.ts` always sets `credentials:"include"` on authed calls; (d) the four browser-matrix outcomes above are consistent with the code paths; (e) no secret/SSO/`@databricks.com`-specific bypass leaked into client code. Reconcile any finding before declaring done.

- [ ] **Step 4: Update memory**

Update `~/.claude/projects/-Users-deep-basu/memory/project_partner_usecase_board.md`: the Vercel+Neon variant now uses **one unified role-gated app** (Clerk OTP for all; `@databricks.com` → admin + View-board switch; shared password = break-glass at `/admin/login`); the separate admin SPA is retired from the build.

---

## Notes for the implementer

- **Task order matters:** 1 (api) → 2 (role) → 3 (components) → 4 (nav) → 5 (App) → 6 (build) → 7 (backend test) → 8 (verify). Tasks 1-4 will leave the build red at their own boundary (documented in each); the build goes fully green at Task 5 Step 2.
- **Do not add npm deps or a frontend test framework** (global constraint). Typecheck via `npm run build` is the automated frontend gate.
- **If the portal theme's CSS variables differ** from `--paper/--coral/--line`, read the `:root` block of `portal-frontend/src/theme.css` and substitute the real token names in Task 3 Step 4.
- **Clerk dashboard redirect URLs:** if post-OTP lands on a 404 rather than `/` or `/admin`, the Clerk instance's after-sign-in URL points at a stale `/admin/*` path — fix it in the Clerk dashboard (config, not code), per the spec's Config note.
