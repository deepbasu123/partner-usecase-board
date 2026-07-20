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
