from sqlalchemy import event

from app.database import engine
from app.models.tasks import Task
from tests.conftest import TASK_PAYLOAD


def create(client, headers, **overrides):
    return client.post("/tasks", json={**TASK_PAYLOAD, **overrides}, headers=headers)


class TestCreateTask:
    def test_create_task_success(self, client, auth_headers):
        response = create(client, auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Clean"
        assert data["description"] == "Clean my room monday"
        assert data["priority"] == "low"
        assert data["completed"] is False
        assert "id" in data and "created_at" in data

    def test_task_is_owned_by_the_creator(self, client, auth_headers):
        me = client.get("/users/me", headers=auth_headers).json()
        assert create(client, auth_headers).json()["user_id"] == me["id"]

    def test_only_title_is_required(self, client, auth_headers):
        response = client.post("/tasks", json={"title": "Just a title"}, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["description"] is None
        assert data["priority"] is None
        assert data["completed"] is False

    def test_task_is_really_saved_in_the_database(self, client, auth_headers, db_session):
        task_id = create(client, auth_headers).json()["id"]
        row = db_session.get(Task, task_id)
        assert row is not None
        assert row.title == "Clean"
        assert row.priority.value == "low"

    def test_title_is_trimmed(self, client, auth_headers):
        assert create(client, auth_headers, title="  Clean  ").json()["title"] == "Clean"

    def test_missing_title_returns_422(self, client, auth_headers):
        response = client.post(
            "/tasks", json={"description": "no title", "priority": "low"}, headers=auth_headers
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"] is True
        assert body["detail"] == "Validation failed"
        assert any(e["field"] == "body -> title" for e in body["errors"])

    def test_blank_title_returns_422(self, client, auth_headers):
        assert create(client, auth_headers, title="   ").status_code == 422

    def test_title_length_limits(self, client, auth_headers):
        assert create(client, auth_headers, title="x" * 200).status_code == 201
        assert create(client, auth_headers, title="x" * 201).status_code == 422

    def test_description_length_limits(self, client, auth_headers):
        assert create(client, auth_headers, description="x" * 2000).status_code == 201
        assert create(client, auth_headers, description="x" * 2001).status_code == 422

    def test_invalid_priority_returns_422(self, client, auth_headers):
        assert create(client, auth_headers, priority="urgent").status_code == 422

    def test_client_cannot_choose_the_owner(self, client, auth_headers):
        assert create(client, auth_headers, user_id=999).status_code == 422

    def test_requires_authentication(self, client):
        response = client.post("/tasks", json=TASK_PAYLOAD)
        assert response.status_code == 401

    def test_trailing_slash_works_without_redirect(self, client, auth_headers):
        response = client.post(
            "/tasks/", json=TASK_PAYLOAD, headers=auth_headers, follow_redirects=False
        )
        assert response.status_code == 201


class TestListTasks:
    def test_empty_list(self, client, auth_headers):
        response = client.get("/tasks", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_with_data(self, client, sample_task, auth_headers):
        response = client.get("/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert [t["title"] for t in data] == ["Clean"]

    def test_requires_authentication(self, client):
        assert client.get("/tasks").status_code == 401

    def test_trailing_slash_works_without_redirect(self, client, auth_headers):
        response = client.get("/tasks/", headers=auth_headers, follow_redirects=False)
        assert response.status_code == 200

    def test_only_returns_own_tasks(self, client, auth_headers, other_auth_headers):
        create(client, auth_headers, title="mine")
        create(client, other_auth_headers, title="theirs")
        mine = client.get("/tasks", headers=auth_headers).json()
        theirs = client.get("/tasks", headers=other_auth_headers).json()
        assert [t["title"] for t in mine] == ["mine"]
        assert [t["title"] for t in theirs] == ["theirs"]

    def test_filter_by_completed(self, client, auth_headers):
        create(client, auth_headers, title="open", completed=False)
        create(client, auth_headers, title="done", completed=True)
        done = client.get("/tasks?completed=true", headers=auth_headers).json()
        todo = client.get("/tasks?completed=false", headers=auth_headers).json()
        assert [t["title"] for t in done] == ["done"]
        assert [t["title"] for t in todo] == ["open"]

    def test_filter_by_priority(self, client, auth_headers):
        create(client, auth_headers, title="a", priority="low")
        create(client, auth_headers, title="b", priority="high")
        high = client.get("/tasks?priority=high", headers=auth_headers).json()
        assert [t["title"] for t in high] == ["b"]

    def test_combined_filters(self, client, auth_headers):
        create(client, auth_headers, title="a", priority="high", completed=True)
        create(client, auth_headers, title="b", priority="high", completed=False)
        create(client, auth_headers, title="c", priority="low", completed=False)
        data = client.get("/tasks?priority=high&completed=false", headers=auth_headers).json()
        assert [t["title"] for t in data] == ["b"]

    def test_pagination_skip_and_limit(self, client, auth_headers):
        for i in range(5):
            create(client, auth_headers, title=f"task {i}")
        page1 = client.get("/tasks?limit=2", headers=auth_headers).json()
        page2 = client.get("/tasks?skip=2&limit=2", headers=auth_headers).json()
        page3 = client.get("/tasks?skip=4&limit=2", headers=auth_headers).json()
        assert [t["title"] for t in page1] == ["task 0", "task 1"]
        assert [t["title"] for t in page2] == ["task 2", "task 3"]
        assert [t["title"] for t in page3] == ["task 4"]

    def test_listing_query_is_ordered_so_pages_are_stable(self, client, auth_headers):
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            client.get("/tasks", headers=auth_headers)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        task_queries = [s for s in statements if "FROM tasks" in s]
        assert task_queries and all("ORDER BY" in s for s in task_queries)

    def test_default_page_size_is_10(self, client, auth_headers):
        for i in range(12):
            create(client, auth_headers, title=f"task {i}")
        assert len(client.get("/tasks", headers=auth_headers).json()) == 10

    def test_invalid_query_values_return_422(self, client, auth_headers):
        for query in ("limit=0", "limit=51", "skip=-1", "priority=urgent", "completed=maybe"):
            response = client.get(f"/tasks?{query}", headers=auth_headers)
            assert response.status_code == 422, query


class TestGetTask:
    def test_get_task_by_id(self, client, sample_task, auth_headers):
        response = client.get(f"/tasks/{sample_task['id']}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Clean"

    def test_not_found_returns_404(self, client, auth_headers):
        response = client.get("/tasks/9999", headers=auth_headers)
        assert response.status_code == 404
        assert response.json() == {"error": True, "detail": "Task with id 9999 not found"}

    def test_non_integer_id_returns_422(self, client, auth_headers):
        assert client.get("/tasks/abc", headers=auth_headers).status_code == 422

    def test_requires_authentication(self, client, sample_task):
        assert client.get(f"/tasks/{sample_task['id']}").status_code == 401

    def test_other_users_task_returns_403(self, client, sample_task, other_auth_headers):
        response = client.get(f"/tasks/{sample_task['id']}", headers=other_auth_headers)
        assert response.status_code == 403
        assert response.json()["error"] is True


class TestUpdateTask:
    def test_patch_task_title(self, client, sample_task, auth_headers):
        response = client.patch(
            f"/tasks/{sample_task['id']}", json={"title": "Updated Title"}, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["description"] == "Clean my room monday"  # untouched
        assert data["priority"] == "low"  # untouched

    def test_patch_several_fields(self, client, sample_task, auth_headers):
        response = client.patch(
            f"/tasks/{sample_task['id']}",
            json={"completed": True, "priority": "high"},
            headers=auth_headers,
        )
        data = response.json()
        assert data["completed"] is True and data["priority"] == "high"
        assert data["title"] == "Clean"

    def test_patch_is_saved_in_the_database(self, client, sample_task, auth_headers, db_session):
        client.patch(f"/tasks/{sample_task['id']}", json={"completed": True}, headers=auth_headers)
        assert db_session.get(Task, sample_task["id"]).completed is True

    def test_priority_and_description_can_be_cleared(self, client, sample_task, auth_headers):
        response = client.patch(
            f"/tasks/{sample_task['id']}",
            json={"priority": None, "description": None},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["priority"] is None
        assert response.json()["description"] is None

    def test_null_title_or_completed_returns_422_not_500(self, client, sample_task, auth_headers):
        for body in ({"title": None}, {"completed": None}):
            response = client.patch(f"/tasks/{sample_task['id']}", json=body, headers=auth_headers)
            assert response.status_code == 422, body

    def test_empty_body_returns_422(self, client, sample_task, auth_headers):
        assert client.patch(f"/tasks/{sample_task['id']}", json={}, headers=auth_headers).status_code == 422

    def test_invalid_values_return_422(self, client, sample_task, auth_headers):
        for body in ({"title": ""}, {"title": "x" * 201}, {"priority": "urgent"}, {"user_id": 5}):
            response = client.patch(f"/tasks/{sample_task['id']}", json=body, headers=auth_headers)
            assert response.status_code == 422, body

    def test_not_found_returns_404(self, client, auth_headers):
        assert client.patch("/tasks/9999", json={"title": "x"}, headers=auth_headers).status_code == 404

    def test_other_users_task_returns_403_and_is_unchanged(
        self, client, sample_task, auth_headers, other_auth_headers
    ):
        response = client.patch(
            f"/tasks/{sample_task['id']}", json={"title": "hacked"}, headers=other_auth_headers
        )
        assert response.status_code == 403
        still = client.get(f"/tasks/{sample_task['id']}", headers=auth_headers).json()
        assert still["title"] == "Clean"

    def test_requires_authentication(self, client, sample_task):
        assert client.patch(f"/tasks/{sample_task['id']}", json={"title": "x"}).status_code == 401


class TestDeleteTask:
    def test_delete_task(self, client, sample_task, auth_headers):
        response = client.delete(f"/tasks/{sample_task['id']}", headers=auth_headers)
        assert response.status_code == 204
        assert response.content == b""

        # verify that it's gone
        assert client.get(f"/tasks/{sample_task['id']}", headers=auth_headers).status_code == 404

    def test_delete_removes_the_database_row(self, client, sample_task, auth_headers, db_session):
        client.delete(f"/tasks/{sample_task['id']}", headers=auth_headers)
        assert db_session.get(Task, sample_task["id"]) is None

    def test_deleting_twice_returns_404(self, client, sample_task, auth_headers):
        client.delete(f"/tasks/{sample_task['id']}", headers=auth_headers)
        assert client.delete(f"/tasks/{sample_task['id']}", headers=auth_headers).status_code == 404

    def test_not_found_returns_404(self, client, auth_headers):
        assert client.delete("/tasks/9999", headers=auth_headers).status_code == 404

    def test_other_users_task_returns_403_and_survives(
        self, client, sample_task, auth_headers, other_auth_headers, db_session
    ):
        response = client.delete(f"/tasks/{sample_task['id']}", headers=other_auth_headers)
        assert response.status_code == 403
        assert db_session.get(Task, sample_task["id"]) is not None

    def test_requires_authentication(self, client, sample_task):
        assert client.delete(f"/tasks/{sample_task['id']}").status_code == 401
