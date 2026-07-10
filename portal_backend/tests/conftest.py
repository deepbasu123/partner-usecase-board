"""Test fixtures. Points db.py at a local Postgres via PG* env vars.

Requires a running Postgres with the board schema applied. The run_tests.sh
helper spins up an ephemeral Postgres 16 and sets these env vars:
  PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE, LAKEBASE_INSTANCE
"""
import os
import pytest


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate mutable tables between tests so each test is isolated.

    use_cases keeps the seeded row; we only clear partners + responses
    (responses cascades). Skipped if no DB is configured.
    """
    if not os.environ.get("PGHOST"):
        pytest.skip("no PGHOST configured for db tests")
    from portal_backend import db
    with db.get_conn() as c, c.cursor() as cur:
        cur.execute("TRUNCATE responses, partners RESTART IDENTITY CASCADE")
    yield
