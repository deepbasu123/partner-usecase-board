"""Clerk session-JWT verification for the partner portal.

Networkless: the JWT signature is checked against Clerk's JWKS (public keys),
which PyJWKClient fetches once and caches. No per-request call to Clerk. Replaces
the old signed-cookie session for partner-gated routes. Admin auth is separate.
"""
import os

import jwt
from jwt import PyJWKClient
from fastapi import Request, HTTPException

_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
_ISSUER = os.environ.get("CLERK_ISSUER") or None

_jwks_client = PyJWKClient(_JWKS_URL) if _JWKS_URL else None


def _client() -> PyJWKClient:
    if _jwks_client is None:
        raise RuntimeError("CLERK_JWKS_URL not set")
    return _jwks_client


def _signing_key(token: str):
    """Resolve the verifying key for this token from the JWKS. Patched in tests."""
    return _client().get_signing_key_from_jwt(token).key


def verify_token(token: str) -> dict:
    """Return verified claims, or raise (bad signature / expired / wrong issuer)."""
    key = _signing_key(token)
    return jwt.decode(
        token, key, algorithms=["RS256"],
        issuer=_ISSUER, options={"verify_aud": False},
    )


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = auth[len("Bearer "):]
    if not token:
        raise HTTPException(401, "missing bearer token")
    return token


def require_identity(request: Request) -> dict:
    """FastAPI dependency: verified {email, clerk_user_id} or 401.

    Email must be present (Clerk session token is configured to include it); it's
    the key we link partner profiles on.
    """
    token = _bearer(request)
    try:
        claims = verify_token(token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "invalid token")
    email = claims.get("email")
    sub = claims.get("sub")
    if not email or not sub:
        raise HTTPException(401, "token missing required claims")
    return {"email": email, "clerk_user_id": sub}
