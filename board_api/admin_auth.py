"""Shared-password admin gate (replaces Databricks SSO on Vercel).

A correct password mints a signed admin cookie; every /api/admin/* data route
depends on require_admin, which 401s without a valid cookie. The admin JS being
publicly downloadable is harmless because every data call is server-gated.

Task 1 extension: require_admin also accepts a valid @databricks.com Clerk JWT
in the Authorization: Bearer header, so Databricks employees can reach admin
routes without the shared password.
"""
import hmac
import logging
import os

from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer, BadSignature

from . import clerk_auth

log = logging.getLogger("board.admin_auth")

ADMIN_COOKIE_NAME = "admin_session"

_DEV_DEFAULT = "dev-only-not-secret-admin"
_secret = os.environ.get("ADMIN_SESSION_SECRET", _DEV_DEFAULT)
if _secret == _DEV_DEFAULT:
    log.warning(
        "ADMIN_SESSION_SECRET is unset - using the insecure dev default. "
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


def is_databricks_email(email) -> bool:
    """True only for exact ...@databricks.com addresses (case-insensitive)."""
    if not email:
        return False
    return email.strip().lower().endswith("@databricks.com")


def _databricks_clerk_email(request) -> str | None:
    """Return the verified Clerk email IFF it's a @databricks.com address, else None.

    Any verification failure returns None so require_admin falls through to the
    cookie check and ultimately 401 - never grants admin on a bad token.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    try:
        claims = clerk_auth.verify_token(token)
    except Exception:
        return None
    email = claims.get("email")
    return email if is_databricks_email(email) else None


def require_admin(request: Request) -> None:
    """Pass on a valid admin cookie OR a valid @databricks.com Clerk JWT."""
    if is_valid_admin(request.cookies.get(ADMIN_COOKIE_NAME, "")):
        return
    if _databricks_clerk_email(request):
        return
    raise HTTPException(401, "admin login required")


ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")


def admin_identity(request: Request) -> str:
    """Effective admin email: the Clerk email if Clerk-authed, else ADMIN_EMAIL."""
    return _databricks_clerk_email(request) or ADMIN_EMAIL
