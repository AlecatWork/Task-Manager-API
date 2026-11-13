"""Shared test fixtures.

Test isolation: these environment variables are set BEFORE the app is imported, so the app itself (not just a dependency override) talks to a throw-away in-memory SQLite database. The real app.db and your .env are never touched.
"""
import os

os.environ["SECRET_KEY"] = "test-secret-key-only-for-pytest-0123456789abcdef"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["NOTIFICATION_DELAY_SECONDS"] = "0"
os.environ["BCRYPT_ROUNDS"] = "4"  # fastest allowed; production default is 12

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.utils.rate_limit import limiter  # noqa: E402

PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def reset_db():
    """Fresh, empty tables for every single test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def rate_limiting_off():
    """Most tests make many requests quickly; rate limiting has its own tests."""
    limiter.reset()
    limiter.enabled = False
    yield
    limiter.enabled = True
    limiter.reset()


@pytest.fixture(autouse=True)
def notification_log(tmp_path, monkeypatch):
    """Send notifications to a temp file so tests never touch the real log."""
    path = tmp_path / "notification_log.txt"
    monkeypatch.setattr(settings, "notification_log_path", str(path))
    return path


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    """A separate session for checking what really reached the database."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register_user(client, email="testuser@example.com", name="Test User", password=PASSWORD):
    """Register a user and return the response (use .json()['access_token'])."""
    return client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    )


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client):
    """Headers for user A (testuser@example.com)."""
    return bearer(register_user(client).json()["access_token"])


@pytest.fixture
def other_auth_headers(client):
    """Headers for a second, different user B."""
    response = register_user(client, email="other@example.com", name="Other User")
    return bearer(response.json()["access_token"])


TASK_PAYLOAD = {
    "title": "Clean",
    "description": "Clean my room monday",
    "priority": "low",
    "completed": False,
}


@pytest.fixture
def sample_task(client, auth_headers):
    """One task owned by user A."""
    response = client.post("/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    assert response.status_code == 201
    return response.json()
