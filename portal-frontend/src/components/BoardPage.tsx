import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Api, Partner, UseCase } from "../api";
import { UseCaseCard } from "./UseCaseCard";
import { TopBar, Loading, EmptyState, ErrorState, DatabricksLogo, BriefcaseIcon } from "./Chrome";

export function BoardPage({ partner, api }: { partner: Partner | null; api: () => Api }) {
  const [cases, setCases] = useState<UseCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api()
      .listCases()
      .then(setCases)
      .catch((e) => setError(e.message ?? "Could not load the board"));
  }, [api]);

  const count = cases?.length ?? 0;
  const signedIn = !!partner;

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
          <section className="chooser" aria-label="Choose how to continue">
            <p className="section-label">Who are you?</p>
            <div className="chooser-cards">
              {/* /admin is a separate SPA at its own base path → full navigation. */}
              <a className="path-card" href="/admin">
                <span className="path-icon dbx" aria-hidden>
                  <DatabricksLogo />
                </span>
                <h3>Databricks user</h3>
                <p>Post opportunities and review the partners who raise their hand.</p>
                <span className="path-cta">Go to the admin portal</span>
              </a>

              <Link className="path-card" to={signedIn ? "/" : "/signin"}>
                <span className="path-icon partner" aria-hidden>
                  <BriefcaseIcon />
                </span>
                <h3>Partner</h3>
                <p>
                  {signedIn
                    ? "You're signed in — browse the open briefs below and raise your hand."
                    : "Sign in with your email, then browse open briefs and raise your hand."}
                </p>
                <span className="path-cta">
                  {signedIn ? "Browse the board" : "Sign in as a partner"}
                </span>
              </Link>
            </div>
          </section>

          <p className="section-label">Posted use cases</p>
          {error ? (
            <ErrorState message={error} />
          ) : !cases ? (
            <Loading label="Loading the board" />
          ) : cases.length === 0 ? (
            <EmptyState
              title="No open use cases right now"
              hint="Check back soon — new briefs are posted as they come up."
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
