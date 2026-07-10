"""Signup + session-check routes."""
import os

from fastapi import APIRouter, Request, Response, HTTPException

from . import db, email, sessions
from .models import SignupIn

router = APIRouter()

# 30-day cookie.
_MAX_AGE = 60 * 60 * 24 * 30
# Secure cookies require https. On by default (production); set
# COOKIE_SECURE=false only for local http testing directly against the backend.
_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"


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
        # Stale cookie for a partner that no longer exists.
        raise HTTPException(401, "session no longer valid")
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}
