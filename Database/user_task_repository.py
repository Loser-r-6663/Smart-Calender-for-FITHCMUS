import requests

from Backend.Regulation.ExtractedTask import ExtractedTask
from Database.task_repository import TaskRepository


class UserTaskRepository(TaskRepository):
    """
    Repository for personal/user-specific tasks stored in the 'user_task' table.
    Requires user_id to associate tasks with specific users.
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ):
        super().__init__(
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            table_name="user_task",
        )

    @classmethod
    def task_to_row(cls, task: ExtractedTask, user_id: str | None = None) -> dict:
        row = super().task_to_row(task)
        resolved_user_id = user_id or getattr(task, "user_id", None)
        if not resolved_user_id:
            raise ValueError("user_id is required for user_task")
        row["user_id"] = str(resolved_user_id)
        return row

    def save(self, tasks: list[ExtractedTask], user_id: str | None = None):
        rows = [self.task_to_row(task, user_id=user_id) for task in tasks]
        if not rows:
            return []

        response = requests.post(
            self.table_url,
            headers=self.headers,
            json=rows,
            timeout=30,
        )
        response.raise_for_status()
        return response

    def get(self, user_id: str | None = None, limit: int = 100) -> list[ExtractedTask]:
        params = {
            "select": "*",
            "limit": limit,
        }
        if user_id is not None:
            params["user_id"] = f"eq.{user_id}"

        response = requests.get(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return [self.row_to_task(row) for row in response.json()]

    def delete(self, tasks: list[ExtractedTask], user_id: str | None = None):
        ids = [task.id for task in tasks if task.id is not None]
        if not ids:
            return

        params = {"id": f"in.({','.join(ids)})"}
        if user_id is not None:
            params["user_id"] = f"eq.{user_id}"

        response = requests.delete(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response

    def delete_by_user(self, user_id: str):
        if not user_id:
            raise ValueError("user_id must not be empty")

        response = requests.delete(
            self.table_url,
            params={"user_id": f"eq.{user_id}"},
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response

    def update(self, task_id: str, data: ExtractedTask | dict, user_id: str | None = None):
        if isinstance(data, ExtractedTask):
            payload = self.task_to_row(data, user_id=user_id)
        elif isinstance(data, dict):
            payload = dict(data)
            resolved_user_id = user_id or payload.get("user_id")
            if resolved_user_id is not None:
                payload["user_id"] = str(resolved_user_id)
        else:
            raise TypeError("update needs an ExtractedTask or a dict as the second argument")

        params = {"id": f"eq.{task_id}"}
        if user_id is not None:
            params["user_id"] = f"eq.{user_id}"

        response = requests.patch(
            self.table_url,
            params=params,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response
