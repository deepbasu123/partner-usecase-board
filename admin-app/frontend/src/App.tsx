// DEPRECATED (2026-07-20): the admin cockpit now lives inside portal-frontend/
// as role-gated routes. This file is no longer built or deployed on
// vercel-neon-deploy. Kept only for the Databricks-App variant referenced by main.

import { useEffect, useState } from "react";
import { useAuth, useUser } from "@clerk/react";
import { api, setAdminTokenGetter, ApiError, type AdminCase, type AdminPartner } from "./api";
import { CreateCaseForm } from "./components/CreateCaseForm";
import { CaseRow } from "./components/CaseRow";
import { AdminLogin } from "./components/AdminLogin";

type Tab = "cases" | "partners";
// null = still checking session; false = show login; true = authed.
type Auth = boolean | null;

function initials(email: string) {
  const name = email.split("@")[0] || "";
  const parts = name.split(/[.\-_]/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "DB";
}

export default function App() {
  const { getToken } = useAuth();
  const { isLoaded: clerkLoaded } = useUser();
  setAdminTokenGetter(() => getToken());  // idempotent; safe to call each render

  const [authed, setAuthed] = useState<Auth>(null);
  const [who, setWho] = useState<string>("");
  const [tab, setTab] = useState<Tab>("cases");
  const [cases, setCases] = useState<AdminCase[] | null>(null);
  const [partners, setPartners] = useState<AdminPartner[] | null>(null);

  // A 401 from any admin call means the session lapsed → return to login.
  function onError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) setAuthed(false);
  }

  // Probe the session: whoami succeeds with a valid admin cookie OR a
  // @databricks.com Clerk Bearer token. Run once Clerk is loaded (so the token
  // is available) and again right after a successful password login.
  function probe() {
    setAuthed(null);
    api.whoami()
      .then((w) => { setWho(w.email); setAuthed(true); })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) setAuthed(false);
        else { setWho(""); setAuthed(true); }  // non-auth error: don't lock out
      });
  }

  useEffect(() => { if (clerkLoaded) probe(); }, [clerkLoaded]);

  // Fallback: if Clerk never finishes loading (outage, blocked/invalid key,
  // network to Clerk blocked), don't spin forever — probe anyway after a short
  // wait so the shared-password login stays reachable. With no Clerk token the
  // probe's whoami 401s and AdminLogin renders, exactly as a signed-out visitor.
  useEffect(() => {
    if (clerkLoaded) return;
    const t = setTimeout(() => { if (!clerkLoaded) probe(); }, 4000);
    return () => clearTimeout(t);
  }, [clerkLoaded]);

  // Load cases once authenticated.
  useEffect(() => {
    if (authed !== true) return;
    api.listCases().then(setCases).catch((err) => { onError(err); setCases([]); });
  }, [authed]);

  useEffect(() => {
    if (authed === true && tab === "partners" && partners === null) {
      api.listPartners().then(setPartners).catch((err) => { onError(err); setPartners([]); });
    }
  }, [authed, tab, partners]);

  if (authed === null) {
    return <div className="login-shell"><div className="spinner" /></div>;
  }
  if (authed === false) {
    return <AdminLogin onAuthed={probe} />;
  }

  function onCreated(c: AdminCase) {
    setCases((prev) => [{ ...c, response_count: 0 }, ...(prev ?? [])]);
  }
  function onChanged(updated: AdminCase) {
    setCases((prev) => (prev ?? []).map((c) => (c.id === updated.id ? updated : c)));
  }

  const openCount = cases?.filter((c) => c.status === "open").length ?? 0;

  return (
    <div className="app">
      <nav className="rail">
        <div className="logo">
          <DatabricksLogo />
          <div className="wordmark">Partner Board</div>
        </div>

        <div className="navlabel">Manage</div>
        <button className={`navitem ${tab === "cases" ? "active" : ""}`} onClick={() => setTab("cases")}>
          <BoardIcon /> Use cases
        </button>
        <button className={`navitem ${tab === "partners" ? "active" : ""}`} onClick={() => setTab("partners")}>
          <PeopleIcon /> Partners
        </button>

        <div className="spacer" />
      </nav>

      <div className="content">
        <header className="topbar">
          <div>
            <h1>{tab === "cases" ? "Use cases" : "Registered partners"}</h1>
            <div className="sub">
              {tab === "cases"
                ? `${openCount} open · post opportunities for GT partners`
                : "Partners who have signed up to the board"}
            </div>
          </div>
          <div className="who-chip" title={who || undefined}>
            <span className="avatar">{who ? initials(who) : "DB"}</span>
            <span className="who-txt">{who || "Not signed in"}</span>
          </div>
        </header>

        <main className="main">
          <div className="main-wrap">
            {tab === "cases" ? (
              <div className="cols">
                <div>
                  <CreateCaseForm onCreated={onCreated} />
                </div>
                <div>
                  <p className="section-label">Posted use cases</p>
                  {cases === null ? (
                    <div className="center-state"><div className="spinner" />Loading…</div>
                  ) : cases.length === 0 ? (
                    <div className="center-state">No use cases yet. Post your first one on the left.</div>
                  ) : (
                    cases.map((c) => <CaseRow key={c.id} c={c} onChanged={onChanged} />)
                  )}
                </div>
              </div>
            ) : (
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
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function DatabricksLogo() {
  // Official Databricks symbol mark (from databricks.com nav logo SVG).
  // viewBox cropped to the glyph's bounds within the source 96x54 artwork.
  return (
    <svg className="dbx-logo" viewBox="33 0 28.2 30.4" fill="none" aria-label="Databricks">
      <path
        d="M59.7279 12.5153L47.2039 19.6185L33.8814 12.0502L33.251 12.3884V17.885L47.2039 25.8339L59.7279 18.7306V21.648L47.2039 28.7513L33.8814 21.1829L33.251 21.5212V22.4514L47.2039 30.4002L61.1989 22.4514V16.9548L60.5685 16.6165L47.2039 24.1849L34.7219 17.0816V14.2065L47.2039 21.2675L61.1989 13.3186V7.9066L60.4844 7.52607L47.2039 15.0521L35.3943 8.32941L47.2039 1.64897L56.9541 7.14554L57.8367 6.68044V6.00394L47.2039 0L33.251 7.9066V8.75223L47.2039 16.7011L59.7279 9.59785V12.5153Z"
        fill="#FF3621"
      />
    </svg>
  );
}

function BoardIcon() {
  return (
    <svg className="ico" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="2.5" y="3" width="15" height="14" rx="2" />
      <path d="M2.5 8h15M8 8v9" />
    </svg>
  );
}
function PeopleIcon() {
  return (
    <svg className="ico" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="7.5" cy="7" r="2.8" />
      <path d="M2.5 16c0-2.8 2.2-4.5 5-4.5s5 1.7 5 4.5" />
      <path d="M13.5 5.2a2.6 2.6 0 010 4.6M14.5 15.8c0-2 .2-3.4-1.2-4.6" />
    </svg>
  );
}
