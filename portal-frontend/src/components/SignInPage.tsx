import { SignIn } from "@clerk/react";
import { LakeAllianceMark, Wordmark } from "./Chrome";

// Clerk widget themed to the lakeAlliance palette. `variables` is Clerk's
// stable theming API (safer than targeting internal class names).
const clerkAppearance = {
  variables: {
    colorPrimary: "#ff3621",
    colorText: "#1b2b30",
    colorTextSecondary: "#56656b",
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    colorInputText: "#1b2b30",
    borderRadius: "10px",
    fontFamily: 'ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  elements: {
    rootBox: { width: "100%" },
    card: { boxShadow: "none", border: "none", background: "transparent", padding: 0 },
    header: { display: "none" },              // our own headline lives in the brand panel
    footer: { display: "none" },              // hide Clerk's dev/branding footer chrome
    formButtonPrimary: {
      fontSize: "15px", textTransform: "none", fontWeight: 650,
      boxShadow: "0 6px 16px -8px rgba(255,54,33,.8)",
    },
  },
};

export function SignInPage() {
  return (
    <main className="signin-stage">
      <div className="signin-card">
        {/* Brand panel — dark navy, layered-lines motif, value props. */}
        <aside className="signin-brand">
          <div className="signin-brand-top">
            <span className="signin-brand-mark" aria-hidden><LakeAllianceMark /></span>
            <Wordmark className="signin-brand-wordmark" />
          </div>
          <div className="signin-brand-body">
            <h1>Raise your hand for the work that fits.</h1>
            <p>Databricks posts real use cases looking for partner help. Sign in to
               browse open briefs and express interest.</p>
            <ul className="signin-brand-points">
              <li><span aria-hidden>✳</span> One email, one code — no password</li>
              <li><span aria-hidden>✳</span> Databricks staff use their @databricks.com email</li>
              <li><span aria-hidden>✳</span> Only the Databricks team sees your response</li>
            </ul>
          </div>
          <p className="signin-brand-foot">A Databricks app for Databricks partners</p>
        </aside>

        {/* Auth panel — the unified Clerk sign-in (auto-routes by email domain). */}
        <section className="signin-auth" aria-label="Sign in">
          <div className="signin-auth-head">
            <h2>Sign in</h2>
            <p>We'll email you a one-time code.</p>
          </div>
          {/* withSignUp merges sign-up into the same flow: a new email registers
              and an existing one signs in, both via the same email box + OTP. */}
          <SignIn routing="path" path="/signin" withSignUp appearance={clerkAppearance} />
        </section>
      </div>
    </main>
  );
}
