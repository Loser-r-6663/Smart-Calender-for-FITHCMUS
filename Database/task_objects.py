from collections.abc import Mapping
from typing import Any

from Database.task_validation import TaskData


class TaskObject(TaskData):
    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "TaskObject":
        return cls.model_validate(dict(record))
