"""Signed-cookie sessions for the passwordless partner portal.

No password: after signup the partner_id is signed into a cookie, and the
signature is what proves the session is genuine on later requests. The secret
comes from SESSION_SECRET (set as a Vercel env var in production; a throwaway
default is used locally so tests run without config).
"""
import logging
import os

from itsdangerous import URLSafeSerializer, BadSignature

log = logging.getLogger("portal.sessions")

SESSION_COOKIE_NAME = "pub_session"

_DEV_DEFAULT = "dev-only-not-secret"
_secret = os.environ.get("SESSION_SECRET", _DEV_DEFAULT)
if _secret == _DEV_DEFAULT:
    # Fine for local/tests; a real deploy MUST set SESSION_SECRET or every
    # cookie is signed with a key that's visible in the repo (forgeable).
    log.warning(
        "SESSION_SECRET is unset — using the insecure dev default. "
        "Set SESSION_SECRET in production or sessions can be forged."
    )

_serializer = URLSafeSerializer(_secret, salt="partner-portal")


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
