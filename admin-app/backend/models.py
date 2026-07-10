"""Request models for the admin API."""
from typing import Literal

from pydantic import BaseModel, field_validator


class UseCaseIn(BaseModel):
    title: str
    description: str
    industry: str | None = None
    region: str | None = None

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required")
        return v.strip()


class StatusIn(BaseModel):
    status: Literal["open", "closed"]
