from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.models.tasks import User
from app.utils.security import hash_password, verify_password
from tests.conftest import PASSWORD, bearer, register_user


def make_token(sub="1", expires_in=timedelta(minutes=5), secret=None):
    claims = {"exp": datetime.now(timezone.utc) + expires_in}
    if sub is not None:
        claims["sub"] = sub
    return jwt.encode(claims, secret or settings.secret_key, algorithm=settings.algorithm)


class TestRegister:
    def test_register_returns_token(self, client):
        response = register_user(client)
        assert response.status_code == 201
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert set(data) == {"access_token", "token_type"}  # nothing else leaks

    def test_registered_token_works_immediately(self, client):
        token = register_user(client).json()["access_token"]
        assert client.get("/users/me", headers=bearer(token)).status_code == 200

    def test_duplicate_email_returns_409_in_standard_format(self, client):
        register_user(client)
        response = register_user(client)
        assert response.status_code == 409
        body = response.json()
        assert body["error"] is True
        assert "already exists" in body["detail"]

    def test_duplicate_email_ignores_upper_and_lower_case(self, client):
        register_user(client, email="Case@Example.com")
        assert register_user(client, email="case@example.COM").status_code == 409

    def test_email_is_stored_lowercase(self, client, db_session):
        register_user(client, email="MiXed@Example.com")
        assert db_session.query(User).one().email == "mixed@example.com"

    def test_invalid_email_returns_422(self, client):
        response = register_user(client, email="not-an-email")
        assert response.status_code == 422
        assert response.json()["error"] is True

    def test_short_password_returns_422(self, client):
        assert register_user(client, password="short").status_code == 422

    def test_password_over_72_bytes_returns_422_not_500(self, client):
        # 40 characters but 80 bytes in UTF-8: bcrypt cannot hash this.
        assert register_user(client, password="é" * 40).status_code == 422

    def test_missing_fields_return_422_with_field_names(self, client):
        response = client.post("/auth/register", json={"email": "a@example.com"})
        assert response.status_code == 422
        fields = [e["field"] for e in response.json()["errors"]]
        assert "body -> name" in fields and "body -> password" in fields

    def test_unknown_fields_are_rejected(self, client):
        response = client.post(
            "/auth/register",
            json={"name": "X", "email": "x@example.com", "password": PASSWORD, "is_active": False},
        )
        assert response.status_code == 422

    def test_password_is_stored_hashed_never_plaintext(self, client, db_session):
        register_user(client)
        user = db_session.query(User).one()
        assert user.hashed_password != PASSWORD
        assert PASSWORD not in user.hashed_password
        assert user.hashed_password.startswith("$2")  # bcrypt
        assert verify_password(PASSWORD, user.hashed_password)
        assert not verify_password("wrong-password", user.hashed_password)


class TestLogin:
    def test_login_success(self, client):
        register_user(client)
        response = client.post(
            "/auth/login", json={"email": "testuser@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"

    def test_login_email_is_case_insensitive(self, client):
        register_user(client)
        response = client.post(
            "/auth/login", json={"email": "TESTUSER@Example.com", "password": PASSWORD}
        )
        assert response.status_code == 200

    def test_wrong_password_returns_401(self, client):
        register_user(client)
        response = client.post(
            "/auth/login", json={"email": "testuser@example.com", "password": "WrongPass123!"}
        )
        assert response.status_code == 401
        assert response.json() == {"error": True, "detail": "Invalid email or password"}

    def test_unknown_email_gives_same_401_as_wrong_password(self, client):
        register_user(client)
        wrong_password = client.post(
            "/auth/login", json={"email": "testuser@example.com", "password": "WrongPass123!"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
        )
        assert unknown_email.status_code == 401
        assert unknown_email.json() == wrong_password.json()  # no user enumeration

    def test_login_with_invalid_body_returns_422(self, client):
        assert client.post("/auth/login", json={"email": "bad"}).status_code == 422

    def test_inactive_user_cannot_log_in(self, client, db_session):
        register_user(client)
        db_session.query(User).update({"is_active": False})
        db_session.commit()
        response = client.post(
            "/auth/login", json={"email": "testuser@example.com", "password": PASSWORD}
        )
        assert response.status_code == 403


class TestTokenValidation:
    def test_no_token_returns_401_with_www_authenticate(self, client):
        response = client.get("/users/me")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"] is True

    def test_garbage_token_returns_401(self, client):
        assert client.get("/users/me", headers=bearer("not.a.jwt")).status_code == 401

    def test_expired_token_returns_401(self, client):
        register_user(client)
        token = make_token(sub="1", expires_in=timedelta(minutes=-1))
        response = client.get("/users/me", headers=bearer(token))
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_token_signed_with_wrong_secret_returns_401(self, client):
        register_user(client)
        token = make_token(sub="1", secret="x" * 40)
        assert client.get("/users/me", headers=bearer(token)).status_code == 401

    def test_token_without_expiry_is_rejected(self, client):
        register_user(client)
        token = jwt.encode({"sub": "1"}, settings.secret_key, algorithm=settings.algorithm)
        assert client.get("/users/me", headers=bearer(token)).status_code == 401

    def test_non_numeric_subject_returns_401_not_500(self, client):
        assert client.get("/users/me", headers=bearer(make_token(sub="abc"))).status_code == 401

    def test_token_for_deleted_user_returns_401(self, client):
        register_user(client)
        assert client.get("/users/me", headers=bearer(make_token(sub="9999"))).status_code == 401

    def test_inactive_user_with_valid_token_gets_403(self, client, db_session):
        token = register_user(client).json()["access_token"]
        db_session.query(User).update({"is_active": False})
        db_session.commit()
        assert client.get("/users/me", headers=bearer(token)).status_code == 403

    def test_token_expiry_is_set_from_settings(self, client):
        token = register_user(client).json()["access_token"]
        claims = jwt.get_unverified_claims(token)
        lifetime = claims["exp"] - claims["iat"]
        assert lifetime == settings.access_token_expire_minutes * 60


class TestLegacyMixedCaseEmails:
    """Rows saved before emails were normalised may contain upper-case letters."""

    def add_legacy_user(self, db_session):
        db_session.add(User(name="Old", email="Legacy@Example.com", hashed_password=hash_password(PASSWORD)))
        db_session.commit()

    def test_legacy_user_can_still_log_in(self, client, db_session):
        self.add_legacy_user(db_session)
        response = client.post("/auth/login", json={"email": "legacy@example.com", "password": PASSWORD})
        assert response.status_code == 200

    def test_registering_a_legacy_email_is_a_duplicate(self, client, db_session):
        self.add_legacy_user(db_session)
        assert register_user(client, email="legacy@example.com").status_code == 409
