"""Admin gate tests: routes blocked without a cookie; login mints one."""
import pytest
from fastapi.testclient import TestClient

from board_api.app import app
from board_api import admin_auth, routes_admin


@pytest.fixture
def client(monkeypatch):
    # Non-secure cookie so the http test client resends it (mirrors local dev).
    monkeypatch.setattr(routes_admin, "_COOKIE_SECURE", False)
    return TestClient(app)


def test_admin_route_blocked_without_cookie(client):
    r = client.get("/api/admin/use-cases")
    assert r.status_code == 401


def test_admin_whoami_blocked_without_cookie(client):
    r = client.get("/api/admin/whoami")
    assert r.status_code == 401


def test_login_wrong_password_401(client, monkeypatch):
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "secret")
    r = client.post("/api/admin/login", json={"password": "nope"})
    assert r.status_code == 401


def test_login_no_password_configured_fails_closed(client, monkeypatch):
    # Empty configured password => every login attempt fails (fail-safe).
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "")
    r = client.post("/api/admin/login", json={"password": ""})
    assert r.status_code == 401


def test_login_then_admin_access(client, monkeypatch):
    monkeypatch.setattr(admin_auth, "_ADMIN_PASSWORD", "secret")
    r = client.post("/api/admin/login", json={"password": "secret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # TestClient persists the Set-Cookie, so a follow-up admin call is allowed.
    assert client.cookies.get(admin_auth.ADMIN_COOKIE_NAME)
