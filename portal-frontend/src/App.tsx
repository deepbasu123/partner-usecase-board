import { useEffect, useState, useCallback } from "react";
import { Routes, Route } from "react-router-dom";
import { useAuth, useUser } from "@clerk/react";
import { makeApi, type Partner } from "./api";
import { Rail } from "./components/Chrome";
import { BoardPage } from "./components/BoardPage";
import { SignInPage } from "./components/SignInPage";
import { Onboarding } from "./components/Onboarding";
import { CaseDetail } from "./components/CaseDetail";

export default function App() {
  const { getToken, isSignedIn } = useAuth();
  const { isLoaded } = useUser();
  const [partner, setPartner] = useState<Partner | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  const api = useCallback(() => makeApi(() => getToken()), [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      setPartner(null);
      return;
    }
    api()
      .me()
      .then((m) => {
        if (m && "onboarding_required" in m) {
          setNeedsOnboarding(true);
          setPartner(null);
        } else if (m) {
          setPartner(m);
          setNeedsOnboarding(false);
        }
      });
  }, [isLoaded, isSignedIn, api]);

  return (
    <div className="app">
      <Rail partner={partner} />
      <div className="content">
        <Routes>
          <Route path="/" element={<BoardPage partner={partner} api={api} />} />
          <Route path="/signin/*" element={<SignInPage />} />
          <Route
            path="/onboarding"
            element={
              <Onboarding
                api={api}
                onDone={(p) => {
                  setPartner(p);
                  setNeedsOnboarding(false);
                }}
              />
            }
          />
          <Route path="/case/:id" element={<CaseDetail partner={partner} api={api} />} />
        </Routes>
      </div>
      {needsOnboarding &&
        window.location.pathname !== "/onboarding" &&
        (window.location.href = "/onboarding")}
    </div>
  );
}
