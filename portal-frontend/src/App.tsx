import { useEffect, useState, useCallback } from "react";
import { Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import { useAuth, useUser } from "@clerk/react";
import { makeApi, type Partner } from "./api";
import { useRole } from "./role";
import { Rail } from "./components/Chrome";
import { BoardPage } from "./components/BoardPage";
import { SignInPage } from "./components/SignInPage";
import { Onboarding } from "./components/Onboarding";
import { CaseDetail } from "./components/CaseDetail";
import { AdminCases } from "./components/AdminCases";
import { AdminPartners } from "./components/AdminPartners";
import { AdminLogin } from "./components/AdminLogin";

export default function App() {
  const { getToken, isSignedIn } = useAuth();
  const { isLoaded } = useUser();
  const { role, email: adminEmail, refresh } = useRole();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [partner, setPartner] = useState<Partner | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  const api = useCallback(() => makeApi(() => getToken()), [getToken]);

  // Partner profile lookup runs for partners only (not admins, not while loading).
  useEffect(() => {
    if (role !== "partner" || !isLoaded || !isSignedIn) {
      setPartner(null);
      setNeedsOnboarding(false);
      return;
    }
    api().me().then((m) => {
      if (m && "onboarding_required" in m) { setNeedsOnboarding(true); setPartner(null); }
      else if (m) { setPartner(m); setNeedsOnboarding(false); }
    }).catch(() => { /* transient: keep state; board is public anyway */ });
  }, [role, isLoaded, isSignedIn, api]);

  // Onboarding redirect — effect, never during render.
  useEffect(() => {
    if (needsOnboarding && pathname !== "/onboarding") navigate("/onboarding");
  }, [needsOnboarding, pathname, navigate]);

  if (role === "loading") {
    return <div className="login-shell"><div className="spinner" /></div>;
  }

  return (
    <div className="app">
      <Rail role={role} partner={partner} adminEmail={adminEmail} />
      <div className="content">
        <Routes>
          <Route path="/" element={<BoardPage partner={partner} api={api} />} />
          <Route path="/signin/*" element={<SignInPage />} />
          <Route path="/case/:id" element={<CaseDetail partner={partner} api={api} />} />
          <Route
            path="/onboarding"
            element={<Onboarding api={api} onDone={(p) => { setPartner(p); setNeedsOnboarding(false); }} />}
          />
          {/* Break-glass login is always reachable (even with no Clerk session). */}
          <Route path="/admin/login" element={<AdminLogin api={api} onAuthed={refresh} />} />
          {/* Admin cockpit — gated in the UI by role; the backend gates the data. */}
          <Route
            path="/admin"
            element={role === "admin" ? <AdminCases api={api} /> : <Navigate to="/admin/login" replace />}
          />
          <Route
            path="/admin/partners"
            element={role === "admin" ? <AdminPartners api={api} /> : <Navigate to="/admin/login" replace />}
          />
        </Routes>
      </div>
    </div>
  );
}
