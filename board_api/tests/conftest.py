"""Test fixtures. Points db.py at a local Postgres via DATABASE_URL.

Tests that touch the database use the `db` fixture, which truncates the mutable
tables (partners + responses; responses cascades) so each test is isolated and
skips cleanly when no DATABASE_URL is configured. Session/email/auth tests need
no DB and simply don't request the fixture.
"""
import os
import pytest


@pytest.fixture
def db():
    """Yield the db module against a clean local Postgres, or skip."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("no DATABASE_URL configured for db tests")
    from board_api import db as dbmod
    with dbmod.get_conn() as c, c.cursor() as cur:
        cur.execute("TRUNCATE responses, partners RESTART IDENTITY CASCADE")
    return dbmod
