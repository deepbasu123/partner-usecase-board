"""Admin API route tests with db + email mocked (no DB needed)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_create_case_uses_forwarded_user_and_emails_partners(client):
    with patch("backend.routes_admin.db.create_use_case",
               return_value={"id": "uc1", "title": "New Brief", "description": "d",
                             "industry": None, "region": "ANZ", "status": "open",
                             "posted_by": "sa@databricks.com", "created_at": "t"}) as mk, \
         patch("backend.routes_admin.db.list_partners",
               return_value=[{"email": "a@x.com"}, {"email": "b@y.com"}]), \
         patch("backend.routes_admin.email.send_new_use_case") as send:
        r = client.post("/api/admin/use-cases",
                        json={"title": "New Brief", "description": "d", "region": "ANZ"},
                        headers={"X-Forwarded-Email": "sa@databricks.com"})
    assert r.status_code == 201
    # posted_by taken from the forwarded identity
    assert mk.call_args[0][4] == "sa@databricks.com"
    # every partner emailed
    assert send.called
    assert send.call_args[0][0] == ["a@x.com", "b@y.com"]


def test_create_case_requires_title(client):
    r = client.post("/api/admin/use-cases", json={"description": "d"},
                    headers={"X-Forwarded-Email": "sa@databricks.com"})
    assert r.status_code == 422


def test_close_case(client):
    with patch("backend.routes_admin.db.set_status",
               return_value={"id": "uc1", "title": "T", "status": "closed", "closed_at": "t"}):
        r = client.patch("/api/admin/use-cases/uc1", json={"status": "closed"})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_close_case_rejects_bad_status(client):
    r = client.patch("/api/admin/use-cases/uc1", json={"status": "banana"})
    assert r.status_code == 422


def test_list_cases(client):
    with patch("backend.routes_admin.db.list_all_use_cases",
               return_value=[{"id": "uc1", "title": "T", "status": "open", "response_count": 2}]):
        r = client.get("/api/admin/use-cases")
    assert r.status_code == 200
    assert r.json()[0]["response_count"] == 2


def test_list_responses_for_case(client):
    with patch("backend.routes_admin.db.list_responses_for",
               return_value=[{"id": "r1", "approach": "we'd do X", "company": "Acme GT",
                              "email": "a@x.com", "contact_name": None, "created_at": "t"}]):
        r = client.get("/api/admin/use-cases/uc1/responses")
    assert r.status_code == 200
    assert r.json()[0]["company"] == "Acme GT"


def test_list_partners(client):
    with patch("backend.routes_admin.db.list_partners",
               return_value=[{"id": "p1", "email": "a@x.com", "company": "Acme GT",
                              "contact_name": None, "created_at": "t"}]):
        r = client.get("/api/admin/partners")
    assert r.status_code == 200
    assert r.json()[0]["company"] == "Acme GT"
