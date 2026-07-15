"""Unit for link_or_create_partner's contract via a fake cursor (no real PG)."""
from unittest.mock import MagicMock, patch
from board_api import db


def test_link_or_create_partner_upserts_by_email():
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"id": "p1", "email": "a@x.com",
                                      "company": "Acme", "contact_name": None,
                                      "created_at": "t"}
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_conn.__enter__.return_value = fake_conn
    with patch("board_api.db.get_conn", return_value=fake_conn):
        row = db.link_or_create_partner("a@x.com", "user_123", "Acme")
    assert row["id"] == "p1"
    # the SQL must reference clerk_user_id and use ON CONFLICT (email)
    sql = fake_cur.execute.call_args[0][0]
    assert "clerk_user_id" in sql
    assert "ON CONFLICT (email)" in sql
