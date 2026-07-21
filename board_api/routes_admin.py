"""Admin routes: login, create/close use cases, view responses + partners.

On Databricks this ran behind workspace SSO. On Vercel there is no SSO, so a
shared password gates access: POST /api/admin/login mints a signed admin cookie
(public_router, unguarded), and every data route depends on require_admin
(router, guarded). posted_by comes from ADMIN_EMAIL since a shared password
carries no per-user identity.
"""
import os

from fastapi import APIRouter, Depends, Request, Response, HTTPException

from . import db, email
from .admin_auth import (ADMIN_COOKIE_NAME, ADMIN_EMAIL, check_password,
                         make_admin_cookie, require_admin, admin_identity)
from .models import UseCaseIn, StatusIn, AdminLoginIn

# Unguarded: only the login endpoint lives here.
public_router = APIRouter()
# Guarded: every route depends on a valid admin cookie.
router = APIRouter(dependencies=[Depends(require_admin)])

# Public board URL included in the "new use case" email to partners.
BOARD_URL = os.environ.get("BOARD_URL", "https://partner-board.example.com")
# ADMIN_EMAIL is imported from admin_auth (shared definition).

_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
_ADMIN_MAX_AGE = 60 * 60 * 24 * 7  # 7-day admin session


@public_router.post("/api/admin/login")
def login(body: AdminLoginIn, response: Response):
    if not check_password(body.password):
        raise HTTPException(401, "invalid password")
    response.set_cookie(
        ADMIN_COOKIE_NAME, make_admin_cookie(),
        httponly=True, secure=_COOKIE_SECURE, samesite="lax", max_age=_ADMIN_MAX_AGE,
    )
    return {"ok": True}


@router.post("/api/admin/use-cases", status_code=201)
def create_case(body: UseCaseIn, request: Request):
    # posted_by = the actual signed-in Databricks person (their Clerk
    # @databricks.com email). Falls back to ADMIN_EMAIL only for break-glass
    # password logins, which carry no per-user identity. This is also who gets
    # emailed when a partner responds (see routes_public.respond → posted_by).
    poster = admin_identity(request)
    uc = db.create_use_case(body.title, body.description, body.industry,
                            body.region, poster)
    # Notify every registered partner about the new opportunity. The email layer
    # sends one message per partner (see email._fanout), so partners never see
    # one another's addresses.
    recipients = [p["email"] for p in db.list_all_partners()]
    if recipients:
        email.send_new_use_case(recipients, uc["title"], uc["description"], BOARD_URL)
    return uc


@router.patch("/api/admin/use-cases/{uc_id}")
def change_status(uc_id: str, body: StatusIn):
    row = db.set_status(uc_id, body.status)
    if not row:
        raise HTTPException(404, "use case not found")
    return row


@router.get("/api/admin/use-cases")
def list_cases():
    return db.list_all_use_cases()


@router.get("/api/admin/use-cases/{uc_id}/responses")
def list_responses(uc_id: str):
    return db.list_responses_for(uc_id)


@router.get("/api/admin/partners")
def list_partners():
    return db.list_all_partners()


@router.get("/api/admin/whoami")
def whoami(request: Request):
    return {"email": admin_identity(request)}
