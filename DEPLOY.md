# Deploy checklist & open decisions

Everything below needs live infrastructure and/or your go-ahead. Nothing here
has been done yet — the code is built and tested locally only.

## Open decisions (need you)

1. **Email transport.** The email module is a stub. Pick Gmail API (via the
   `/gmail` skill; fine for pilot volume) or an SMTP relay, then wire it into
   `common/email.py::_send` and re-copy into both backends. **Per your rule, no
   external email sends until you approve the transport and a test send.**
2. **Cloud Run project + region.** Which GCP project hosts the portal. Needs an
   interactive `gcloud auth login` from you.
3. **Lakebase instance.** Reuse an existing deep-test instance (e.g.
   `lottery-hub-db`) or create a dedicated one. Apply `db/schema.sql` +
   `db/seed.sql` via `deploy/provision_lakebase.sh`.
4. **Admin access group.** Which workspace group/users may reach the admin app
   (see the required permissions block below).

## Task 0 spike (must pass before relying on the architecture)

The one genuinely unproven thing: **can the portal on Cloud Run reach Lakebase
in the AWS deep-test workspace via a service principal?**

1. Create an SP: `databricks service-principals create --display-name partner-portal-backend`
   and a secret. Grant it a Lakebase Postgres role with `SELECT/INSERT` on the
   board tables + `generate_database_credential`.
2. Set `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`,
   `LAKEBASE_INSTANCE`, `PGDATABASE` and run a connectivity probe (see the plan's
   `spike/check_lakebase_from_outside.py`). Expect `SELECT 1` to succeed.
3. If egress is blocked → fallback is hosting the portal in one-env AWS. **Stop
   and decide before proceeding.**

> Note: Databricks CLI v0.228.0 has **no `database` command group** and
> `apps list` RPC fails — use the REST API (`/api/2.0/database/instances`,
> `/api/2.0/apps`) or a newer CLI.

## Portal → Cloud Run

```bash
./deploy/portal_cloudrun.sh <gcp-project> <region>
```
Required env / secrets on the service (all enforced, no safe defaults):
- `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` (SP M2M)
- `LAKEBASE_INSTANCE`, `PGDATABASE=databricks_postgres`
- `SESSION_SECRET` — **must set** (else cookies are forgeable; the app warns)
- `PORTAL_ORIGIN` — the public Cloud Run URL (else credentialed CORS fails)
- `EOI_NOTIFY_EMAILS`, `EMAIL_FROM`
- `COOKIE_SECURE` stays default `true` (https)

After deploy: from a browser with **no Databricks login**, confirm the board
loads, signup works, and an EOI submits. That's the proof the public surface
works without a Databricks account.

## Admin → Databricks App

1. Edit `admin-app/app.yaml`: set `LAKEBASE_INSTANCE` and `BOARD_URL` (the portal
   URL). Attach the Lakebase **Database** resource so `PGHOST/PGUSER` inject.
2. **Add a permissions block so only your team can reach it** (without this,
   Databricks Apps default to all authenticated workspace users — a real risk on
   a shared workspace):
   ```yaml
   permissions:
     - group_name: "<your-team-group>"
       permission_level: "CAN_USE"
   ```
3. Deploy (REST API or newer CLI): `databricks apps deploy partner-admin --source-code-path .`
4. Verify: reachable only when logged into the workspace; posting a case writes
   to Lakebase and shows on the portal; partners get the new-case email.

## Deferred to post-pilot (intentionally OUT)

- GT-partner allowlist/gating (pilot signup is open to anyone with the link)
- Email-link verification (`partners.verified` column reserved for it)
- Partner-to-partner visibility (EOIs stay private to Databricks)
- A `has_responded` pre-check so the EOI form hides after responding (today the
  server correctly rejects the duplicate with a friendly 409)
