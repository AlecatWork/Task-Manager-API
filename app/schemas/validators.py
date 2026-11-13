"""Validation helpers shared by several schemas."""

# bcrypt only looks at the first 72 *bytes* of a password (and newer versions
# refuse longer input), so over-long passwords are rejected up front.
MAX_PASSWORD_BYTES = 72


def check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded")
    return value


def normalize_email(value: str) -> str:
    """Emails are compared case-insensitively, so store them lower-cased."""
    return value.strip().lower()
