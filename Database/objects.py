"""Compatibility exports for database result objects."""

from Database.daily_task_objects import DailyTaskObject
from Database.task_objects import TaskObject
from Database.user_objects import UserObject, UserTaskObject

__all__ = [
    "DailyTaskObject",
    "TaskObject",
    "UserObject",
    "UserTaskObject",
]
