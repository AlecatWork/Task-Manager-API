from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.validators import check_password_bytes, normalize_email


class RegisterRequest(BaseModel):
    """What a client sends us to register a new user."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1, max_length=100,
        description="User's name",
        examples=["Kodjo Kohn"]
    )
    email: EmailStr = Field(
        max_length=255,
        description="User's email (case-insensitive, must be unique)",
        examples=["KodjoKohn@yahoo.fr"]
    )
    password: str = Field(
        min_length=8, max_length=72,
        description="User's password (8-72 characters, at most 72 bytes)",
        examples=["Kodjohn65!"]
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        return check_password_bytes(value)


class UserResponse(BaseModel):
    """What we send back for a user. The password (or its hash) is never included."""
    id: int
    name: str
    email: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Kodjo Kohn",
                "email": "kodjokohn@yahoo.fr",
                "is_active": True,
                "created_at": "2026-09-06T00:30:00",
            }
        },
    )
