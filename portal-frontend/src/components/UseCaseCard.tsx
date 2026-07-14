import { Link } from "react-router-dom";
import type { UseCase } from "../api";

function excerpt(text: string, n = 150) {
  return text.length > n ? text.slice(0, n).trimEnd() + "…" : text;
}

export function UseCaseCard({ uc }: { uc: UseCase }) {
  const meta = [uc.region, uc.industry].filter(Boolean).join(" · ");
  return (
    <Link to={`/case/${uc.id}`} className="uc-card">
      <div className="tags">
        <span className="pill pill-open">Open</span>
      </div>
      <h3>{uc.title}</h3>
      {meta && <div className="meta">{meta}</div>}
      <p className="excerpt">{excerpt(uc.description)}</p>
      <div className="foot">
        <span className="respond-hint">View &amp; respond</span>
      </div>
    </Link>
  );
}
