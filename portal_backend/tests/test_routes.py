"""API route tests using FastAPI TestClient with db + email mocked.

No database required — every db call is patched, so these validate the HTTP
contract (status codes, cookies, error handling) in isolation.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from portal_backend.main import app
from portal_backend import sessions


@pytest.fixture
def client():
    return TestClient(app)


def _session_cookie(pid="p1"):
    return sessions.make_session_cookie(pid)


def test_signup_sets_cookie_and_returns_partner(client):
    with patch("portal_backend.routes_partners.db.get_or_create_partner",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT",
                             "contact_name": None, "created_at": "t"}), \
         patch("portal_backend.routes_partners.email.send_welcome"):
        r = client.post("/api/signup", json={"email": "a@x.com", "company": "Acme GT"})
    assert r.status_code == 200
    assert r.json()["id"] == "p1"
    assert sessions.SESSION_COOKIE_NAME in r.cookies


def test_signup_rejects_bad_email(client):
    r = client.post("/api/signup", json={"email": "not-an-email", "company": "Acme"})
    assert r.status_code == 422


def test_me_401_without_session(client):
    r = client.get("/api/me")
    assert r.status_code == 401


def test_me_returns_partner_with_session(client):
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("p9"))
    with patch("portal_backend.routes_partners.db.get_partner",
               return_value={"id": "p9", "email": "z@x.com", "company": "Zeta GT",
                             "contact_name": None, "created_at": "t"}):
        r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["id"] == "p9"
    assert r.json()["company"] == "Zeta GT"


def test_me_401_when_partner_gone(client):
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("ghost"))
    with patch("portal_backend.routes_partners.db.get_partner", return_value=None):
        r = client.get("/api/me")
    assert r.status_code == 401


def test_list_cases(client):
    with patch("portal_backend.routes_board.db.list_open_use_cases",
               return_value=[{"id": "uc1", "title": "T", "description": "d",
                              "industry": None, "region": "ANZ", "status": "open",
                              "created_at": "t"}]):
        r = client.get("/api/use-cases")
    assert r.status_code == 200
    assert r.json()[0]["id"] == "uc1"


def test_get_case_404(client):
    with patch("portal_backend.routes_board.db.get_use_case", return_value=None):
        r = client.get("/api/use-cases/nope")
    assert r.status_code == 404


def test_response_requires_session(client):
    r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 401


def test_response_created_201(client):
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("p1"))
    with patch("portal_backend.routes_responses.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "open",
                             "posted_by": "admin@example.com"}), \
         patch("portal_backend.routes_responses.db.create_response",
               return_value={"id": "r1", "use_case_id": "uc1", "partner_id": "p1",
                             "approach": "x", "created_at": "t"}), \
         patch("portal_backend.routes_responses.db.get_partner",
               return_value={"id": "p1", "company": "Acme GT", "email": "a@x.com"}), \
         patch("portal_backend.routes_responses.email.send_new_eoi"):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 201
    assert r.json()["id"] == "r1"


def test_duplicate_response_returns_409(client):
    from portal_backend import db as dbmod
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("p1"))
    with patch("portal_backend.routes_responses.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "open",
                             "posted_by": "admin@example.com"}), \
         patch("portal_backend.routes_responses.db.create_response",
               side_effect=dbmod.DuplicateResponse()):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 409


def test_response_404_when_case_missing(client):
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("p1"))
    with patch("portal_backend.routes_responses.db.get_use_case", return_value=None):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 404


def test_response_rejected_on_closed_case(client):
    client.cookies.set(sessions.SESSION_COOKIE_NAME, _session_cookie("p1"))
    with patch("portal_backend.routes_responses.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "closed",
                             "posted_by": "admin@example.com"}):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 409


def test_get_case_hides_closed_from_public(client):
    # A closed case must not be served on the public detail endpoint.
    with patch("portal_backend.routes_board.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "closed"}):
        r = client.get("/api/use-cases/uc1")
    assert r.status_code == 404


def test_board_endpoints_need_no_session(client):
    # Explicit guarantee: the public board is reachable with no cookie.
    with patch("portal_backend.routes_board.db.list_open_use_cases", return_value=[]):
        r = client.get("/api/use-cases")
    assert r.status_code == 200
