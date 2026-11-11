from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from Database.enums import DRLCategory


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


class UserDRLScoresObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    dieu_1: int = Field(default=0, ge=0, le=100)
    dieu_2: int = Field(default=0, ge=0, le=100)
    dieu_3: int = Field(default=0, ge=0, le=100)
    dieu_4: int = Field(default=0, ge=0, le=100)
    dieu_5: int = Field(default=0, ge=0, le=100)

    def to_drl_dict(self) -> dict[str, int]:
        return {
            "dieu_1": self.dieu_1,
            "dieu_2": self.dieu_2,
            "dieu_3": self.dieu_3,
            "dieu_4": self.dieu_4,
            "dieu_5": self.dieu_5,
        }

    @classmethod
    def from_records(
        cls, user_id: int, records: Iterable[Mapping[str, Any]]
    ) -> "UserDRLScoresObject":
        scores = {category.value: 0 for category in DRLCategory}
        for record in records:
            category = record.get("drl_category")
            if category in scores:
                scores[category] = int(record["points"])
        return cls(user_id=user_id, **scores)
