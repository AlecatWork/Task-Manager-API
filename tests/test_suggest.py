class TestSuggest:
    def test_returns_placeholder_without_a_body(self, client, sample_task, auth_headers):
        response = client.post(f"/tasks/{sample_task['id']}/suggest", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == sample_task["id"]
        assert data["is_placeholder"] is True
        assert "Clean" in data["suggestion"]
        assert "Clean my room monday" in data["suggestion"]  # stored description

    def test_uses_the_description_sent_in_the_body(self, client, sample_task, auth_headers):
        response = client.post(
            f"/tasks/{sample_task['id']}/suggest",
            json={"description": "Plan the quarterly report"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "Plan the quarterly report" in response.json()["suggestion"]

    def test_works_for_a_task_without_description(self, client, auth_headers):
        task = client.post("/tasks", json={"title": "Bare"}, headers=auth_headers).json()
        assert client.post(f"/tasks/{task['id']}/suggest", headers=auth_headers).status_code == 200

    def test_invalid_body_returns_422(self, client, sample_task, auth_headers):
        response = client.post(
            f"/tasks/{sample_task['id']}/suggest", json={"description": ""}, headers=auth_headers
        )
        assert response.status_code == 422

    def test_not_found_returns_404(self, client, auth_headers):
        assert client.post("/tasks/9999/suggest", headers=auth_headers).status_code == 404

    def test_other_users_task_returns_403(self, client, sample_task, other_auth_headers):
        response = client.post(f"/tasks/{sample_task['id']}/suggest", headers=other_auth_headers)
        assert response.status_code == 403

    def test_requires_authentication(self, client, sample_task):
        assert client.post(f"/tasks/{sample_task['id']}/suggest").status_code == 401
