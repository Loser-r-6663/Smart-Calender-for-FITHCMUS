from collections.abc import Mapping
from datetime import datetime
from math import isfinite
import re
from typing import Any

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from Database.enums import DRLCategory, SourcePlatform, TaskStatus, TaskType
from Database.task_config import TASK_DEFAULTS, current_task_timestamp


def validate_datetime_input(value: Any) -> Any:
    if value is not None and not isinstance(value, (str, datetime)):
        raise ValueError(
            "datetime fields must use ISO 8601 strings or datetime values"
        )
    return value


class TaskData(BaseModel):
    model_config = ConfigDict(
        extra="forbid", use_enum_values=True, validate_default=True
    )

    id: str = Field(min_length=1, max_length=64, pattern=r"\S")
    title: str = Field(min_length=2, max_length=255, pattern=r"\S")
    type: TaskType
    course: str | None = Field(default=TASK_DEFAULTS["course"], min_length=1)
    description: str | None = TASK_DEFAULTS["description"]
    target_audience: str | None = Field(
        default=TASK_DEFAULTS["target_audience"], min_length=1
    )
    location: str | None = Field(default=TASK_DEFAULTS["location"], min_length=1)
    registration_start: datetime | None = TASK_DEFAULTS["registration_start"]
    registration_end: datetime | None = TASK_DEFAULTS["registration_end"]
    start_time: datetime | None = TASK_DEFAULTS["start_time"]
    end_time: datetime | None = TASK_DEFAULTS["end_time"]
    deadline: datetime | None = TASK_DEFAULTS["deadline"]
    estimated_hours: float | None = Field(
        default=TASK_DEFAULTS["estimated_hours"], ge=0.25, le=40.0, strict=True
    )
    training_points: int = Field(
        default=TASK_DEFAULTS["training_points"], ge=0, le=100, strict=True
    )
    drl_category: DRLCategory | None = TASK_DEFAULTS["drl_category"]
    recurrence: str | None = Field(default=TASK_DEFAULTS["recurrence"], max_length=50)
    status: TaskStatus = TASK_DEFAULTS["status"]
    is_manual: bool = Field(default=TASK_DEFAULTS["is_manual"], strict=True)
    source_url: AnyHttpUrl | None = TASK_DEFAULTS["source_url"]
    source_platform: SourcePlatform = TASK_DEFAULTS["source_platform"]
    updated_at: datetime = Field(default_factory=current_task_timestamp)

    @field_validator(
        "id",
        "title",
        "course",
        "description",
        "target_audience",
        "location",
        "recurrence",
        "source_url",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if "\x00" in value:
            raise ValueError("text fields cannot contain a null character")
        return value

    @field_validator("recurrence")
    @classmethod
    def validate_recurrence_format(cls, value: str | None) -> str | None:
        if value is None:
            return value
        match = re.fullmatch(
            r"(T[2-7]|CN) "
            r"((?:[01]\d|2[0-3]):[0-5]\d)-"
            r"((?:[01]\d|2[0-3]):[0-5]\d)",
            value,
        )
        if match is None:
            raise ValueError(
                "recurrence must use the format 'T2 08:00-10:00' "
                "with a weekday from T2 to T7 or CN"
            )
        start_time = datetime.strptime(match.group(2), "%H:%M").time()
        end_time = datetime.strptime(match.group(3), "%H:%M").time()
        if start_time >= end_time:
            raise ValueError("recurrence start time must be before end time")
        return value

    @field_validator(
        "registration_start",
        "registration_end",
        "start_time",
        "end_time",
        "deadline",
        "updated_at",
        mode="before",
    )
    @classmethod
    def validate_datetime_fields(cls, value: Any) -> Any:
        return validate_datetime_input(value)

    @field_validator("estimated_hours")
    @classmethod
    def validate_finite_estimated_hours(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("estimated_hours must be finite")
        return value

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
        if (
            self.type in {TaskType.ASSIGNMENT, TaskType.TUITION}
            and self.deadline is None
        ):
            raise ValueError(f"{self.type} tasks require a deadline")
        if self.training_points > 0 and self.drl_category is None:
            self.drl_category = DRLCategory.DIEU_3.value

        return self


def validate_task_data(task_data: Mapping[str, Any]) -> dict[str, Any]:
    validated = TaskData.model_validate(dict(task_data))
    result = validated.model_dump()
    if result["source_url"] is not None:
        result["source_url"] = str(result["source_url"])
    return result
