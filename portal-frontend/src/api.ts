// Typed client for the portal backend. Same-origin in prod (SPA served by
// FastAPI); dev uses Vite's proxy. Auth is via Clerk Bearer token.
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
    throw new ApiError(r.status, (detail as { detail?: string }).detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

// getToken comes from Clerk's useAuth(); null token => no auth header (public reads).
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
