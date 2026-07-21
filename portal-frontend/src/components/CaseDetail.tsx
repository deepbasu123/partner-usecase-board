import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/react";
import { ApiError, type Api, type UseCase, type Partner } from "../api";
import { TopBar, Loading, ErrorState } from "./Chrome";

/** Turn a poster email into a display name: "deep.basu@databricks.com" → "Deep Basu".
 *  Falls back to the raw local-part if it doesn't split into name-like tokens. */
function posterName(email: string): string {
  const local = email.split("@")[0] || email;
  const parts = local.split(/[.\-_]+/).filter(Boolean);
  if (!parts.length) return local;
  return parts.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
}

export function CaseDetail({ partner, api }: { partner: Partner | null; api: () => Api }) {
  const { id = "" } = useParams();
  const { isSignedIn } = useAuth();
  const nav = useNavigate();
  const [uc, setUc] = useState<UseCase | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api()
      .getCase(id)
      .then(setUc)
      .catch((e) =>
        setError(e instanceof ApiError && e.status === 404 ? "not-found" : e.message),
      );
  }, [id, api]);

  return (
    <>
      <TopBar title="Use case" sub={uc?.title} partner={partner} />
      <main className="main">
        <div className="main-wrap">
          <Link to="/" className="back-link">
            ← Back to the board
          </Link>

          {error === "not-found" ? (
            <ErrorState message="This use case doesn't exist or has been closed." />
          ) : error ? (
            <ErrorState message={error} />
          ) : !uc ? (
            <Loading label="Loading use case" />
          ) : (
            <>
              <div className="detail-head">
                <div className="tags">
                  <span className="pill pill-open">Open</span>
                  {uc.region && <span className="tag">{uc.region}</span>}
                  {uc.industry && <span className="tag">{uc.industry}</span>}
                </div>
                <h1>{uc.title}</h1>
                {/* Poster (a @databricks.com email) is shown only to signed-in
                    users - the case detail endpoint is public, so we don't leak
                    the internal email to anonymous visitors with a case link. */}
                {isSignedIn && uc.posted_by && (
                  <div className="posted-by">
                    Posted by <b>{posterName(uc.posted_by)}</b>, Databricks
                    {" · "}
                    <a href={`mailto:${uc.posted_by}`}>{uc.posted_by}</a>
                  </div>
                )}
              </div>

              <div className="detail-grid">
                <div className="detail-body">{uc.description}</div>
                <div>
                  {partner ? (
                    <EoiForm caseId={uc.id} company={partner.company} api={api} />
                  ) : (
                    <div className="card">
                      <h3 style={{ marginBottom: 10 }}>Interested?</h3>
                      <p className="muted" style={{ marginBottom: 18 }}>
                        Join the board to tell us how you&apos;d approach this. It takes one step
                        and no password.
                      </p>
                      <button
                        className="btn btn-primary btn-block"
                        onClick={() => nav("/signin")}
                      >
                        Sign in to respond
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}

function EoiForm({
  caseId,
  company,
  api,
}: {
  caseId: string;
  company: string;
  api: () => Api;
}) {
  const [approach, setApproach] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api().respond(caseId, approach.trim());
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("You've already responded to this use case.");
      } else {
        setError(err instanceof Error ? err.message : "Could not submit. Please try again.");
      }
      setBusy(false);
    }
  }

  if (done)
    return (
      <div className="card">
        <div className="notice notice-ok" role="status">
          Thanks, your response is in.
        </div>
        <p className="muted">
          The Databricks team will be in touch with <b>{company}</b> if it&apos;s a fit. You can
          respond to other open use cases from the board.
        </p>
      </div>
    );

  return (
    <form className="card" onSubmit={submit}>
      <h3 style={{ marginBottom: 6 }}>Raise your hand</h3>
      <p className="muted" style={{ marginBottom: 18, fontSize: 14 }}>
        Responding as <b>{company}</b>. Only the Databricks team sees this.
      </p>
      {error && (
        <div className="notice notice-err" role="alert">
          {error}
        </div>
      )}
      <div className="field">
        <label htmlFor="approach">How would you approach this?</label>
        <textarea
          id="approach"
          value={approach}
          onChange={(e) => setApproach(e.target.value)}
          placeholder="Relevant experience, accelerators, team, rough timeline…"
          required
        />
      </div>
      <button
        className="btn btn-primary btn-block"
        type="submit"
        disabled={busy || !approach.trim()}
      >
        {busy ? "Submitting…" : "Submit expression of interest"}
      </button>
    </form>
  );
}
