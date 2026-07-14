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

const cred: RequestInit = { credentials: "include" };

export const api = {
  login: (password: string) =>
    fetch(`${BASE}/api/admin/login`, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    }).then(json<{ ok: boolean }>),

  whoami: () =>
    fetch(`${BASE}/api/admin/whoami`, cred).then(json<{ email: string }>),

  listCases: () =>
    fetch(`${BASE}/api/admin/use-cases`, cred).then(json<AdminCase[]>),

  createCase: (body: {
    title: string;
    description: string;
    industry?: string;
    region?: string;
  }) =>
    fetch(`${BASE}/api/admin/use-cases`, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<AdminCase>),

  setStatus: (id: string, status: "open" | "closed") =>
    fetch(`${BASE}/api/admin/use-cases/${id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    }).then(json<AdminCase>),

  responsesFor: (id: string) =>
    fetch(`${BASE}/api/admin/use-cases/${id}/responses`, cred).then(json<AdminResponse[]>),

  listPartners: () =>
    fetch(`${BASE}/api/admin/partners`, cred).then(json<AdminPartner[]>),
};
