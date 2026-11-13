"""Password hashing (bcrypt), JWT creation and the get_current_user dependency."""
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.tasks import User
from app.utils.exceptions import ForbiddenException, UnauthorizedException


http_bearer = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by /auth/register or /auth/login.",
)

# A real bcrypt hash of a random string. Login verifies against it when the email is unknown so that "unknown email" and "wrong password" take the same time and cannot be told apart.
DUMMY_HASH = "$2b$12$nhzT91rOyLWGvDMZkKYkM.lMBFrR/fxMej7F/GjtiP5YXCkDkyInC"


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash. Callers must keep passwords <= 72 bytes."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:  # malformed hash or over-long password
        return False


def create_access_token(data: dict) -> str:
    """Create a signed JWT that expires after ACCESS_TOKEN_EXPIRE_MINUTES."""
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    to_encode.update(
        {
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        }
    )
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate the Bearer JWT and return the matching active user."""
    if credentials is None:
        raise UnauthorizedException("Not authenticated")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require_exp": True, "require_sub": True},
        )
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise UnauthorizedException("Invalid or expired token")

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise ForbiddenException("Inactive user")
    return user
