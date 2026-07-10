"""Lakebase access for the admin app.

This side IS a Databricks App, so in production Databricks injects the
service-principal Postgres credentials (PGHOST/PGUSER) and the app mints a
Lakebase credential via its injected identity — the tritium house pattern.
Locally/in tests, PG* env vars point at a Postgres directly.

Reuses the same three tables as the portal, with admin-only operations:
create/close use cases, list every case (any status), and read responses
joined to partner details.
"""
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.string import TextLoader

DATABASE = os.environ.get("PGDATABASE", "databricks_postgres")
INSTANCE = os.environ.get("LAKEBASE_INSTANCE")

_UUID_OID = 2950


class _UuidAsText(TextLoader):
    """Return uuid values as str so ids serialize cleanly to JSON."""


def _conn_params():
    host = os.environ.get("PGHOST")
    user = os.environ.get("PGUSER")
    pwd = os.environ.get("PGPASSWORD")

    if not (host and user and pwd):
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        host = host or w.database.get_database_instance(INSTANCE).read_write_dns
        user = user or w.current_user.me().user_name
        pwd = pwd or w.database.generate_database_credential(
            request_id="partner-admin", instance_names=[INSTANCE]).token

    return dict(host=host, port=int(os.environ.get("PGPORT", "5432")),
                dbname=DATABASE, user=user, password=pwd,
                sslmode=os.environ.get("PGSSLMODE", "require"))


def get_conn():
    conn = psycopg.connect(**_conn_params(), row_factory=dict_row)
    conn.adapters.register_loader(_UUID_OID, _UuidAsText)
    return conn


def create_use_case(title, description, industry, region, posted_by):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO use_cases (title, description, industry, region, posted_by) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, title, description, industry, region, status, posted_by, created_at",
            (title, description, industry, region, posted_by))
        return cur.fetchone()


def set_status(uc_id, status):
    """Open or close a use case. closed_at is set/cleared accordingly.

    Returns the full row (plus response_count) so the shape matches the
    AdminCase the frontend already holds.
    """
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE use_cases SET status = %s, "
            "closed_at = CASE WHEN %s = 'closed' THEN now() ELSE NULL END "
            "WHERE id = %s "
            "RETURNING id, title, description, industry, region, status, "
            "posted_by, created_at, closed_at, "
            "(SELECT count(*) FROM responses r WHERE r.use_case_id = use_cases.id) "
            "AS response_count",
            (status, status, uc_id))
        return cur.fetchone()


def list_all_use_cases():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.title, u.description, u.industry, u.region, u.status, "
            "u.posted_by, u.created_at, u.closed_at, "
            "(SELECT count(*) FROM responses r WHERE r.use_case_id = u.id) AS response_count "
            "FROM use_cases u ORDER BY u.created_at DESC")
        return cur.fetchall()


def list_responses_for(uc_id):
    """Responses to one use case, joined to the responding partner."""
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.approach, r.created_at, "
            "p.company, p.email, p.contact_name "
            "FROM responses r JOIN partners p ON p.id = r.partner_id "
            "WHERE r.use_case_id = %s ORDER BY r.created_at DESC",
            (uc_id,))
        return cur.fetchall()


def list_partners():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners ORDER BY created_at DESC")
        return cur.fetchall()
