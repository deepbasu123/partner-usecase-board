import { useState } from "react";
import { api, type AdminCase } from "../api";

export function CreateCaseForm({ onCreated }: { onCreated: (c: AdminCase) => void }) {
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
      const c = await api.createCase({
        title: title.trim(),
        description: description.trim(),
        industry: industry.trim() || undefined,
        region: region.trim() || undefined,
      });
      onCreated(c);
      setMsg({ ok: true, text: "Posted. Registered partners have been emailed." });
      setTitle("");
      setDescription("");
      setIndustry("");
      setRegion("");
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed to post." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Post a use case</h2>
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
        <button className="btn btn-primary" type="submit" disabled={busy || !title.trim() || !description.trim()}>
          {busy ? "Posting…" : "Post & notify partners"}
        </button>
      </form>
    </div>
  );
}
