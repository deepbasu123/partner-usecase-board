import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, type Partner } from "../api";

export function SignupForm({ onSignedIn }: { onSignedIn: (p: Partner) => void }) {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const p = await api.signup(email.trim(), company.trim(), contact.trim() || undefined);
      onSignedIn(p);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed. Please try again.");
      setBusy(false);
    }
  }

  return (
    <>
      <Link to="/" className="back-link">
        ← Back to the board
      </Link>
      <section className="hero" style={{ paddingBottom: 18 }}>
        <p className="eyebrow">Join the board</p>
        <h1>One step. No password.</h1>
        <p>
          Tell us who you are and we&apos;ll email you when new use cases are posted. You can
          respond to any open brief once you&apos;re in.
        </p>
      </section>

      <form className="panel" onSubmit={submit} noValidate>
        {error && (
          <div className="notice notice-err" role="alert">
            {error}
          </div>
        )}
        <div className="field">
          <label htmlFor="company">Company</label>
          <input
            id="company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Your firm's name"
            required
            autoComplete="organization"
          />
        </div>
        <div className="field">
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@yourfirm.com"
            required
            autoComplete="email"
          />
          <span className="hint">We&apos;ll send new use cases and updates here.</span>
        </div>
        <div className="field">
          <label htmlFor="contact">Your name (optional)</label>
          <input
            id="contact"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="First and last name"
            autoComplete="name"
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy || !email || !company}>
          {busy ? "Joining…" : "Join the board"}
        </button>
      </form>
    </>
  );
}
