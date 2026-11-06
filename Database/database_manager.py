from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, TypeVar

from Database.daily_tasks import DailyTaskRepository
from Database.db_connection import DatabaseConnection
from Database.tasks import TaskRepository
from Database.user_tasks import UserTaskRepository
from Database.users import UserRepository


Result = TypeVar("Result")


class DatabaseManager:
    def __init__(self, database: DatabaseConnection | None = None) -> None:
        self.database = database or DatabaseConnection()
        self.tasks = TaskRepository()
        self.users = UserRepository()
        self.user_tasks = UserTaskRepository()
        self.daily_tasks = DailyTaskRepository()

    def _run(self, operation: Callable[..., Result], *args: Any) -> Result:
        with self.database.transaction() as db_connection:
            return operation(db_connection, *args)

    def create_task(self, task_data: Mapping[str, Any]) -> dict[str, Any]:
        return self._run(self.tasks.create, task_data)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._run(self.tasks.get_by_id, task_id)

    def update_task(
        self, task_id: str, updates: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return self._run(self.tasks.update, task_id, updates)

    def delete_task(self, task_id: str) -> bool:
        return self._run(self.tasks.delete, task_id)

    def create_user(
        self, username: str, email: str, full_name: str | None = None
    ) -> dict[str, Any]:
        return self._run(self.users.create, username, email, full_name)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        return self._run(self.users.get_by_id, user_id)

    def update_user(
        self, user_id: int, updates: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return self._run(self.users.update, user_id, updates)

    def delete_user(self, user_id: int) -> bool:
        return self._run(self.users.delete, user_id)

    def assign_task(self, user_id: int, task_id: str) -> bool:
        return self._run(self.user_tasks.assign, user_id, task_id)

    def get_user_tasks(self, user_id: int) -> list[dict[str, Any]]:
        return self._run(self.user_tasks.get_for_user, user_id)

    def unassign_task(self, user_id: int, task_id: str) -> bool:
        return self._run(self.user_tasks.unassign, user_id, task_id)

    def set_daily_task(
        self,
        user_id: int,
        work_date: date,
        task_id: str,
        is_completed_today: bool = False,
    ) -> dict[str, Any]:
        return self._run(
            self.daily_tasks.set_for_date,
            user_id,
            work_date,
            task_id,
            is_completed_today,
        )

    def get_tasks_by_date(
        self, user_id: int, work_date: date
    ) -> list[dict[str, Any]]:
        return self._run(self.daily_tasks.get_for_user_date, user_id, work_date)

    def set_daily_task_completion(
        self,
        user_id: int,
        work_date: date,
        task_id: str,
        is_completed: bool,
    ) -> dict[str, Any] | None:
        return self._run(
            self.daily_tasks.set_completion,
            user_id,
            work_date,
            task_id,
            is_completed,
        )

    def remove_daily_task(
        self, user_id: int, work_date: date, task_id: str
    ) -> bool:
        return self._run(self.daily_tasks.remove, user_id, work_date, task_id)
