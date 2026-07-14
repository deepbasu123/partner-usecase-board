"""Public portal routes: signup, session check, board listing, EOI submission.

Merges the former portal_backend routes_partners + routes_board +
routes_responses. No auth beyond the passwordless signed-cookie session.
"""
import os

from fastapi import APIRouter, Request, Response, HTTPException

from . import db, email, sessions
from .models import SignupIn, EoiIn

router = APIRouter()

# 30-day session cookie.
_MAX_AGE = 60 * 60 * 24 * 30
# Secure cookies require https. On by default (production); set
# COOKIE_SECURE=false only for local http testing directly against the backend.
_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"

# Comma-separated shared address(es) that also get notified on each EOI.
_NOTIFY = [e.strip() for e in os.environ.get("EOI_NOTIFY_EMAILS", "").split(",") if e.strip()]


# ── signup + session ─────────────────────────────────────────────────────────

@router.post("/api/signup")
def signup(body: SignupIn, response: Response):
    partner = db.get_or_create_partner(str(body.email), body.company, body.contact_name)
    response.set_cookie(
        sessions.SESSION_COOKIE_NAME,
        sessions.make_session_cookie(partner["id"]),
        httponly=True, secure=_COOKIE_SECURE, samesite="lax", max_age=_MAX_AGE,
    )
    email.send_welcome(partner["email"], partner["company"])
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


@router.get("/api/me")
def me(request: Request):
    pid = sessions.read_session_cookie(request.cookies.get(sessions.SESSION_COOKIE_NAME, ""))
    if not pid:
        raise HTTPException(401, "not signed in")
    partner = db.get_partner(pid)
    if not partner:
        raise HTTPException(401, "session no longer valid")
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


# ── public board ─────────────────────────────────────────────────────────────

@router.get("/api/use-cases")
def list_cases():
    return db.list_open_use_cases()


@router.get("/api/use-cases/{uc_id}")
def get_case(uc_id: str):
    uc = db.get_use_case(uc_id)
    # Only open cases are public. A closed (or missing) case is a 404 so the
    # detail endpoint can't leak closed cases the board list already hides.
    if not uc or uc.get("status") != "open":
        raise HTTPException(404, "use case not found")
    return uc


# ── expression of interest ───────────────────────────────────────────────────

@router.post("/api/use-cases/{uc_id}/responses", status_code=201)
def respond(uc_id: str, body: EoiIn, request: Request):
    pid = sessions.read_session_cookie(request.cookies.get(sessions.SESSION_COOKIE_NAME, ""))
    if not pid:
        raise HTTPException(401, "sign up first")

    uc = db.get_use_case(uc_id)
    if not uc:
        raise HTTPException(404, "no such use case")
    if uc.get("status") != "open":
        raise HTTPException(409, "this use case is closed")

    try:
        response_row = db.create_response(uc_id, pid, body.approach)
    except db.DuplicateResponse:
        raise HTTPException(409, "you've already responded to this use case")

    # Notify the poster plus any shared list. Look up the partner's company for
    # the email body; fall back gracefully if not found.
    partner = db.get_partner(pid) or {"company": "A partner"}
    recipients = list(_NOTIFY)
    poster = uc.get("posted_by") or os.environ.get("EMAIL_FROM")
    if poster and poster not in recipients:
        recipients.append(poster)
    if recipients:
        email.send_new_eoi(recipients, partner["company"], uc["title"], body.approach)

    return response_row
