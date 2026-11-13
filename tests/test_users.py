from tests.conftest import bearer, register_user


class TestMe:
    def test_returns_profile(self, client, auth_headers):
        response = client.get("/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@example.com"
        assert data["name"] == "Test User"
        assert data["is_active"] is True
        assert "id" in data and "created_at" in data

    def test_never_exposes_password_or_hash(self, client, auth_headers):
        data = client.get("/users/me", headers=auth_headers).json()
        assert "password" not in data
        assert "hashed_password" not in data

    def test_requires_authentication(self, client):
        assert client.get("/users/me").status_code == 401

    def test_each_token_returns_its_own_user(self, client, auth_headers, other_auth_headers):
        assert client.get("/users/me", headers=auth_headers).json()["email"] == "testuser@example.com"
        assert client.get("/users/me", headers=other_auth_headers).json()["email"] == "other@example.com"

    def test_login_token_works_too(self, client):
        register_user(client)
        token = client.post(
            "/auth/login", json={"email": "testuser@example.com", "password": "Password123!"}
        ).json()["access_token"]
        assert client.get("/users/me", headers=bearer(token)).status_code == 200
