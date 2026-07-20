import { useEffect, useState } from "react";
import type { Api, AdminCase, AdminResponse } from "../api";

export function AdminCases({ api }: { api: () => Api }) {
  const [cases, setCases] = useState<AdminCase[] | null>(null);

  useEffect(() => {
    api().listAllCases().then(setCases).catch(() => setCases([]));
  }, [api]);

  function onCreated(c: AdminCase) {
    setCases((prev) => [{ ...c, response_count: 0 }, ...(prev ?? [])]);
  }
  function onChanged(u: AdminCase) {
    setCases((prev) => (prev ?? []).map((c) => (c.id === u.id ? u : c)));
  }

  return (
    <div className="cols">
      <div>
        <CreateCaseForm api={api} onCreated={onCreated} />
      </div>
      <div>
        <p className="section-label">Posted use cases</p>
        {cases === null ? (
          <div className="center-state"><div className="spinner" />Loading…</div>
        ) : cases.length === 0 ? (
          <div className="center-state">No use cases yet. Post your first one on the left.</div>
        ) : (
          cases.map((c) => <CaseRow key={c.id} api={api} c={c} onChanged={onChanged} />)
        )}
      </div>
    </div>
  );
}

function CreateCaseForm({ api, onCreated }: { api: () => Api; onCreated: (c: AdminCase) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [industry, setIndustry] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const c = await api().createCase({
        title: title.trim(),
        description: description.trim(),
        industry: industry.trim() || undefined,
        region: region.trim() || undefined,
      });
      onCreated(c);
      setMsg({ ok: true, text: "Posted. Registered partners have been emailed." });
      setTitle(""); setDescription(""); setIndustry(""); setRegion("");
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed to post." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Post a use case</h2>
      <p className="card-hint">Registered partners are emailed when you post.</p>
      {msg && <div className={`notice ${msg.ok ? "notice-ok" : "notice-err"}`}>{msg.text}</div>}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="e.g. Workforce Management — ANZ" required />
        </div>
        <div className="field">
          <label htmlFor="desc">The ask</label>
          <textarea id="desc" value={description} onChange={(e) => setDescription(e.target.value)}
                    placeholder="What you need help with, context, and what a good partner looks like." required />
        </div>
        <div className="row2">
          <div className="field">
            <label htmlFor="industry">Industry (optional)</label>
            <input id="industry" value={industry} onChange={(e) => setIndustry(e.target.value)}
                   placeholder="e.g. Utilities" />
          </div>
          <div className="field">
            <label htmlFor="region">Region (optional)</label>
            <input id="region" value={region} onChange={(e) => setRegion(e.target.value)}
                   placeholder="e.g. ANZ" />
          </div>
        </div>
        <button className="btn btn-primary btn-block" type="submit"
                disabled={busy || !title.trim() || !description.trim()}>
          {busy ? "Posting…" : "Post & notify partners"}
        </button>
      </form>
    </div>
  );
}

function CaseRow({ api, c, onChanged }: { api: () => Api; c: AdminCase; onChanged: (c: AdminCase) => void }) {
  const [open, setOpen] = useState(false);
  const [responses, setResponses] = useState<AdminResponse[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggleResponses() {
    const next = !open;
    setOpen(next);
    if (next && responses === null) setResponses(await api().responsesFor(c.id));
  }
  async function toggleStatus() {
    setBusy(true);
    try {
      const u = await api().setCaseStatus(c.id, c.status === "open" ? "closed" : "open");
      onChanged({ ...c, status: u.status, closed_at: u.closed_at });
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
            {c.region ? `${c.region} · ` : ""}{c.industry ? `${c.industry} · ` : ""}posted by {c.posted_by}
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
                <div className="rhd"><b>{r.company}</b><a href={`mailto:${r.email}`}>{r.email}</a></div>
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
