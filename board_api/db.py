"""Neon Postgres access for the merged Partner Board API.

Single connection source: the DATABASE_URL env var (Neon pooled string). No
Databricks SDK, no credential minting — plain Postgres. The SPA never imports
this module; only the FastAPI backend does, so DB credentials stay server-side.
"""
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.string import TextLoader

# Postgres UUID OID. Load UUID columns as plain strings (not Python UUID
# objects) so ids serialize cleanly into JSON responses and signed cookies.
_UUID_OID = 2950


class _UuidAsText(TextLoader):
    """Return uuid values as str."""


class DuplicateResponse(Exception):
    """Raised when a partner submits a second EOI for the same use case."""


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is required (Neon pooled connection string, "
            "?sslmode=require only — no channel_binding).")
    return dsn


def get_conn():
    """Open a new connection with dict rows and UUID-as-string loading."""
    conn = psycopg.connect(_dsn(), row_factory=dict_row, autocommit=True)
    conn.adapters.register_loader(_UUID_OID, _UuidAsText)
    return conn


# ── public portal reads/writes ───────────────────────────────────────────────

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


def get_partner(partner_id):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners WHERE id = %s", (partner_id,))
        return cur.fetchone()


def list_all_partners():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, email, company, contact_name, created_at "
                    "FROM partners ORDER BY created_at DESC")
        return cur.fetchall()


# ── admin operations ─────────────────────────────────────────────────────────

def create_use_case(title, description, industry, region, posted_by):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO use_cases (title, description, industry, region, posted_by) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, title, description, industry, region, status, posted_by, created_at",
            (title, description, industry, region, posted_by))
        return cur.fetchone()


def set_status(uc_id, status):
    """Open or close a use case; closed_at is set/cleared accordingly.

    Returns the full row plus response_count so the shape matches the AdminCase
    the frontend already holds.
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
            "SELECT r.id, r.approach, r.created_at, p.company, p.email, p.contact_name "
            "FROM responses r JOIN partners p ON p.id = r.partner_id "
            "WHERE r.use_case_id = %s ORDER BY r.created_at DESC",
            (uc_id,))
        return cur.fetchall()
