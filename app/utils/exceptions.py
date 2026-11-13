"""Application-specific exceptions.

Every one of these is caught by a single global handler in main.py, so every error the API raises on purpose has the same JSON shape:
    {"error": true, "detail": "..."}
"""


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(self, detail: str, status_code: int = 400, headers: dict | None = None):
        self.detail = detail
        self.status_code = status_code
        self.headers = headers
        super().__init__(detail)


class NotFoundException(AppException):
    """Resource not found (404)"""

    def __init__(self, resource: str, resource_id):
        super().__init__(
            detail=f"{resource} with id {resource_id} not found", status_code=404
        )


class DuplicateException(AppException):
    """Duplicate resource conflict (409)"""

    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            detail=f"{resource} with {field} '{value}' already exists", status_code=409
        )


class ForbiddenException(AppException):
    """Authenticated, but not allowed to do this (403)"""

    def __init__(self, detail: str = "You don't have permission"):
        super().__init__(detail=detail, status_code=403)


class UnauthorizedException(AppException):
    """Missing, invalid or expired credentials (401)"""

    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            detail=detail, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )
