import { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import { api, type Partner } from "./api";
import { Masthead } from "./components/Chrome";
import { BoardPage } from "./components/BoardPage";
import { SignupForm } from "./components/SignupForm";
import { CaseDetail } from "./components/CaseDetail";

export default function App() {
  const [partner, setPartner] = useState<Partner | null>(null);

  // Restore session on load. /api/me returns the full partner (id, email,
  // company) so the masthead survives a refresh. The board and case pages
  // fetch their own data and don't wait on this — an unauthenticated 401 here
  // is expected and must not block the public content from rendering.
  useEffect(() => {
    api.me().then(setPartner);
  }, []);

  return (
    <div className="shell">
      <Masthead partner={partner} />
      <Routes>
        <Route path="/" element={<BoardPage signedIn={!!partner} />} />
        <Route path="/signup" element={<SignupForm onSignedIn={setPartner} />} />
        <Route path="/case/:id" element={<CaseDetail partner={partner} />} />
      </Routes>
    </div>
  );
}
