"""Admin routes: create/close use cases, view responses + partners.

This app runs behind Databricks workspace SSO, so it needs no auth logic of
its own — only authenticated workspace users can reach it. The acting user's
email arrives via the platform's forwarded identity headers, used for
posted_by.
"""
import os

from fastapi import APIRouter, Request, HTTPException

from . import db, email
from .models import UseCaseIn, StatusIn

router = APIRouter()

# Public board URL included in the "new use case" email to partners.
BOARD_URL = os.environ.get("BOARD_URL", "https://partner-board.example.com")


def _acting_user(request: Request) -> str:
    """Email of the signed-in Databricks user (forwarded by the platform)."""
    return (request.headers.get("X-Forwarded-Email")
            or request.headers.get("X-Forwarded-User")
            or os.environ.get("EMAIL_FROM", "admin@example.com"))


@router.post("/api/admin/use-cases", status_code=201)
def create_case(body: UseCaseIn, request: Request):
    uc = db.create_use_case(body.title, body.description, body.industry,
                            body.region, _acting_user(request))
    # Notify every registered partner about the new opportunity.
    recipients = [p["email"] for p in db.list_partners()]
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
    return db.list_partners()


@router.get("/api/admin/whoami")
def whoami(request: Request):
    return {"email": _acting_user(request)}
