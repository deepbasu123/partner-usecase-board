"""Public API route tests using FastAPI TestClient with db + email mocked.

No database required — every db call is patched, so these validate the HTTP
contract (status codes, error handling) in isolation. Auth is exercised via
dependency_overrides on clerk_auth.require_identity (Bearer-token gate).
Patch targets are board_api.routes_public.* since the three former route files
are merged.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from board_api.app import app
from board_api import clerk_auth


@pytest.fixture
def client():
    return TestClient(app)


def _auth(email="a@x.com", uid="user_1"):
    """Override require_identity so routes see a verified partner."""
    app.dependency_overrides[clerk_auth.require_identity] = \
        lambda: {"email": email, "clerk_user_id": uid}


def _noauth():
    app.dependency_overrides.pop(clerk_auth.require_identity, None)


# ── /api/me ──────────────────────────────────────────────────────────────────

def test_me_onboarding_required_when_no_profile(client):
    _auth("new@x.com")
    with patch("board_api.routes_public.db.get_partner_by_email", return_value=None):
        r = client.get("/api/me")
    _noauth()
    assert r.status_code == 200
    assert r.json() == {"onboarding_required": True}


def test_me_returns_profile_when_exists(client):
    _auth("z@x.com")
    with patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p9", "email": "z@x.com", "company": "Zeta GT",
                             "contact_name": None, "created_at": "t"}):
        r = client.get("/api/me")
    _noauth()
    assert r.status_code == 200
    assert r.json()["company"] == "Zeta GT"


def test_me_401_without_token(client):
    r = client.get("/api/me")   # no dependency override, no header
    assert r.status_code == 401


# ── /api/onboarding ───────────────────────────────────────────────────────────

def test_onboarding_creates_profile(client):
    _auth("new@x.com", "user_9")
    with patch("board_api.routes_public.db.link_or_create_partner",
               return_value={"id": "p2", "email": "new@x.com", "company": "Acme GT",
                             "contact_name": None, "created_at": "t"}), \
         patch("board_api.routes_public.email.send_welcome"):
        r = client.post("/api/onboarding", json={"company": "Acme GT"})
    _noauth()
    assert r.status_code == 201
    assert r.json()["company"] == "Acme GT"


def test_onboarding_rejects_blank_company(client):
    _auth("new@x.com")
    r = client.post("/api/onboarding", json={"company": "  "})
    _noauth()
    assert r.status_code == 422


# ── /api/use-cases (public board) ────────────────────────────────────────────

def test_list_cases(client):
    with patch("board_api.routes_public.db.list_open_use_cases",
               return_value=[{"id": "uc1", "title": "T", "description": "d",
                              "industry": None, "region": "ANZ", "status": "open",
                              "created_at": "t"}]):
        r = client.get("/api/use-cases")
    assert r.status_code == 200
    assert r.json()[0]["id"] == "uc1"


def test_get_case_404(client):
    with patch("board_api.routes_public.db.get_use_case", return_value=None):
        r = client.get("/api/use-cases/nope")
    assert r.status_code == 404


def test_get_case_hides_closed_from_public(client):
    with patch("board_api.routes_public.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "closed"}):
        r = client.get("/api/use-cases/uc1")
    assert r.status_code == 404


def test_board_endpoints_need_no_session(client):
    with patch("board_api.routes_public.db.list_open_use_cases", return_value=[]):
        r = client.get("/api/use-cases")
    assert r.status_code == 200


# ── /api/use-cases/{id}/responses ────────────────────────────────────────────

def test_response_requires_token(client):
    r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    assert r.status_code == 401


def test_response_401_when_no_partner_profile(client):
    _auth("new@x.com", "user_1")
    with patch("board_api.routes_public.db.get_partner_by_email", return_value=None):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 401


def test_response_created_201(client):
    _auth("a@x.com", "user_1")
    with patch("board_api.routes_public.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "open",
                             "posted_by": "admin@example.com"}), \
         patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT"}), \
         patch("board_api.routes_public.db.create_response",
               return_value={"id": "r1", "use_case_id": "uc1", "partner_id": "p1",
                             "approach": "x", "created_at": "t"}), \
         patch("board_api.routes_public.email.send_new_eoi"):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 201
    assert r.json()["id"] == "r1"


def test_duplicate_response_returns_409(client):
    from board_api import db as dbmod
    _auth("a@x.com", "user_1")
    with patch("board_api.routes_public.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "open",
                             "posted_by": "admin@example.com"}), \
         patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT"}), \
         patch("board_api.routes_public.db.create_response",
               side_effect=dbmod.DuplicateResponse()):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 409


def test_response_404_when_case_missing(client):
    _auth("a@x.com", "user_1")
    with patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT"}), \
         patch("board_api.routes_public.db.get_use_case", return_value=None):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 404


def test_response_rejected_on_closed_case(client):
    _auth("a@x.com", "user_1")
    with patch("board_api.routes_public.db.get_partner_by_email",
               return_value={"id": "p1", "email": "a@x.com", "company": "Acme GT"}), \
         patch("board_api.routes_public.db.get_use_case",
               return_value={"id": "uc1", "title": "T", "status": "closed",
                             "posted_by": "admin@example.com"}):
        r = client.post("/api/use-cases/uc1/responses", json={"approach": "x"})
    _noauth()
    assert r.status_code == 409
