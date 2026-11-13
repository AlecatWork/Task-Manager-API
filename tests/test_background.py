from app.config import settings
from app.utils.notifications import send_notification
from tests.conftest import TASK_PAYLOAD


def log_lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


class TestBackgroundNotifications:
    def test_creating_a_task_logs_a_notification(self, client, auth_headers, notification_log):
        client.post("/tasks", json=TASK_PAYLOAD, headers=auth_headers)
        lines = log_lines(notification_log)
        assert len(lines) == 1
        assert "to=testuser@example.com" in lines[0]  # the user's e-mail
        assert "Task created" in lines[0] and "Clean" in lines[0]

    def test_updating_a_task_logs_with_the_users_email(
        self, client, sample_task, auth_headers, notification_log
    ):
        client.patch(f"/tasks/{sample_task['id']}", json={"completed": True}, headers=auth_headers)
        lines = log_lines(notification_log)
        assert len(lines) == 2  # create + update
        assert "to=testuser@example.com" in lines[1]  # not the numeric user id
        assert "Task updated" in lines[1]

    def test_deleting_a_task_logs_with_the_users_email(
        self, client, sample_task, auth_headers, notification_log
    ):
        client.delete(f"/tasks/{sample_task['id']}", headers=auth_headers)
        lines = log_lines(notification_log)
        assert len(lines) == 2  # create + delete
        assert "to=testuser@example.com" in lines[1]
        assert "Task deleted" in lines[1]

    def test_each_notification_is_on_its_own_line(self, client, auth_headers, notification_log):
        for title in ("one", "two", "three"):
            client.post("/tasks", json={"title": title}, headers=auth_headers)
        assert len(log_lines(notification_log)) == 3
        assert "\\n" not in notification_log.read_text()  # no literal backslash-n

    def test_failed_requests_log_nothing(self, client, auth_headers, notification_log):
        client.post("/tasks", json={"description": "no title"}, headers=auth_headers)
        client.patch("/tasks/9999", json={"title": "x"}, headers=auth_headers)
        client.delete("/tasks/9999", headers=auth_headers)
        assert log_lines(notification_log) == []

    def test_other_users_notifications_go_to_their_own_email(
        self, client, auth_headers, other_auth_headers, notification_log
    ):
        client.post("/tasks", json={"title": "mine"}, headers=other_auth_headers)
        assert "to=other@example.com" in log_lines(notification_log)[0]

    def test_a_title_with_newlines_cannot_forge_log_lines(self, client, auth_headers, notification_log):
        client.post("/tasks", json={"title": "evil\n[fake] to=boss@example.com"}, headers=auth_headers)
        assert len(log_lines(notification_log)) == 1

    def test_notification_failure_never_breaks_the_request(
        self, client, auth_headers, monkeypatch, tmp_path
    ):
        # Point the log at a directory that does not exist: writing will fail.
        monkeypatch.setattr(settings, "notification_log_path", str(tmp_path / "missing" / "log.txt"))
        response = client.post("/tasks", json=TASK_PAYLOAD, headers=auth_headers)
        assert response.status_code == 201

    def test_send_notification_writes_a_timestamped_line(self, notification_log):
        send_notification("someone@example.com", "hello")
        (line,) = log_lines(notification_log)
        assert line.startswith("[") and "to=someone@example.com | hello" in line
