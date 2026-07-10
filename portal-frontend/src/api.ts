// Typed client for the portal backend. Same-origin in prod (SPA served by
// FastAPI); dev uses Vite's proxy. credentials:"include" carries the session
// cookie set at signup.
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

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(r.status, detail.detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

const opts = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "include",
  headers: body ? { "content-type": "application/json" } : undefined,
  body: body ? JSON.stringify(body) : undefined,
});

export const api = {
  signup: (email: string, company: string, contact_name?: string) =>
    fetch(`${BASE}/api/signup`, opts("POST", { email, company, contact_name })).then(
      json<Partner>,
    ),

  me: async (): Promise<Partner | null> => {
    const r = await fetch(`${BASE}/api/me`, { credentials: "include" });
    return r.ok ? ((await r.json()) as Partner) : null;
  },

  listCases: () =>
    fetch(`${BASE}/api/use-cases`, { credentials: "include" }).then(json<UseCase[]>),

  getCase: (id: string) =>
    fetch(`${BASE}/api/use-cases/${id}`, { credentials: "include" }).then(json<UseCase>),

  respond: (id: string, approach: string) =>
    fetch(`${BASE}/api/use-cases/${id}/responses`, opts("POST", { approach })).then(
      json<{ id: string }>,
    ),
};

export { ApiError };
