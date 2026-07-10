# Task 0 Spike — Results

**Date:** 2026-07-10 · **Workspace:** deep-test-1 (fevm-deep-test-1, AWS us-east-1)

## Verdict

| Leg | Result | Notes |
|---|---|---|
| **Cross-cloud Lakebase connectivity** | ✅ **GO** | A host outside Databricks connected to a Lakebase Postgres endpoint over the public internet and queried it. |
| **M2M service-principal path** | ✅ **GO** | SP OAuth → mint credential → connect → query, all proven. Requires the SP be registered as a `SERVICE_PRINCIPAL` instance role (recipe below). |
| Pinned pip installs under lockdown | ✅ GO | Installed via `pypi-proxy.dev.databricks.com`. |
| Pinned npm install + vite build under lockdown | ✅ GO | Internal `npm-proxy.cloud.databricks.com` serves packages; SPA builds. |
| Email transport | ⛔ not tested | Deferred — needs a transport decision + explicit send approval. |

**Bottom line:** the portal-on-Cloud-Run → Lakebase-in-AWS architecture is validated.
No fallback to one-env AWS needed.

**Independently verified** on a second model (Sonnet): confirmed external-host
connectivity to the Lakebase endpoint and that the SP is registered with
`identity_type = SERVICE_PRINCIPAL` (the structural prerequisite for OAuth token
auth). The full SP-secret path was run twice during the spike with matching
results before the scratch secret was deleted.

**Security cleanup done:** the scratch SP's OAuth secret was **deleted** after the
spike (HTTP 200; the SP can no longer authenticate). The secret was never written
to disk or committed. The SP and its `tritium-lakebase` instance role remain and
should be removed when convenient (see cleanup list below).

## What was proven, precisely

- The **Databricks Python SDK `database` API works on SDK v0.118.0** even though the
  installed **CLI v0.228.0 has no `database`/`postgres` command group** and its
  `apps list` RPC fails. So credential minting goes through the SDK, not the CLI.
- Connecting from this laptop (external to Databricks = valid Cloud Run stand-in)
  to `tritium-lakebase` (`...database.us-east-1.cloud.databricks.com:5432`,
  `sslmode=require`) returned `SELECT 1` and `PostgreSQL 16.14`.
- The **full M2M path**: a dedicated SP authenticated via
  `DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET`, minted a Lakebase credential, and
  connected — using the SP's **application id as the Postgres user**.

## The provisioning recipe (this bit is essential)

A brand-new SP is rejected with `password authentication failed` until it is
registered as an **instance role with `identity_type = SERVICE_PRINCIPAL`**.
A bare Postgres `CREATE ROLE` produces a `PG_ONLY` role (expects a password) and
**does not work** with OAuth token auth.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import database as dbsvc

w = WorkspaceClient(profile="deep-test-1")
w.database.create_database_instance_role(
    "<instance-name>",
    dbsvc.DatabaseInstanceRole(
        name="<sp-application-id>",
        identity_type=dbsvc.DatabaseInstanceRoleIdentityType.SERVICE_PRINCIPAL,
    ),
)
# verify: w.database.list_database_instance_roles("<instance>") should show the
# SP with identity_type 'SERVICE_PRINCIPAL' (NOT 'PG_ONLY').
```

Then grant that role table privileges inside the target database
(`GRANT SELECT, INSERT ON partners, use_cases, responses TO "<sp-app-id>"`),
connecting as an admin identity.

## Connection code (matches portal_backend/db.py)

```python
import os, psycopg
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()  # M2M: DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET
host = w.database.get_database_instance(os.environ["LAKEBASE_INSTANCE"]).read_write_dns
tok  = w.database.generate_database_credential(
           request_id="partner-portal", instance_names=[os.environ["LAKEBASE_INSTANCE"]]).token
conn = psycopg.connect(host=host, port=5432, dbname="databricks_postgres",
                       user=os.environ["DATABRICKS_CLIENT_ID"], password=tok, sslmode="require")
```

## Spike artifacts to clean up (temporary)

- **Service principal `partner-portal-backend`** (app_id `786eaa4a-d274-4a90-8c0d-cb6f2580aeb8`,
  SCIM id `77939116774651`) + its OAuth secret — created only for this spike.
- **Instance role** for that SP on `tritium-lakebase`.

These were made against `tritium-lakebase` (a convenient existing instance) purely
to prove the path. For the real pilot, create a dedicated instance/SP and remove
these. The OAuth secret was kept in-shell only and never written to disk or git.
