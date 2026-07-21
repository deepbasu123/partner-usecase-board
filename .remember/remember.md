# Handoff

## State
lakeAlliance (formerly Partner Board) — Vercel+Neon app, branch `vercel-neon-deploy` @ HEAD `5e7aed5`, pushed to origin/deepbasu123. Live: https://lakealliance.vercel.app (new alias; old databricks-gt-partner.vercel.app still works). This session shipped: unified Clerk auth (email OTP; @databricks.com→admin, else partner board; break-glass pw at /admin/login), rebrand to one-word "lakeAlliance" (two-tone wordmark + 3-layer mark), Gmail SMTP email (per-recipient, confirmed delivering to primary inbox), "who are you" chooser hidden once signed in + rail role badge. Board cleaned to 6 use cases (deleted 6 via Neon: 3 tests + 3 low-engagement seed). board_api 57/57 tests pass.

## Next
1. Optional: rename Vercel PROJECT + GitHub REPO from `partner-usecase-board` to lake-alliance (only the public URL alias was changed, not project/repo names).
2. Replace 10 fake `.example` seed partners with real addresses before real partner notifications (posts silently skip .example — they bounce).

## Context
- Email creds live: GMAIL_USER/GMAIL_APP_PASSWORD (lakealliance.notify@gmail.com) in Vercel prod; source ~/Documents/gmail token.rtf. Gotcha: `send_new_use_case`→_safe swallows errors, so "no exception" ≠ delivered — verify via IMAP on SENDER account.
- Vercel gotcha: `vercel deploy --prod` does NOT auto-move the lakealliance.vercel.app alias — re-run `vercel alias set <newDeploy> lakealliance.vercel.app` after each prod deploy.
- Tokens: github/vercel(vcp_ prefix, use textutil to de-RTF)/gmail/resend all in ~/Documents/*.rtf.
- Deleted use-case backup saved to /tmp/la_backup/ (use_cases.json + responses.json) — temp, will clear.
- Full durable detail in ~/.claude/projects/-Users-deep-basu/memory/project_partner_usecase_board.md.
