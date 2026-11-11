from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, TypeVar

from Database.daily_tasks import DailyTaskRepository
from Database.db_connection import DatabaseConnection
from Database.daily_task_objects import DailyTaskObject
from Database.enums import TaskStatus, TaskType
from Database.task_objects import TaskObject
from Database.tasks import TaskRepository
from Database.user_tasks import UserTaskRepository
from Database.user_objects import UserObject, UserTaskObject
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

    def get_task(self, task_id: str) -> TaskObject | None:
        record = self._run(self.tasks.get_by_id, task_id)
        return TaskObject.from_record(record) if record is not None else None

    def list_tasks(
        self,
        status: TaskStatus | str | None = None,
        task_type: TaskType | str | None = None,
    ) -> list[TaskObject]:
        records = self._run(self.tasks.list_tasks, status, task_type)
        return [TaskObject.from_record(record) for record in records]

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

    def get_user(self, user_id: int) -> UserObject | None:
        record = self._run(self.users.get_by_id, user_id)
        return UserObject.from_record(record) if record is not None else None

    def update_user(
        self, user_id: int, updates: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return self._run(self.users.update, user_id, updates)

    def delete_user(self, user_id: int) -> bool:
        return self._run(self.users.delete, user_id)

    def assign_task(self, user_id: int, task_id: str) -> bool:
        return self._run(self.user_tasks.assign, user_id, task_id)

    def get_user_tasks(self, user_id: int) -> list[UserTaskObject]:
        records = self._run(self.user_tasks.get_for_user, user_id)
        return [UserTaskObject.from_record(record) for record in records]

    def unassign_task(self, user_id: int, task_id: str) -> bool:
        return self._run(self.user_tasks.unassign, user_id, task_id)

    def set_daily_task(
        self,
        work_date: date,
        task_id: str,
        is_completed_today: bool = False,
    ) -> dict[str, Any]:
        return self._run(
            self.daily_tasks.set_for_date,
            work_date,
            task_id,
            is_completed_today,
        )

    def get_tasks_by_date(
        self, user_id: int, work_date: date
    ) -> list[DailyTaskObject]:
        records = self._run(
            self.daily_tasks.get_for_user_date, user_id, work_date
        )
        return [DailyTaskObject.from_record(record) for record in records]

    def set_daily_task_completion(
        self,
        work_date: date,
        task_id: str,
        is_completed: bool,
    ) -> dict[str, Any] | None:
        return self._run(
            self.daily_tasks.set_completion, work_date, task_id, is_completed
        )

    def remove_daily_task(self, work_date: date, task_id: str) -> bool:
        return self._run(self.daily_tasks.remove, work_date, task_id)
