import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Api, Partner } from "../api";
import { TopBar } from "./Chrome";

export function Onboarding({ api, onDone }: { api: () => Api; onDone: (p: Partner) => void }) {
  const nav = useNavigate();
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await api().onboarding(company.trim());
      onDone(p);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <>
      <TopBar title="One more thing" sub="Tell us who you're with" partner={null} />
      <main className="main">
        <div className="main-wrap" style={{ maxWidth: 460 }}>
          <form className="card" onSubmit={submit} noValidate>
            {error && (
              <div className="notice notice-err" role="alert">
                {error}
              </div>
            )}
            <div className="field">
              <label htmlFor="company">What firm are you with?</label>
              <input
                id="company"
                value={company}
                autoComplete="organization"
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Your firm's name"
                required
              />
            </div>
            <button
              className="btn btn-primary btn-block"
              type="submit"
              disabled={busy || !company.trim()}
            >
              {busy ? "Saving…" : "Continue"}
            </button>
          </form>
        </div>
      </main>
    </>
  );
}
