import { useState, type FormEvent } from "react";
import { ApiError, type Api } from "../api";
import { DatabricksLogo } from "./Chrome";

// Break-glass password gate. Reachable at /admin/login WITHOUT a Clerk session,
// so it works during a Clerk outage and for a non-@databricks.com admin. On
// success the backend sets the admin cookie; onAuthed() re-probes the role.
export function AdminLogin({ api, onAuthed }: { api: () => Api; onAuthed: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api().adminLogin(password);
      onAuthed();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Incorrect password."
          : "Couldn't sign in. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">
          <DatabricksLogo />
          <div className="login-wordmark">Partner Board</div>
        </div>
        <h1 className="login-title">Admin sign in</h1>
        <p className="login-sub">Break-glass password for the Databricks team. Employees normally sign in with their @databricks.com email instead.</p>
        <label className="login-label" htmlFor="pw">Password</label>
        <input id="pw" className="login-input" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)} autoFocus
               autoComplete="current-password" placeholder="••••••••••" />
        {error && <div className="login-error">{error}</div>}
        <button className="login-btn" type="submit" disabled={busy || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
