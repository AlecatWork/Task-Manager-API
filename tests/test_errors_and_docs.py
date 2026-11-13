from fastapi.testclient import TestClient

from app.main import app
from app.utils.rate_limit import limiter
from tests.conftest import PASSWORD, register_user


class TestConsistentErrorFormat:
    """Every error, whatever raised it, looks like {"error": true, "detail": ...}."""

    def assert_standard(self, response, status):
        assert response.status_code == status
        body = response.json()
        assert body["error"] is True
        assert isinstance(body["detail"], str)

    def test_401(self, client):
        self.assert_standard(client.get("/tasks"), 401)

    def test_login_401(self, client):
        response = client.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
        self.assert_standard(response, 401)

    def test_403(self, client, sample_task, other_auth_headers):
        self.assert_standard(client.get(f"/tasks/{sample_task['id']}", headers=other_auth_headers), 403)

    def test_404_resource(self, client, auth_headers):
        self.assert_standard(client.get("/tasks/9999", headers=auth_headers), 404)

    def test_404_unknown_route(self, client):
        self.assert_standard(client.get("/no-such-page"), 404)

    def test_405_wrong_method(self, client):
        self.assert_standard(client.put("/auth/login"), 405)

    def test_409(self, client):
        register_user(client)
        self.assert_standard(register_user(client), 409)

    def test_422(self, client, auth_headers):
        self.assert_standard(client.post("/tasks", json={}, headers=auth_headers), 422)

    def test_unexpected_crash_returns_500_in_the_same_format(self, monkeypatch):
        def boom(_password):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr("app.routers.auth.hash_password", boom)
        with TestClient(app, raise_server_exceptions=False) as crash_client:
            response = register_user(crash_client)
        self.assert_standard(response, 500)
        assert "simulated crash" not in response.text  # internals are not leaked


class TestRateLimiting:
    def test_register_is_limited_to_5_per_minute(self, client):
        limiter.enabled = True
        limiter.reset()
        statuses = [register_user(client, email=f"user{i}@example.com").status_code for i in range(6)]
        assert statuses == [201, 201, 201, 201, 201, 429]

    def test_429_uses_the_standard_error_format(self, client):
        limiter.enabled = True
        limiter.reset()
        for i in range(5):
            register_user(client, email=f"user{i}@example.com")
        response = register_user(client, email="one-too-many@example.com")
        assert response.status_code == 429
        body = response.json()
        assert body["error"] is True and "Rate limit exceeded" in body["detail"]


class TestCors:
    def test_streamlit_origin_is_allowed(self, client):
        response = client.options(
            "/tasks",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:8501"

    def test_unknown_origin_is_not_allowed(self, client):
        response = client.options(
            "/tasks",
            headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in response.headers


class TestDocumentation:
    def test_swagger_ui_loads(self, client):
        assert client.get("/docs").status_code == 200

    def test_app_metadata(self, client):
        info = client.get("/openapi.json").json()["info"]
        assert info["title"] == "Task Manager API"
        assert info["version"] == "1.0.0"
        assert info["description"].strip()

    def test_every_tag_has_a_description(self, client):
        spec = client.get("/openapi.json").json()
        tags = {t["name"]: t.get("description") for t in spec["tags"]}
        assert set(tags) == {"Authentication", "Tasks", "Users"}
        assert all(tags.values())

    def test_every_endpoint_has_a_docstring_and_summary(self, client):
        spec = client.get("/openapi.json").json()
        for path, methods in spec["paths"].items():
            for method, operation in methods.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get("description", "").strip(), f"{method.upper()} {path} has no docstring"

    def test_all_required_endpoints_exist(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        expected = {
            ("/auth/register", "post"), ("/auth/login", "post"), ("/users/me", "get"),
            ("/tasks", "post"), ("/tasks", "get"),
            ("/tasks/{task_id}", "get"), ("/tasks/{task_id}", "patch"), ("/tasks/{task_id}", "delete"),
            ("/tasks/{task_id}/suggest", "post"),
        }
        assert {(p, m) for p, ms in paths.items() for m in ms} == expected

    def test_response_schemas_never_contain_a_password(self, client):
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        for name in ("UserResponse", "TaskResponse", "TokenResponse", "AISuggestResponse"):
            assert not any("password" in prop for prop in schemas[name]["properties"]), name

    def test_response_schemas_have_examples(self, client):
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        with_examples = [n for n in ("UserResponse", "TaskResponse", "TokenResponse", "AISuggestResponse")
                         if "example" in schemas[n] or "examples" in schemas[n]]
        assert len(with_examples) >= 2
