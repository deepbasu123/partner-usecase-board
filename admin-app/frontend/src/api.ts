// Admin API client. Same-origin (SPA served by the FastAPI app in prod; Vite
// proxy in dev). No credentials handling needed — the Databricks App platform
// gates access via workspace SSO.
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

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const d = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(d.detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

export const api = {
  whoami: () =>
    fetch(`${BASE}/api/admin/whoami`).then(json<{ email: string }>),

  listCases: () =>
    fetch(`${BASE}/api/admin/use-cases`).then(json<AdminCase[]>),

  createCase: (body: {
    title: string;
    description: string;
    industry?: string;
    region?: string;
  }) =>
    fetch(`${BASE}/api/admin/use-cases`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<AdminCase>),

  setStatus: (id: string, status: "open" | "closed") =>
    fetch(`${BASE}/api/admin/use-cases/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    }).then(json<AdminCase>),

  responsesFor: (id: string) =>
    fetch(`${BASE}/api/admin/use-cases/${id}/responses`).then(json<AdminResponse[]>),

  listPartners: () =>
    fetch(`${BASE}/api/admin/partners`).then(json<AdminPartner[]>),
};
