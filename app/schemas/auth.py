from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.validators import check_password_bytes, normalize_email


class LoginRequest(BaseModel):
    """What a client sends us to log in."""
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        max_length=255,
        description="User's email (case-insensitive)",
        examples=["KodjoKohn@yahoo.fr"]
    )
    password: str = Field(
        min_length=1, max_length=72,
        description="User's password",
        examples=["Kodjohn65!"]
    )

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        return check_password_bytes(value)


class TokenResponse(BaseModel):
    """The JWT returned after registering or logging in."""
    access_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signature",
                "token_type": "bearer",
            }
        }
    )
