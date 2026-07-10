"""Request models for the partner portal API."""
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
