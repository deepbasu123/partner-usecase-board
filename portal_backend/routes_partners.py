"""Signup + session-check routes."""
from fastapi import APIRouter, Request, Response, HTTPException

from . import db, email, sessions
from .models import SignupIn

router = APIRouter()

# 30-day cookie.
_MAX_AGE = 60 * 60 * 24 * 30


@router.post("/api/signup")
def signup(body: SignupIn, response: Response):
    partner = db.get_or_create_partner(str(body.email), body.company, body.contact_name)
    response.set_cookie(
        sessions.SESSION_COOKIE_NAME,
        sessions.make_session_cookie(partner["id"]),
        httponly=True, secure=True, samesite="lax", max_age=_MAX_AGE,
    )
    email.send_welcome(partner["email"], partner["company"])
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


@router.get("/api/me")
def me(request: Request):
    pid = sessions.read_session_cookie(request.cookies.get(sessions.SESSION_COOKIE_NAME, ""))
    if not pid:
        raise HTTPException(401, "not signed in")
    return {"id": pid}
