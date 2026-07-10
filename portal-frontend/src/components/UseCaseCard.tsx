import { Link } from "react-router-dom";
import type { UseCase } from "../api";

function excerpt(text: string, n = 150) {
  return text.length > n ? text.slice(0, n).trimEnd() + "…" : text;
}

export function UseCaseCard({ uc }: { uc: UseCase }) {
  return (
    <Link to={`/case/${uc.id}`} className="card">
      <div className="tags">
        {uc.region && <span className="tag">{uc.region}</span>}
        {uc.industry && <span className="tag">{uc.industry}</span>}
      </div>
      <h3>{uc.title}</h3>
      <p className="excerpt">{excerpt(uc.description)}</p>
      <div className="card-foot">
        <span className="respond-hint">View &amp; respond</span>
      </div>
    </Link>
  );
}
