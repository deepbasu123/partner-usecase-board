"""EOI submission route (requires a session)."""
import os

from fastapi import APIRouter, Request, HTTPException

from . import db, email, sessions
from .models import EoiIn

router = APIRouter()

# Comma-separated shared address(es) that also get notified on each EOI.
_NOTIFY = [e.strip() for e in os.environ.get("EOI_NOTIFY_EMAILS", "").split(",") if e.strip()]


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

    # Notify the poster plus any shared list. Look up the partner's company
    # for the email body; fall back gracefully if not found.
    partner = db.get_partner(pid) or {"company": "A partner"}
    recipients = list(_NOTIFY)
    poster = uc.get("posted_by") or os.environ.get("EMAIL_FROM")
    if poster and poster not in recipients:
        recipients.append(poster)
    if recipients:
        email.send_new_eoi(recipients, partner["company"], uc["title"], body.approach)

    return response_row
