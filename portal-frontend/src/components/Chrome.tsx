import { Link } from "react-router-dom";
import type { Partner } from "../api";

/** Masthead shown on every page. Shows who's signed in, if anyone. */
export function Masthead({ partner }: { partner: Partner | null }) {
  return (
    <header className="masthead">
      <Link to="/" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
        <span className="brand-mark">Databricks · Partners</span>
        <span className="brand-name">Use-Case Board</span>
      </Link>
      <div className="who">
        {partner ? (
          <>
            Signed in as <b>{partner.company}</b>
          </>
        ) : (
          <span className="muted">Open to GT partners</span>
        )}
      </div>
    </header>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="center-state">
      <div className="spinner" aria-hidden />
      <p>{label}…</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="center-state">
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      {hint && <p className="muted">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="center-state">
      <h3 style={{ marginBottom: 8 }}>Something went wrong</h3>
      <p className="muted">{message}</p>
    </div>
  );
}
