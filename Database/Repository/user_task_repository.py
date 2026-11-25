import requests

from DataProcessor.Standardization.ExtractedTask import ExtractedTask
from Database.Repository.task_repository import TaskRepository


class UserTaskRepository(TaskRepository):
    """
    Repository for personal/user-specific tasks stored in the 'user_task' table.
    Requires user_id to associate tasks with specific users.
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
        user_id: str | None = None
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/user_task"
        self.user_id = user_id
        self.access_token = access_token

    @classmethod
    def task_to_row(cls, task: ExtractedTask, user_id: str | None = None) -> dict:
        row = super().task_to_row(task)
        resolved_user_id = user_id or getattr(task, "user_id", None)
        if not resolved_user_id:
            raise ValueError("user_id is required for user_task")
        row["user_id"] = str(resolved_user_id)
        return row

    def save_tasks(self, tasks: list[ExtractedTask]):
        rows = [self.task_to_row(task, user_id=self.user_id) for task in tasks]
        if not rows:
            return []

        response = requests.post(
            self.table_url,
            headers=self.headers,
            json=rows,
            timeout=30,
        )
        self._raise(response)
        return response

    def get_tasks(self, limit: int = 100) -> list[ExtractedTask]:
        params = {
            "select": "*",
            "limit": limit,
        }
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.get(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return [self.row_to_task(row) for row in response.json()]

    def pop_tasks(self, *, persist, limit: int = 100) -> list[ExtractedTask]:
        """Acknowledge only owner-scoped rows after durable persistence returns."""
        if not self.user_id or not self.access_token:
            raise ValueError("Consumption requires an authenticated owner and token")
        tasks = self.get_tasks(limit=limit)
        if any(task.user_id not in (None, self.user_id) for task in tasks):
            raise ValueError("Personal row belongs to another owner")
        saved_ids = set(persist(tasks))
        acknowledged = [task for task in tasks if task.id in saved_ids]
        if acknowledged:
            self.acknowledge_tasks(acknowledged)
        return tasks

    def acknowledge_tasks(self, tasks: list[ExtractedTask]):
        if not self.user_id or not self.access_token:
            raise ValueError("Acknowledgement requires an authenticated owner and token")
        for task in tasks:
            if task.user_id not in (None, self.user_id) or task.id is None:
                raise ValueError("Acknowledgement requires this owner's persisted rows")
        for task in tasks:
            response = requests.delete(
                self.table_url, headers=self.headers,
                params={"user_id": f"eq.{self.user_id}", "id": f"eq.{task.id}",
                        "updated_at": f"eq.{task.updated_at.isoformat()}"}, timeout=30,
            )
            self._raise(response)

    def delete_tasks(self, tasks: list[ExtractedTask]):
        ids = [task.id for task in tasks if task.id is not None]
        if not ids:
            return

        params = {"id": f"in.({','.join(ids)})"}
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.delete(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return response

    def update_task(self, task_id: str, data: ExtractedTask | dict):
        if isinstance(data, ExtractedTask):
            payload = self.task_to_row(data, user_id=self.user_id)
        elif isinstance(data, dict):
            payload = dict(data)
            resolved_user_id = self.user_id or payload.get("user_id")
            if resolved_user_id is not None:
                payload["user_id"] = str(resolved_user_id)
        else:
            raise TypeError("update needs an ExtractedTask or a dict as the second argument")

        params = {"id": f"eq.{task_id}"}
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.patch(
            self.table_url,
            params=params,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        self._raise(response)
        return response
