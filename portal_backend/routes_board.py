"""Public board routes: list open use cases, fetch one."""
from fastapi import APIRouter, HTTPException

from . import db

router = APIRouter()


@router.get("/api/use-cases")
def list_cases():
    return db.list_open_use_cases()


@router.get("/api/use-cases/{uc_id}")
def get_case(uc_id: str):
    uc = db.get_use_case(uc_id)
    # Only open cases are public. A closed (or missing) case is a 404 here so
    # the detail endpoint can't leak closed cases the board list already hides.
    if not uc or uc.get("status") != "open":
        raise HTTPException(404, "use case not found")
    return uc
