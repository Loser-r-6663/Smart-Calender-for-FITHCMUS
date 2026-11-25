import requests

from DataProcessor.Standardization.ExtractedTask import ExtractedTask
from DataProcessor.Standardization.Task import Task
from Database.Repository.base import BaseSupabaseClient


class UserTaskStateRepository(BaseSupabaseClient):
    """Store per-user scheduling fields for public and private tasks."""

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
        user_id: str | None = None,
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/user_task_state"
        self.user_id = user_id

    def _require_user_id(self) -> str:
        if not self.user_id:
            raise ValueError("user_id is required for user_task_state")
        return str(self.user_id)

    def get_task_states(
        self,
        tasks: list[ExtractedTask],
    ) -> dict[str, dict[str, bool | str]]:
        if not tasks:
            return {}

        params = {
            "select": "id,recurrence,status,compulsory,flexible",
            "user_id": f"eq.{self._require_user_id()}",
            "id": f"in.({','.join(dict.fromkeys([task.id for task in tasks]))})",
        }
        response = requests.get(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)

        fields = ("recurrence", "status", "compulsory", "flexible")
        return {
            row["id"]: {field: row[field] for field in fields}
            for row in response.json()
        }

    def update_tasks(self, tasks: list[Task]) -> requests.Response | None:
        if not tasks:
            return None

        user_id = self._require_user_id()
        rows_by_id: dict[str, dict[str, str | bool]] = {}
        for task in tasks:
            if not isinstance(task, Task):
                raise TypeError("tasks must contain only Task instances")
            if task.id is None:
                raise ValueError("task.id is required to save user task state")

            rows_by_id[task.id] = {
                "id": task.id,
                "user_id": user_id,
                "recurrence": task.recurrence,
                "status": task.status,
                "compulsory": task.compulsory,
                "flexible": task.flexible,
            }

        response = requests.post(
            self.table_url,
            params={"on_conflict": "id,user_id"},
            headers={
                **self.headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            json=list(rows_by_id.values()),
            timeout=30,
        )
        self._raise(response)
        return response
