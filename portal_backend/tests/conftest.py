"""Test fixtures. Points db.py at a local Postgres via PG* env vars.

Tests that touch the database use the `db` fixture, which truncates the
mutable tables (partners + responses; responses cascades) so each test is
isolated and skips cleanly when no Postgres is configured. Session/email
tests need no DB and simply don't request the fixture.
"""
import os
import pytest


@pytest.fixture
def db():
    """Yield the db module against a clean local Postgres, or skip."""
    if not os.environ.get("PGHOST"):
        pytest.skip("no PGHOST configured for db tests")
    from portal_backend import db as dbmod
    with dbmod.get_conn() as c, c.cursor() as cur:
        cur.execute("TRUNCATE responses, partners RESTART IDENTITY CASCADE")
    return dbmod
