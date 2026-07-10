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
    if not uc:
        raise HTTPException(404, "use case not found")
    return uc
