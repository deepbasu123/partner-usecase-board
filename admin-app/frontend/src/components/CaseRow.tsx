import { useState } from "react";
import { api, type AdminCase, type AdminResponse } from "../api";

export function CaseRow({ c, onChanged }: { c: AdminCase; onChanged: (c: AdminCase) => void }) {
  const [open, setOpen] = useState(false);
  const [responses, setResponses] = useState<AdminResponse[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggleResponses() {
    const next = !open;
    setOpen(next);
    if (next && responses === null) {
      setResponses(await api.responsesFor(c.id));
    }
  }

  async function toggleStatus() {
    setBusy(true);
    try {
      const updated = await api.setStatus(c.id, c.status === "open" ? "closed" : "open");
      onChanged({ ...c, status: updated.status, closed_at: updated.closed_at });
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
            {c.region ? `${c.region} · ` : ""}
            {c.industry ? `${c.industry} · ` : ""}
            posted by {c.posted_by}
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
                <div className="rhd">
                  <b>{r.company}</b>
                  <a href={`mailto:${r.email}`}>{r.email}</a>
                </div>
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
