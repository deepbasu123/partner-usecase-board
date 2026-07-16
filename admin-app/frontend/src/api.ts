// Admin API client. Same-origin (SPA served by Vercel; the FastAPI function
// handles /api). Access is gated by a shared-password admin cookie, so every
// call sends credentials. A 401 means "not logged in" → the app shows login.
const BASE = import.meta.env.VITE_API_BASE ?? "";

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
    const d = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(r.status, d.detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

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

export const api = {
  login: (password: string) =>
    fetch(`${BASE}/api/admin/login`, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    }).then(json<{ ok: boolean }>),  // login stays as-is (no token needed)

  whoami: async () =>
    fetch(`${BASE}/api/admin/whoami`, await authInit()).then(json<{ email: string }>),

  listCases: async () =>
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

  setStatus: async (id: string, status: "open" | "closed") =>
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
