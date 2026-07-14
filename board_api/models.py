"""Request models for the merged Partner Board API (public + admin)."""
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


class SignupIn(BaseModel):
    email: EmailStr
    company: str
    contact_name: str | None = None

    @field_validator("company")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("company is required")
        return v.strip()


class EoiIn(BaseModel):
    approach: str

    @field_validator("approach")
    @classmethod
    def approach_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("approach is required")
        return v.strip()


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


class AdminLoginIn(BaseModel):
    password: str
