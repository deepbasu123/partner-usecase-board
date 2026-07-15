import { SignIn } from "@clerk/react";
import { TopBar } from "./Chrome";

export function SignInPage() {
  return (
    <>
      <TopBar title="Sign in" sub="We'll email you a code — no password" partner={null} />
      <main className="main">
        <div className="main-wrap" style={{ maxWidth: 460 }}>
          <SignIn routing="path" path="/signin" signUpUrl="/signin" />
        </div>
      </main>
    </>
  );
}
