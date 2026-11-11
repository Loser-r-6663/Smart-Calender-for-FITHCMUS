import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.api_authorization import load_role_config
from Database.api import app, get_database_manager
from Database.user_objects import UserDRLScoresObject


class FakeDatabaseManager:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, object]] = {}
        self.users: dict[int, dict[str, object]] = {}
        self.user_drl: dict[int, dict[str, int]] = {}
        self.next_user_id = 1

    def create_task(self, task_data: dict[str, object]) -> dict[str, object]:
        self.tasks[str(task_data["id"])] = task_data
        return task_data

    def list_tasks(
        self, status: object = None, task_type: object = None
    ) -> list[dict[str, object]]:
        items = list(self.tasks.values())
        if status is not None:
            status_val = getattr(status, "value", status)
            items = [
                item for item in items if item.get("status", "active") == status_val
            ]
        if task_type is not None:
            type_val = getattr(task_type, "value", task_type)
            items = [item for item in items if item.get("type") == type_val]
        return items

    def delete_task(self, task_id: str) -> bool:
        return self.tasks.pop(task_id, None) is not None

    def create_user(
        self, username: str, email: str, full_name: str | None = None
    ) -> dict[str, object]:
        user = {
            "id": self.next_user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
        }
        self.users[self.next_user_id] = user
        self.next_user_id += 1
        return user

    def delete_user(self, user_id: int) -> bool:
        self.user_drl.pop(user_id, None)
        return self.users.pop(user_id, None) is not None

    def get_user_drl_scores(self, user_id: int) -> UserDRLScoresObject | None:
        if user_id not in self.users:
            return None
        return UserDRLScoresObject(user_id=user_id, **self.user_drl.get(user_id, {}))

    def set_user_drl_scores(
        self,
        user_id: int,
        scores: dict[str, int],
        *,
        replace: bool = False,
    ) -> UserDRLScoresObject | None:
        if user_id not in self.users:
            return None
        current = {} if replace else dict(self.user_drl.get(user_id, {}))
        for key, value in scores.items():
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError("Invalid DRL score")
            current[key] = value
        self.user_drl[user_id] = current
        return UserDRLScoresObject(user_id=user_id, **current)


class ApiAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {"ADMIN_API_KEY": "test-admin-key", "LLM_API_KEY": "test-llm-key"},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.database = FakeDatabaseManager()
        app.dependency_overrides[get_database_manager] = lambda: self.database
        self.addCleanup(app.dependency_overrides.clear)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_requests_without_valid_key_are_unauthorized(self) -> None:
        missing_key_response = self.client.post(
            "/tasks",
            json={"id": "test-task", "title": "Test task", "type": "personal"},
        )
        invalid_key_response = self.client.post(
            "/tasks",
            headers={"Authorization": "Bearer invalid-key"},
            json={"id": "test-task", "title": "Test task", "type": "personal"},
        )

        self.assertEqual(missing_key_response.status_code, 401)
        self.assertEqual(invalid_key_response.status_code, 401)
        self.assertEqual(self.database.tasks, {})

    def test_llm_can_create_valid_task_only(self) -> None:
        valid_response = self.client.post(
            "/tasks",
            headers={"Authorization": "Bearer test-llm-key"},
            json={"id": "llm-task", "title": "LLM task", "type": "personal"},
        )
        invalid_response = self.client.post(
            "/tasks",
            headers={"Authorization": "Bearer test-llm-key"},
            json={"id": "invalid-task", "title": " ", "type": "personal"},
        )

        self.assertEqual(valid_response.status_code, 201, valid_response.text)
        self.assertEqual(invalid_response.status_code, 422, invalid_response.text)
        self.assertEqual(set(self.database.tasks), {"llm-task"})

    def test_llm_cannot_use_admin_endpoints(self) -> None:
        headers = {"Authorization": "Bearer test-llm-key"}
        responses = (
            self.client.post(
                "/users",
                headers=headers,
                json={
                    "username": "llm-user",
                    "email": "llm@example.edu",
                },
            ),
            self.client.get("/tasks", headers=headers),
            self.client.get("/tasks/any-task", headers=headers),
            self.client.patch(
                "/tasks/any-task",
                headers=headers,
                json={"title": "Changed title"},
            ),
            self.client.delete("/tasks/any-task", headers=headers),
            self.client.get("/users/1", headers=headers),
            self.client.patch(
                "/users/1",
                headers=headers,
                json={"full_name": "Changed name"},
            ),
            self.client.delete("/users/1", headers=headers),
            self.client.get("/users/1/tasks", headers=headers),
            self.client.get("/users/1/drl", headers=headers),
            self.client.put(
                "/users/1/drl",
                headers=headers,
                json={"dieu_1": 10},
            ),
            self.client.patch(
                "/users/1/drl",
                headers=headers,
                json={"dieu_1": 10},
            ),
            self.client.put(
                "/users/1/tasks/any-task",
                headers=headers,
            ),
            self.client.delete(
                "/users/1/tasks/any-task",
                headers=headers,
            ),
            self.client.get(
                "/users/1/daily-tasks?work_date=2026-11-07",
                headers=headers,
            ),
            self.client.put(
                "/daily-tasks/2026-11-07/any-task",
                headers=headers,
                json={"is_completed_today": False},
            ),
            self.client.patch(
                "/daily-tasks/2026-11-07/any-task/completion",
                headers=headers,
                json={"is_completed": True},
            ),
            self.client.delete(
                "/daily-tasks/2026-11-07/any-task",
                headers=headers,
            ),
        )

        self.assertTrue(all(response.status_code == 403 for response in responses))
        self.assertEqual(self.database.users, {})
        self.assertEqual(self.database.tasks, {})

    def test_admin_can_create_and_delete_tasks_and_users(self) -> None:
        headers = {"Authorization": "Bearer test-admin-key"}
        task_response = self.client.post(
            "/tasks",
            headers=headers,
            json={"id": "admin-task", "title": "Admin task", "type": "personal"},
        )
        user_response = self.client.post(
            "/users",
            headers=headers,
            json={"username": "admin-user", "email": "admin@example.edu"},
        )

        self.assertEqual(task_response.status_code, 201, task_response.text)
        self.assertEqual(user_response.status_code, 201, user_response.text)
        self.assertEqual(
            self.client.delete("/tasks/admin-task", headers=headers).status_code,
            204,
        )
        self.assertEqual(
            self.client.delete("/users/1", headers=headers).status_code,
            204,
        )

    def test_admin_can_list_tasks_with_optional_filters(self) -> None:
        headers = {"Authorization": "Bearer test-admin-key"}
        self.client.post(
            "/tasks",
            headers=headers,
            json={"id": "t-class", "title": "Class task", "type": "class"},
        )
        self.client.post(
            "/tasks",
            headers=headers,
            json={"id": "t-event", "title": "Event task", "type": "event", "status": "done"},
        )

        all_resp = self.client.get("/tasks", headers=headers)
        self.assertEqual(all_resp.status_code, 200, all_resp.text)
        self.assertEqual(
            {item["id"] for item in all_resp.json()}, {"t-class", "t-event"}
        )

        filtered_resp = self.client.get(
            "/tasks?status=done&type=event", headers=headers
        )
        self.assertEqual(filtered_resp.status_code, 200, filtered_resp.text)
        self.assertEqual([item["id"] for item in filtered_resp.json()], ["t-event"])

        bad_resp = self.client.get("/tasks?status=invalid", headers=headers)
        self.assertEqual(bad_resp.status_code, 422)

    def test_admin_can_read_and_update_user_drl_scores(self) -> None:
        headers = {"Authorization": "Bearer test-admin-key"}
        self.assertEqual(
            self.client.get("/users/999/drl", headers=headers).status_code, 404
        )

        self.client.post(
            "/users",
            headers=headers,
            json={"username": "drl-user", "email": "drl@example.edu"},
        )

        initial = self.client.get("/users/1/drl", headers=headers)
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(
            initial.json(),
            {
                "user_id": 1,
                "dieu_1": 0,
                "dieu_2": 0,
                "dieu_3": 0,
                "dieu_4": 0,
                "dieu_5": 0,
            },
        )

        put_resp = self.client.put(
            "/users/1/drl",
            headers=headers,
            json={"dieu_1": 22, "dieu_4": 15},
        )
        self.assertEqual(put_resp.status_code, 200, put_resp.text)
        self.assertEqual(put_resp.json()["dieu_1"], 22)
        self.assertEqual(put_resp.json()["dieu_4"], 15)
        self.assertEqual(put_resp.json()["dieu_2"], 0)

        patch_resp = self.client.patch(
            "/users/1/drl",
            headers=headers,
            json={"dieu_2": 18},
        )
        self.assertEqual(patch_resp.status_code, 200, patch_resp.text)
        self.assertEqual(patch_resp.json()["dieu_1"], 22)
        self.assertEqual(patch_resp.json()["dieu_2"], 18)

        bad_patch = self.client.patch(
            "/users/1/drl",
            headers=headers,
            json={"dieu_1": True},
        )
        self.assertEqual(bad_patch.status_code, 422)

    def test_equal_role_keys_disable_authorization(self) -> None:
        with patch.dict(
            os.environ,
            {"ADMIN_API_KEY": "same-key", "LLM_API_KEY": "same-key"},
        ):
            response = self.client.post(
                "/tasks",
                headers={"Authorization": "Bearer same-key"},
                json={"id": "test-task", "title": "Test task", "type": "personal"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.database.tasks, {})

    def test_role_permissions_are_loaded_from_json_configuration(self) -> None:
        roles = load_role_config()

        self.assertEqual(roles["admin"]["permissions"], ["*"])
        self.assertEqual(roles["llm"]["permissions"], ["tasks:create"])
        self.assertEqual(roles["admin"]["api_key_env"], "ADMIN_API_KEY")
        self.assertEqual(roles["llm"]["api_key_env"], "LLM_API_KEY")


if __name__ == "__main__":
    unittest.main()
