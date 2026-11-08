from collections.abc import Mapping
from datetime import date
from typing import Any

from Database.task_objects import TaskObject


class DailyTaskObject(TaskObject):
    work_date: date
    is_completed_today: bool

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "DailyTaskObject":
        return cls.model_validate(dict(record))
