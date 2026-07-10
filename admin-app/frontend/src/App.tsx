import { useEffect, useState } from "react";
import { api, type AdminCase, type AdminPartner } from "./api";
import { CreateCaseForm } from "./components/CreateCaseForm";
import { CaseRow } from "./components/CaseRow";

export default function App() {
  const [who, setWho] = useState<string>("");
  const [tab, setTab] = useState<"cases" | "partners">("cases");
  const [cases, setCases] = useState<AdminCase[] | null>(null);
  const [partners, setPartners] = useState<AdminPartner[] | null>(null);

  useEffect(() => {
    api.whoami().then((w) => setWho(w.email)).catch(() => setWho(""));
    api.listCases().then(setCases).catch(() => setCases([]));
  }, []);

  useEffect(() => {
    if (tab === "partners" && partners === null) {
      api.listPartners().then(setPartners).catch(() => setPartners([]));
    }
  }, [tab, partners]);

  function onCreated(c: AdminCase) {
    setCases((prev) => [{ ...c, response_count: 0 }, ...(prev ?? [])]);
  }

  function onChanged(updated: AdminCase) {
    setCases((prev) => (prev ?? []).map((c) => (c.id === updated.id ? updated : c)));
  }

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="brand-mark">Databricks · Partners</span>
          <span className="brand-name">Admin</span>
        </div>
        <div className="who">{who ? <>Signed in as <b>{who}</b></> : "Databricks staff only"}</div>
      </header>

      <div className="tabs">
        <button className={`tab ${tab === "cases" ? "active" : ""}`} onClick={() => setTab("cases")}>
          Use cases
        </button>
        <button className={`tab ${tab === "partners" ? "active" : ""}`} onClick={() => setTab("partners")}>
          Partners
        </button>
      </div>

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
          <p className="section-label">Registered partners</p>
          {partners === null ? (
            <div className="center-state"><div className="spinner" />Loading…</div>
          ) : partners.length === 0 ? (
            <div className="center-state">No partners have signed up yet.</div>
          ) : (
            <table className="ptable">
              <thead>
                <tr><th>Company</th><th>Email</th><th>Contact</th><th>Joined</th></tr>
              </thead>
              <tbody>
                {partners.map((p) => (
                  <tr key={p.id}>
                    <td><b>{p.company}</b></td>
                    <td><a href={`mailto:${p.email}`} style={{ color: "var(--accent-ink)", textDecoration: "none" }}>{p.email}</a></td>
                    <td>{p.contact_name ?? "—"}</td>
                    <td className="muted">{new Date(p.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
