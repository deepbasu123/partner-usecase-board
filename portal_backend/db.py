"""Lakebase Postgres access for the public partner portal.

The portal runs OUTSIDE Databricks (Cloud Run), so in production it
authenticates as a service principal via M2M OAuth env vars
(DATABRICKS_HOST, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET) that
WorkspaceClient() picks up automatically, then mints a short-lived Lakebase
credential.

Connection resolution (first match wins), so the same module works locally,
in tests, and on Cloud Run:
  host     = PGHOST      else instance.read_write_dns (via SDK)
  user     = PGUSER      else DATABRICKS_CLIENT_ID (the SP)
  password = PGPASSWORD  else a freshly minted Lakebase credential (via SDK)

The SPA never imports this module — only the FastAPI backend does, so DB
credentials stay server-side.
"""
import os

import psycopg
from psycopg.rows import dict_row

DATABASE = os.environ.get("PGDATABASE", "databricks_postgres")


class DuplicateResponse(Exception):
    """Raised when a partner submits a second EOI for the same use case."""


def _conn_params():
    host = os.environ.get("PGHOST")
    user = os.environ.get("PGUSER")
    pwd = os.environ.get("PGPASSWORD")

    # Any missing piece is resolved by authenticating to Databricks as the SP
    # and minting a Lakebase credential. Imported lazily so local/test runs
    # never need the SDK or network.
    if not (host and user and pwd):
        from databricks.sdk import WorkspaceClient
        instance = os.environ["LAKEBASE_INSTANCE"]
        w = WorkspaceClient()
        host = host or w.database.get_database_instance(instance).read_write_dns
        user = user or os.environ["DATABRICKS_CLIENT_ID"]
        pwd = pwd or w.database.generate_database_credential(
            request_id="partner-portal", instance_names=[instance]).token

    return dict(host=host, port=int(os.environ.get("PGPORT", "5432")),
                dbname=DATABASE, user=user, password=pwd,
                sslmode=os.environ.get("PGSSLMODE", "require"))


def get_conn():
    """Open a new autocommit-off connection with dict rows."""
    return psycopg.connect(**_conn_params(), row_factory=dict_row)


def list_open_use_cases():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, title, description, industry, region, status, created_at "
                    "FROM use_cases WHERE status='open' ORDER BY created_at DESC")
        return cur.fetchall()


def get_use_case(uc_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, title, description, industry, region, status, posted_by, created_at "
                    "FROM use_cases WHERE id = %s", (uc_id,))
        return cur.fetchone()


def get_or_create_partner(email, company, contact_name):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO partners (email, company, contact_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET company = EXCLUDED.company "
            "RETURNING id, email, company, contact_name, created_at",
            (email, company, contact_name))
        return cur.fetchone()


def create_response(use_case_id, partner_id, approach):
    try:
        with get_conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO responses (use_case_id, partner_id, approach) "
                "VALUES (%s, %s, %s) "
                "RETURNING id, use_case_id, partner_id, approach, created_at",
                (use_case_id, partner_id, approach))
            return cur.fetchone()
    except psycopg.errors.UniqueViolation:
        raise DuplicateResponse(
            f"partner {partner_id} already responded to {use_case_id}")


def list_all_partners():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners ORDER BY created_at DESC")
        return cur.fetchall()
