import { SignIn } from "@clerk/react";
import { TopBar } from "./Chrome";

export function SignInPage() {
  return (
    <>
      <TopBar title="Sign in" sub="We'll email you a code — no password" partner={null} />
      <main className="main">
        <div className="main-wrap" style={{ maxWidth: 460 }}>
          {/* withSignUp merges sign-up into the same flow: a new email is
              registered and an existing one is signed in, both via the same
              email box + OTP. Without it, <SignIn> is lookup-only and a
              first-time partner hits "couldn't find your account". */}
          <SignIn routing="path" path="/signin" withSignUp />
        </div>
      </main>
    </>
  );
}
