import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type UseCase } from "../api";
import { UseCaseCard } from "./UseCaseCard";
import { Loading, EmptyState, ErrorState } from "./Chrome";

export function BoardPage({ signedIn }: { signedIn: boolean }) {
  const [cases, setCases] = useState<UseCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listCases()
      .then(setCases)
      .catch((e) => setError(e.message ?? "Could not load the board"));
  }, []);

  return (
    <>
      <section className="hero">
        <p className="eyebrow">Partner opportunities</p>
        <h1>Use cases where we&apos;re looking for partner support.</h1>
        <p>
          These are real opportunities the Databricks field team wants help delivering. Browse
          the open briefs below and raise your hand on any you can take on.
        </p>
        {!signedIn && (
          <p style={{ marginTop: 22 }}>
            <Link to="/signup" className="btn btn-primary" style={{ textDecoration: "none" }}>
              Join as a partner
            </Link>
          </p>
        )}
      </section>

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
        <div className="board stagger">
          {cases.map((uc) => (
            <UseCaseCard key={uc.id} uc={uc} />
          ))}
        </div>
      )}
    </>
  );
}
