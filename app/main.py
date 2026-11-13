"""
Task Manager API - application entry point.

Security measures:
- CORS restricted to known frontend origins (default: http://localhost:8501 for
  Streamlit, plus http://localhost:3000); configurable through CORS_ORIGINS.
- CORS methods restricted to the HTTP methods the API uses.
- slowapi rate limiting per client IP (see each endpoint's docstring).
- Passwords hashed with bcrypt; JWTs signed and expiring.
- Pydantic schemas enforce lengths, enums, e-mail format and reject unknown fields.
- Every protected endpoint requires a Bearer token; users can only touch their own tasks.
- Every error response - application errors, validation errors, 401/404/405,
  rate limiting and unexpected crashes - uses the same JSON shape:
  {"error": true, "detail": "..."}.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import init_db
from app.routers import auth, tasks, users
from app.utils.exceptions import AppException
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

tags_metadata = [
    {
        "name": "Authentication",
        "description": "User registration and login. All protected endpoints require a Bearer token.",
    },
    {
        "name": "Tasks",
        "description": "Create, read, update and delete your own tasks, plus a placeholder AI suggestion. All endpoints require authentication.",
    },
    {
        "name": "Users",
        "description": "The authenticated user's profile.",
    },
]

DESCRIPTION = """
A full-featured task management API with JWT authentication, Pydantic validation and SQLAlchemy persistence.

## Quick Start
1. Register with `POST /auth/register` (or log in with `POST /auth/login`)
2. Copy the `access_token` from the response
3. Click **Authorize** above and paste the token
4. Start creating and managing tasks
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create missing tables when the server starts
    yield


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Routers
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(auth.router)


# ---- Global exception handlers: one consistent JSON error format ----------

def error_response(status_code: int, detail, headers: dict | None = None, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": True, "detail": detail, **extra},
        headers=headers,
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return error_response(exc.status_code, exc.detail, exc.headers)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Covers framework-raised errors such as unknown routes (404) or wrong methods (405).
    return error_response(exc.status_code, exc.detail, getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": " -> ".join(str(part) for part in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return error_response(422, "Validation failed", errors=errors)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return error_response(429, f"Rate limit exceeded: {exc.detail}")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "Internal server error")
