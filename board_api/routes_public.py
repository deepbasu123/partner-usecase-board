"""Public portal routes: identity check, onboarding, board listing, EOI submission.

Auth is gated on Clerk Bearer-token identity (require_identity dependency).
No cookies, no sessions module. Admin auth is separate (routes_admin.py).
"""
import os
from fastapi import APIRouter, HTTPException, Depends

from . import db, email
from .clerk_auth import require_identity
from .models import OnboardingIn, EoiIn

router = APIRouter()

# Comma-separated shared address(es) that also get notified on each EOI.
_NOTIFY = [e.strip() for e in os.environ.get("EOI_NOTIFY_EMAILS", "").split(",") if e.strip()]


# ── identity + onboarding ─────────────────────────────────────────────────────

@router.get("/api/me")
def me(identity: dict = Depends(require_identity)):
    partner = db.get_partner_by_email(identity["email"])
    if not partner:
        return {"onboarding_required": True}
    return {"id": partner["id"], "email": partner["email"], "company": partner["company"]}


@router.post("/api/onboarding", status_code=201)
def onboarding(body: OnboardingIn, identity: dict = Depends(require_identity)):
    partner = db.link_or_create_partner(identity["email"], identity["clerk_user_id"], body.company)
    email.send_welcome(partner["email"], partner["company"])
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
def respond(uc_id: str, body: EoiIn, identity: dict = Depends(require_identity)):
    partner = db.get_partner_by_email(identity["email"])
    if not partner:
        raise HTTPException(401, "complete onboarding first")

    uc = db.get_use_case(uc_id)
    if not uc:
        raise HTTPException(404, "no such use case")
    if uc.get("status") != "open":
        raise HTTPException(409, "this use case is closed")

    try:
        response_row = db.create_response(uc_id, partner["id"], body.approach)
    except db.DuplicateResponse:
        raise HTTPException(409, "you've already responded to this use case")

    recipients = list(_NOTIFY)
    # Notify whoever posted the case; fall back to the admin address (posted_by
    # is set to ADMIN_EMAIL at creation, so the fallback is a safety net only).
    poster = uc.get("posted_by") or os.environ.get("ADMIN_EMAIL")
    if poster and poster not in recipients:
        recipients.append(poster)
    if recipients:
        email.send_new_eoi(recipients, partner["company"], uc["title"], body.approach)
    return response_row
