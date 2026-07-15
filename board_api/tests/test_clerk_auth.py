"""clerk_auth tests: mint a local RS256 JWT, inject the public key as the
'signing key', and assert verify_token + require_identity behave. No network,
no real Clerk."""
import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from board_api import clerk_auth

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(claims):
    claims = {"exp": int(time.time()) + 3600, **claims}
    return jwt.encode(claims, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _inject_key(monkeypatch):
    # verify_token calls _signing_key(token) to get the verifying key.
    monkeypatch.setattr(clerk_auth, "_signing_key", lambda token: _KEY.public_key())


def _request_with(auth_header):
    scope = {"type": "http", "headers": []}
    if auth_header is not None:
        scope["headers"] = [(b"authorization", auth_header.encode())]
    return Request(scope)


def test_verify_token_returns_claims():
    tok = _make_token({"sub": "user_123", "email": "a@x.com"})
    claims = clerk_auth.verify_token(tok)
    assert claims["sub"] == "user_123"
    assert claims["email"] == "a@x.com"


def test_require_identity_returns_email_and_id():
    tok = _make_token({"sub": "user_123", "email": "a@x.com"})
    ident = clerk_auth.require_identity(_request_with(f"Bearer {tok}"))
    assert ident == {"email": "a@x.com", "clerk_user_id": "user_123"}


def test_require_identity_401_without_header():
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with(None))
    assert e.value.status_code == 401


def test_require_identity_401_on_garbage_token():
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with("Bearer not.a.jwt"))
    assert e.value.status_code == 401


def test_require_identity_401_when_email_claim_missing():
    tok = _make_token({"sub": "user_123"})  # no email → cannot link partner
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with(f"Bearer {tok}"))
    assert e.value.status_code == 401


def test_require_identity_401_when_sub_claim_missing():
    tok = _make_token({"email": "a@x.com"})  # no sub → cannot form clerk_user_id
    with pytest.raises(HTTPException) as e:
        clerk_auth.require_identity(_request_with(f"Bearer {tok}"))
    assert e.value.status_code == 401
