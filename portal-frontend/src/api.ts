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
