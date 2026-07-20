import { Link, useLocation } from "react-router-dom";
import { Show, UserButton } from "@clerk/react";
import type { Partner } from "../api";

/** lakeAlliance layered mark — three stacked layers (diamond + two chevrons). */
export function LakeAllianceMark({ className = "la-mark" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 58"
      fill="none"
      stroke="#FF3621"
      strokeWidth="3.2"
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-label="lakeAlliance"
    >
      <path d="M32 5 L58 21 L32 37 L6 21 Z" />
      <path d="M8 27 L32 44 L56 27" />
      <path d="M8 35 L32 52 L56 35" />
    </svg>
  );
}

/** "lakeAlliance" wordmark — one word, "lake" navy + "Alliance" lava (no space). */
export function Wordmark({ className = "wordmark" }: { className?: string }) {
  return (
    <div className={className}>
      <span className="wm-lake">lake</span><span className="wm-alliance">Alliance</span>
    </div>
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

  return (
    <nav className="rail">
      <Link to={role === "admin" ? "/admin" : "/"} className="logo">
        <LakeAllianceMark />
        <Wordmark />
      </Link>

      {/* Role badge: shows how you're signed in. Databricks employees always;
          partners only once signed in; hidden for signed-out visitors. */}
      {role === "admin" ? (
        <div className="role-badge role-badge-dbx">Signed in as Databricks employee</div>
      ) : (
        <Show when="signed-in">
          <div className="role-badge role-badge-partner">Signed in as partner</div>
        </Show>
      )}

      {role === "admin" ? (
        <>
          <div className="navlabel">Manage</div>
          <Link to="/admin" className={`navitem ${pathname === "/admin" ? "active" : ""}`}>
            <AdminIcon /> Use cases
          </Link>
          <Link to="/admin/partners" className={`navitem ${pathname === "/admin/partners" ? "active" : ""}`}>
            <JoinIcon /> Partners
          </Link>
          <Link to={onBoard ? "/admin" : "/"} className="navitem">
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
        <LakeAllianceMark />
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
