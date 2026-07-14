"""Shared-password admin gate (replaces Databricks SSO on Vercel).

A correct password mints a signed admin cookie; every /api/admin/* data route
depends on require_admin, which 401s without a valid cookie. The admin JS being
publicly downloadable is harmless because every data call is server-gated.
"""
import hmac
import logging
import os

from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer, BadSignature

log = logging.getLogger("board.admin_auth")

ADMIN_COOKIE_NAME = "admin_session"

_DEV_DEFAULT = "dev-only-not-secret-admin"
_secret = os.environ.get("ADMIN_SESSION_SECRET", _DEV_DEFAULT)
if _secret == _DEV_DEFAULT:
    log.warning(
        "ADMIN_SESSION_SECRET is unset — using the insecure dev default. "
        "Set ADMIN_SESSION_SECRET in production or admin cookies can be forged."
    )

_serializer = URLSafeSerializer(_secret, salt="partner-admin")

# No password configured => gate is effectively closed (every check fails),
# so a misconfigured deploy fails safe rather than open.
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def check_password(pw: str) -> bool:
    """Constant-time compare of a submitted password to the configured one."""
    if not _ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(pw or "", _ADMIN_PASSWORD)


def make_admin_cookie() -> str:
    """Return a signed token proving admin access."""
    return _serializer.dumps({"role": "admin"})


def is_valid_admin(token: str) -> bool:
    if not token:
        return False
    try:
        return _serializer.loads(token).get("role") == "admin"
    except (BadSignature, AttributeError, TypeError):
        return False


def require_admin(request: Request) -> None:
    """FastAPI dependency: 401 unless a valid admin cookie is present."""
    if not is_valid_admin(request.cookies.get(ADMIN_COOKIE_NAME, "")):
        raise HTTPException(401, "admin login required")
