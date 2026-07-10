"""Signed-cookie sessions for the passwordless partner portal.

No password: after signup the partner_id is signed into a cookie, and the
signature is what proves the session is genuine on later requests. The secret
comes from SESSION_SECRET (set as a Cloud Run secret in production; a
throwaway default is used locally so tests run without config).
"""
import os

from itsdangerous import URLSafeSerializer, BadSignature

SESSION_COOKIE_NAME = "pub_session"

_serializer = URLSafeSerializer(
    os.environ.get("SESSION_SECRET", "dev-only-not-secret"),
    salt="partner-portal",
)


def make_session_cookie(partner_id: str) -> str:
    """Return a signed token carrying the partner id."""
    return _serializer.dumps({"pid": partner_id})


def read_session_cookie(token: str):
    """Return the partner id from a valid token, else None."""
    if not token:
        return None
    try:
        return _serializer.loads(token)["pid"]
    except (BadSignature, KeyError, TypeError):
        return None
