from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class UserObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    username: str
    email: str
    full_name: str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "UserObject":
        return cls.model_validate(dict(record))


class UserTaskObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    task_id: str
    assigned_at: datetime

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "UserTaskObject":
        return cls.model_validate(dict(record))
