import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";

// Shared-password gate for the admin cockpit (replaces Databricks SSO on
// Vercel). On success the backend sets the admin cookie and we call onAuthed().
export function AdminLogin({ onAuthed }: { onAuthed: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onAuthed();
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 401
          ? "Incorrect password."
          : "Couldn't sign in. Please try again.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">
          <svg viewBox="33 0 28.2 30.4" fill="none" aria-label="Databricks" width="34" height="34">
            <path
              d="M59.7279 12.5153L47.2039 19.6185L33.8814 12.0502L33.251 12.3884V17.885L47.2039 25.8339L59.7279 18.7306V21.648L47.2039 28.7513L33.8814 21.1829L33.251 21.5212V22.4514L47.2039 30.4002L61.1989 22.4514V16.9548L60.5685 16.6165L47.2039 24.1849L34.7219 17.0816V14.2065L47.2039 21.2675L61.1989 13.3186V7.9066L60.4844 7.52607L47.2039 15.0521L35.3943 8.32941L47.2039 1.64897L56.9541 7.14554L57.8367 6.68044V6.00394L47.2039 0L33.251 7.9066V8.75223L47.2039 16.7011L59.7279 9.59785V12.5153Z"
              fill="#FF3621"
            />
          </svg>
          <div className="login-wordmark">Partner Board</div>
        </div>
        <h1 className="login-title">Admin sign in</h1>
        <p className="login-sub">Enter the admin password to manage use cases and view partner responses.</p>

        <label className="login-label" htmlFor="pw">Password</label>
        <input
          id="pw"
          className="login-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete="current-password"
          placeholder="••••••••••"
        />

        {error && <div className="login-error">{error}</div>}

        <button className="login-btn" type="submit" disabled={busy || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
