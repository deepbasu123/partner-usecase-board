import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@clerk/react";
import type { Api, Partner, UseCase } from "../api";
import { UseCaseCard } from "./UseCaseCard";
import { TopBar, Loading, EmptyState, ErrorState, LakeAllianceMark } from "./Chrome";

export function BoardPage({ partner, api }: { partner: Partner | null; api: () => Api }) {
  const { isSignedIn } = useAuth();
  const [cases, setCases] = useState<UseCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api()
      .listCases()
      .then(setCases)
      .catch((e) => setError(e.message ?? "Could not load the board"));
  }, [api]);

  const count = cases?.length ?? 0;

  return (
    <>
      <TopBar
        title="Open use cases"
        sub={
          cases
            ? `${count} open · opportunities where the Databricks field team wants partner help`
            : "opportunities where the Databricks field team wants partner help"
        }
        partner={partner}
      />
      <main className="main">
        <div className="main-wrap">
          {/* Signed-out visitors get one sign-in entry. Sign-in is unified: the
              same email box routes @databricks.com employees to admin and
              everyone else to the partner board, so a single button is enough. */}
          {!isSignedIn && (
            <section className="signin-invite" aria-label="Sign in">
              <div className="signin-invite-mark" aria-hidden>
                <LakeAllianceMark />
              </div>
              <h2 className="signin-invite-title">
                Where Databricks and its partners <em>meet</em>
              </h2>
              <p className="signin-invite-sub">
                Sign in to browse open use cases and raise your hand. We email you a
                code, so there's no password to remember.
              </p>
              <Link className="btn btn-primary signin-invite-cta" to="/signin">
                Sign in
              </Link>
              <p className="signin-invite-note">
                <span className="dot" aria-hidden />
                <span className="signin-invite-note-txt">
                  Databricks employees: sign in with your <b>@databricks.com</b> email
                  to post and manage use cases.
                </span>
              </p>
            </section>
          )}

          <p className="section-label">Posted use cases</p>
          {error ? (
            <ErrorState message={error} />
          ) : !cases ? (
            <Loading label="Loading the board" />
          ) : cases.length === 0 ? (
            <EmptyState
              title="No open use cases right now"
              hint="Check back soon. New briefs are posted as they come up."
            />
          ) : (
            <div className="board">
              {cases.map((uc) => (
                <UseCaseCard key={uc.id} uc={uc} />
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
