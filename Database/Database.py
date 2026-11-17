from datetime import datetime

from Backend.Regulation.BaseTask import DayTime
from Backend.Regulation.ExtractedTask import ExtractedTask
from Backend.Regulation.User import User

from Database.task_repository import TaskRepository
from Database.user_task_repository import UserTaskRepository
from Database.user_repository import UserRepository
from Database import crypto


class Database:
    """
    Facade class for database operations, providing backward compatibility
    while delegating specific domain operations to specialized repositories.
    """

    def __init__(
        self,
        user: User | str | None = None,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ):
        self.user = user
        self.public_tasks = TaskRepository(supabase_url=supabase_url, supabase_key=supabase_key)
        self.user_tasks = UserTaskRepository(supabase_url=supabase_url, supabase_key=supabase_key)
        self.users = UserRepository(supabase_url=supabase_url, supabase_key=supabase_key)

        # Route self.tasks based on user
        self.tasks = self.user_tasks if self.user else self.public_tasks

        # Retain backward-compatible attributes
        self.TASKS_TABLE_URL = self.tasks.table_url
        self.USERS_TABLE_URL = self.users.table_url
        self.HEADERS = self.tasks.headers

    def _resolve_user_id(self, user: User | str | None = None) -> str | None:
        target_user = user if user is not None else self.user
        if target_user is None:
            return None
        if isinstance(target_user, User):
            return str(target_user.id) if target_user.id else None
        return str(target_user)

    # --- Security / Encryption Backward Compatibility ---
    @staticmethod
    def _get_fernet():
        return crypto.get_fernet()

    @classmethod
    def _encrypt(cls, value: str | None):
        return crypto.encrypt(value)

    @classmethod
    def _decrypt(cls, value: str | None):
        return crypto.decrypt(value)

    @staticmethod
    def _hash_password(password: str):
        return crypto.hash_password(password)

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        return crypto.verify_password(password, stored_hash)

    # --- Task Mapper Backward Compatibility ---
    @staticmethod
    def _serialize_time(value: datetime | DayTime | None, prefix: str):
        return TaskRepository.serialize_time(value, prefix)

    @staticmethod
    def _deserialize_time(row: dict, prefix: str):
        return TaskRepository.deserialize_time(row, prefix)

    @classmethod
    def _task_to_row(cls, task: ExtractedTask, user_id: str | None = None):
        if user_id or getattr(task, "user_id", None):
            return UserTaskRepository.task_to_row(task, user_id=user_id)
        return TaskRepository.task_to_row(task)

    @classmethod
    def _row_to_task(cls, row: dict) -> ExtractedTask:
        return TaskRepository.row_to_task(row)

    # --- User Mapper Backward Compatibility ---
    @classmethod
    def _user_to_row(cls, user: User) -> dict:
        return UserRepository.user_to_row(user)

    @classmethod
    def _row_to_user(cls, row: dict, include_password_hash: bool = False) -> User:
        return UserRepository.row_to_user(row, include_password_hash=include_password_hash)

    # --- Task Operations ---
    def save_tasks(self, tasks: list[ExtractedTask], user: User | str | None = None):
        user_id = self._resolve_user_id(user)
        if user_id: return self.user_tasks.save(tasks, user_id=user_id)
        return self.public_tasks.save(tasks)

    def delete_tasks(self, tasks: list[ExtractedTask], user: User | str | None = None):
        user_id = self._resolve_user_id(user)
        if user_id: return self.user_tasks.delete(tasks, user_id=user_id)
        return self.public_tasks.delete(tasks)

    def get_tasks(self, limit: int = 100, user: User | str | None = None) -> list[ExtractedTask]:
        user_id = self._resolve_user_id(user)
        if user_id: return self.user_tasks.get(user_id=user_id, limit=limit)
        return self.public_tasks.get(limit=limit)

    def update_task(self, task_id: str, data: ExtractedTask | dict, user: User | str | None = None):
        user_id = self._resolve_user_id(user)
        if user_id: return self.user_tasks.update(task_id=task_id, data=data, user_id=user_id)
        return self.public_tasks.update(task_id=task_id, data=data)

    # --- User Operations ---
    def save_user(self, user: User) -> User:
        return self.users.save(user=user)

    def get_user(self, username: str, password: str | None = None) -> User | None:
        return self.users.get(username=username, password=password)

    def get_users(self, page_size: int = 1000) -> list[User]:
        return self.users.get_all(page_size=page_size)

    def update_user(self, user_or_id: str | User, data: User | dict | None = None) -> User:
        return self.users.update(user_or_id=user_or_id, data=data)

    def delete_user(self, user: User | str):
        return self.users.delete(user=user)

    def delete_users(self, users: list[User]):
        return self.users.delete_many(users=users)
