"""Admin API route tests with db + email mocked (no DB needed).

Each guarded call needs a valid admin cookie, so the `admin_client` fixture
logs in through the real login endpoint (password patched) first.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from board_api.app import app
from board_api import admin_auth, routes_admin


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "secret")
    # Over http://testserver the client won't resend a Secure cookie, so mint
    # a non-secure admin cookie here — mirrors the local COOKIE_SECURE=false path.
    monkeypatch.setattr(routes_admin, "_COOKIE_SECURE", False)
    c = TestClient(app)
    assert c.post("/api/admin/login", json={"password": "secret"}).status_code == 200
    return c


def test_create_case_uses_admin_email_and_emails_partners(admin_client):
    with patch("board_api.routes_admin.db.create_use_case",
               return_value={"id": "uc1", "title": "New Brief", "description": "d",
                             "industry": None, "region": "ANZ", "status": "open",
                             "posted_by": routes_admin.ADMIN_EMAIL, "created_at": "t"}) as mk, \
         patch("board_api.routes_admin.db.list_all_partners",
               return_value=[{"email": "a@x.com"}, {"email": "b@y.com"}]), \
         patch("board_api.routes_admin.email.send_new_use_case") as send:
        r = admin_client.post("/api/admin/use-cases",
                              json={"title": "New Brief", "description": "d", "region": "ANZ"})
    assert r.status_code == 201
    # posted_by is the configured ADMIN_EMAIL (5th positional arg to create_use_case).
    assert mk.call_args[0][4] == routes_admin.ADMIN_EMAIL
    # every partner emailed
    assert send.called
    assert send.call_args[0][0] == ["a@x.com", "b@y.com"]


def test_create_case_requires_title(admin_client):
    r = admin_client.post("/api/admin/use-cases", json={"description": "d"})
    assert r.status_code == 422


def test_close_case(admin_client):
    with patch("board_api.routes_admin.db.set_status",
               return_value={"id": "uc1", "title": "T", "status": "closed", "closed_at": "t"}):
        r = admin_client.patch("/api/admin/use-cases/uc1", json={"status": "closed"})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_close_case_rejects_bad_status(admin_client):
    r = admin_client.patch("/api/admin/use-cases/uc1", json={"status": "banana"})
    assert r.status_code == 422


def test_list_cases(admin_client):
    with patch("board_api.routes_admin.db.list_all_use_cases",
               return_value=[{"id": "uc1", "title": "T", "status": "open", "response_count": 2}]):
        r = admin_client.get("/api/admin/use-cases")
    assert r.status_code == 200
    assert r.json()[0]["response_count"] == 2


def test_list_responses_for_case(admin_client):
    with patch("board_api.routes_admin.db.list_responses_for",
               return_value=[{"id": "r1", "approach": "we'd do X", "company": "Acme GT",
                              "email": "a@x.com", "contact_name": None, "created_at": "t"}]):
        r = admin_client.get("/api/admin/use-cases/uc1/responses")
    assert r.status_code == 200
    assert r.json()[0]["company"] == "Acme GT"


def test_list_partners(admin_client):
    with patch("board_api.routes_admin.db.list_all_partners",
               return_value=[{"id": "p1", "email": "a@x.com", "company": "Acme GT",
                              "contact_name": None, "created_at": "t"}]):
        r = admin_client.get("/api/admin/partners")
    assert r.status_code == 200
    assert r.json()[0]["company"] == "Acme GT"


def test_whoami_returns_admin_email(admin_client):
    r = admin_client.get("/api/admin/whoami")
    assert r.status_code == 200
    assert r.json()["email"] == routes_admin.ADMIN_EMAIL
