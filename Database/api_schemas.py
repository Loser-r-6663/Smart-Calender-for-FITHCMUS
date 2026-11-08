from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from Database.enums import DRLCategory, SourcePlatform, TaskStatus, TaskType
from Database.task_validation import validate_datetime_input


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    title: str | None = None
    type: TaskType | None = None
    course: str | None = Field(default=None, min_length=1)
    description: str | None = None
    target_audience: str | None = Field(default=None, min_length=1)
    location: str | None = Field(default=None, min_length=1)
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = Field(
        default=None, ge=0.25, le=40.0, strict=True
    )
    training_points: int | None = Field(
        default=None, ge=0, le=100, strict=True
    )
    drl_category: DRLCategory | None = None
    recurrence: str | None = None
    status: TaskStatus | None = None
    is_manual: bool | None = Field(default=None, strict=True)
    source_url: str | None = None
    source_platform: SourcePlatform | None = None

    @field_validator(
        "registration_start",
        "registration_end",
        "start_time",
        "end_time",
        "deadline",
        mode="before",
    )
    @classmethod
    def check_datetime_format(cls, value: Any) -> Any:
        return validate_datetime_input(value)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    email: str | None = None
    full_name: str | None = None


class DailyTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_completed_today: bool = False


class CompletionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_completed: bool
