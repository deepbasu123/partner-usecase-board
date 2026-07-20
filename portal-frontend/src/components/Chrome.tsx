import { Link, useLocation } from "react-router-dom";
import { Show, UserButton } from "@clerk/react";
import type { Partner } from "../api";

/** Official Databricks symbol mark (from databricks.com nav logo SVG). */
export function DatabricksLogo() {
  return (
    <svg className="dbx-logo" viewBox="33 0 28.2 30.4" fill="none" aria-label="Databricks">
      <path
        d="M59.7279 12.5153L47.2039 19.6185L33.8814 12.0502L33.251 12.3884V17.885L47.2039 25.8339L59.7279 18.7306V21.648L47.2039 28.7513L33.8814 21.1829L33.251 21.5212V22.4514L47.2039 30.4002L61.1989 22.4514V16.9548L60.5685 16.6165L47.2039 24.1849L34.7219 17.0816V14.2065L47.2039 21.2675L61.1989 13.3186V7.9066L60.4844 7.52607L47.2039 15.0521L35.3943 8.32941L47.2039 1.64897L56.9541 7.14554L57.8367 6.68044V6.00394L47.2039 0L33.251 7.9066V8.75223L47.2039 16.7011L59.7279 9.59785V12.5153Z"
        fill="#FF3621"
      />
    </svg>
  );
}

/** Professional briefcase mark for the Partner chooser card. */
export function BriefcaseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4h5A1.5 1.5 0 0 1 16 5.5V7" />
      <path d="M3 12h18" />
      <path d="M12 12v2" />
    </svg>
  );
}

function BoardIcon() {
  return (
    <svg className="ico" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="2.5" y="3" width="15" height="14" rx="2" />
      <path d="M2.5 8h15M8 8v9" />
    </svg>
  );
}
function JoinIcon() {
  return (
    <svg className="ico" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="9" cy="7" r="3" />
      <path d="M3.5 16.5c0-3 2.5-4.8 5.5-4.8s5.5 1.8 5.5 4.8" />
      <path d="M16 6.5v4M18 8.5h-4" />
    </svg>
  );
}
function AdminIcon() {
  return (
    <svg className="ico" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M10 2.5l6 2.2v4.2c0 3.6-2.5 6.6-6 8-3.5-1.4-6-4.4-6-8V4.7l6-2.2z" />
    </svg>
  );
}

/** Sidebar rail. Role-aware: partners see Browse + sign-in; admins see the
 *  admin sections plus a "View board" toggle. */
export function Rail({
  role,
  partner,
  adminEmail,
}: {
  role: import("../role").Role;
  partner: Partner | null;
  adminEmail: string | null;
}) {
  const { pathname } = useLocation();
  const onBoard = pathname === "/" || pathname.startsWith("/case");
  const onJoin = pathname.startsWith("/signin");
  const onAdmin = pathname.startsWith("/admin");

  return (
    <nav className="rail">
      <Link to={role === "admin" ? "/admin" : "/"} className="logo">
        <DatabricksLogo />
        <div className="wordmark">Partner Board</div>
      </Link>

      {role === "admin" ? (
        <>
          <div className="navlabel">Manage</div>
          <Link to="/admin" className={`navitem ${onAdmin && pathname === "/admin" ? "active" : ""}`}>
            <AdminIcon /> Use cases
          </Link>
          <Link to="/admin/partners" className={`navitem ${pathname === "/admin/partners" ? "active" : ""}`}>
            <JoinIcon /> Partners
          </Link>
          <Link to="/" className={`navitem ${onBoard ? "active" : ""}`}>
            <BoardIcon /> {onBoard ? "Back to admin" : "View board"}
          </Link>
          <div className="spacer" />
          {adminEmail && (
            <div className="navitem" title={adminEmail}>
              <span className="avatar">{initials(adminEmail)}</span>
              <span className="who-txt">{adminEmail}</span>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="navlabel">Browse</div>
          <Link to="/" className={`navitem ${onBoard ? "active" : ""}`}>
            <BoardIcon /> Open use cases
          </Link>
          <Show when="signed-out">
            <Link to="/signin" className={`navitem ${onJoin ? "active" : ""}`}>
              <JoinIcon /> Sign in as a partner
            </Link>
          </Show>
          <Show when="signed-in">
            <div className="navitem">
              <UserButton /> {partner?.company ?? "Account"}
            </div>
          </Show>
          <div className="spacer" />
        </>
      )}
    </nav>
  );
}

/** Content-area top bar with title + who's signed in. */
export function TopBar({
  title,
  sub,
  partner,
}: {
  title: string;
  sub?: string;
  partner: Partner | null;
}) {
  return (
    <header className="topbar">
      <div className="topbar-lead">
        <DatabricksLogo />
        <span className="topbar-sep" aria-hidden />
        <div>
          <h1>{title}</h1>
          {sub && <div className="sub">{sub}</div>}
        </div>
      </div>
      {partner && (
        <div className="who-chip" title={partner.email}>
          <span className="avatar">{initials(partner.company)}</span>
          <span className="who-txt">{partner.company}</span>
        </div>
      )}
    </header>
  );
}

function initials(name: string) {
  const parts = name.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "P";
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="center-state">
      <div className="spinner" aria-hidden />
      <p>{label}…</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="center-state">
      <h3>{title}</h3>
      {hint && <p className="muted">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="center-state">
      <h3>Something went wrong</h3>
      <p className="muted">{message}</p>
    </div>
  );
}
