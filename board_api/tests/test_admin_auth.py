"""Admin gate tests: routes blocked without a cookie; login mints one.

Also tests the Clerk JWT + @databricks.com domain-rule auth path added in Task 1.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from board_api.app import app
from board_api import admin_auth, clerk_auth, routes_admin

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _tok(claims):
    return jwt.encode({"exp": int(time.time()) + 3600, "sub": "u1", **claims}, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _inject_key(monkeypatch):
    monkeypatch.setattr(clerk_auth, "_signing_key", lambda token: _KEY.public_key())


def _req(headers=None, cookies=None):
    scope = {"type": "http", "headers": []}
    hs = []
    if headers:
        for k, v in headers.items():
            hs.append((k.lower().encode(), v.encode()))
    if cookies:
        cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
        hs.append((b"cookie", cookie.encode()))
    scope["headers"] = hs
    return Request(scope)


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


# --- domain rule ---
@pytest.mark.parametrize("email,expected", [
    ("a@databricks.com", True),
    ("A@Databricks.COM", True),
    ("  a@databricks.com  ", True),
    ("a@sub.databricks.com", False),
    ("a@notdatabricks.com", False),
    ("a@databricks.com.evil.com", False),
    ("", False),
    (None, False),
])
def test_is_databricks_email(email, expected):
    assert admin_auth.is_databricks_email(email) is expected


# --- require_admin ---
def test_require_admin_accepts_databricks_clerk_token():
    req = _req(headers={"Authorization": f"Bearer {_tok({'email': 'sa@databricks.com'})}"})
    admin_auth.require_admin(req)  # must not raise


def test_require_admin_rejects_non_databricks_clerk_token():
    req = _req(headers={"Authorization": f"Bearer {_tok({'email': 'partner@gmail.com'})}"})
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(req)
    assert e.value.status_code == 401


def test_require_admin_still_accepts_password_cookie():
    cookie = admin_auth.make_admin_cookie()
    req = _req(cookies={admin_auth.ADMIN_COOKIE_NAME: cookie})
    admin_auth.require_admin(req)  # must not raise


def test_require_admin_401_with_neither():
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(_req())
    assert e.value.status_code == 401


def test_require_admin_rejects_garbage_token():
    req = _req(headers={"Authorization": "Bearer not.a.jwt"})
    with pytest.raises(HTTPException) as e:
        admin_auth.require_admin(req)
    assert e.value.status_code == 401
