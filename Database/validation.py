from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskType(str, Enum):
    CLASS = "class"
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    EVENT = "event"
    PERSONAL = "personal"
    TUITION = "tuition"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class DRLCategory(str, Enum):
    DIEU_1 = "dieu_1"
    DIEU_2 = "dieu_2"
    DIEU_3 = "dieu_3"
    DIEU_4 = "dieu_4"
    DIEU_5 = "dieu_5"


class SourcePlatform(str, Enum):
    MOODLE = "moodle"
    PORTAL = "portal"
    FACEBOOK = "facebook"
    CUSTOM = "custom"


class TaskData(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"\S")
    title: str = Field(min_length=2, max_length=255, pattern=r"\S")
    type: TaskType
    course_code: str | None = Field(
        default=None, pattern=r"^[A-Z]{3}\d{5}$", max_length=20
    )
    description: str | None = None
    target_audience: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = Field(
        default=None, ge=0.25, le=40.0, strict=True
    )
    training_points: int = Field(default=0, ge=0, le=100, strict=True)
    drl_category: DRLCategory | None = None
    recurrence: str | None = Field(default=None, max_length=50)
    status: TaskStatus = TaskStatus.ACTIVE
    is_manual: bool = Field(default=False, strict=True)
    source_url: str | None = None
    source_platform: SourcePlatform = SourcePlatform.CUSTOM
    embedding: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_task_logic(self) -> "TaskData":
        for field_name in (
            "registration_start",
            "registration_end",
            "start_time",
            "end_time",
            "deadline",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"{field_name} must include a timezone")

        if (
            self.registration_start is not None
            and self.registration_end is not None
            and self.registration_start >= self.registration_end
        ):
            raise ValueError("registration_start must be before registration_end")
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError("start_time must be before end_time")
        if self.type in {TaskType.ASSIGNMENT, TaskType.TUITION} and self.deadline is None:
            raise ValueError(f"{self.type} tasks require a deadline")
        if self.training_points > 0 and self.drl_category is None:
            self.drl_category = DRLCategory.DIEU_3.value

        return self


class UserData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=1, max_length=50, pattern=r"\S"
    )
    email: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    full_name: str | None = Field(default=None, max_length=100)


def validate_task_data(task_data: Mapping[str, Any]) -> dict[str, Any]:
    validated = TaskData.model_validate(dict(task_data))
    return validated.model_dump(exclude_unset=True)


def validate_user_data(user_data: Mapping[str, Any]) -> dict[str, Any]:
    validated = UserData.model_validate(dict(user_data))
    return validated.model_dump(exclude_unset=True)
