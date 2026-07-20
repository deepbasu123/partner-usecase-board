import { useCallback, useEffect, useState } from "react";
import { useAuth, useUser } from "@clerk/react";
import { isDatabricksEmail } from "./auth";
import { makeApi } from "./api";

export type Role = "loading" | "partner" | "admin";

// Resolve the caller's role. Order (all fail-safe — ambiguity => not admin):
//   1. Clerk still loading                -> "loading"
//   2. signed-in @databricks.com email    -> "admin"  (email from Clerk)
//   3. else GET /api/admin/whoami == 200   -> "admin"  (break-glass cookie)
//   4. else                                -> "partner"
// A 4s fallback covers Clerk never loading (outage / blocked key) so the
// break-glass whoami probe still runs and /admin/login stays reachable.
export function useRole() {
  const { getToken, isSignedIn } = useAuth();
  const { user, isLoaded } = useUser();
  const [role, setRole] = useState<Role>("loading");
  const [email, setEmail] = useState<string | null>(null);
  const [clerkTimedOut, setClerkTimedOut] = useState(false);

  const dbxEmail = isDatabricksEmail(user?.primaryEmailAddress?.emailAddress);

  useEffect(() => {
    if (isLoaded) return;
    const t = setTimeout(() => setClerkTimedOut(true), 4000);
    return () => clearTimeout(t);
  }, [isLoaded]);

  const resolve = useCallback(async () => {
    if (!isLoaded && !clerkTimedOut) {
      setRole("loading");
      return;
    }
    if (isLoaded && isSignedIn && dbxEmail) {
      setRole("admin");
      setEmail(user?.primaryEmailAddress?.emailAddress ?? null);
      return;
    }
    // Probe the break-glass cookie (and, harmlessly, a dbx token if present).
    try {
      const who = await makeApi(() => getToken()).adminWhoami();
      setRole("admin");
      setEmail(who.email);
    } catch {
      setRole("partner");
      setEmail(null);
    }
  }, [isLoaded, clerkTimedOut, isSignedIn, dbxEmail, user, getToken]);

  useEffect(() => {
    void resolve();
  }, [resolve]);

  return { role, email, refresh: () => void resolve() };
}
