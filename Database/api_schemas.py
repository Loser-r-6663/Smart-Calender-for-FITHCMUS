from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from Database.enums import DRLCategory, SourcePlatform, TaskStatus, TaskType
from Database.task_validation import validate_datetime_input
from Database.user_drl import validate_drl_scores


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


class UserDRLScoresSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dieu_1: int = Field(default=0, ge=0, le=100, strict=True)
    dieu_2: int = Field(default=0, ge=0, le=100, strict=True)
    dieu_3: int = Field(default=0, ge=0, le=100, strict=True)
    dieu_4: int = Field(default=0, ge=0, le=100, strict=True)
    dieu_5: int = Field(default=0, ge=0, le=100, strict=True)


class UserDRLScoresUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dieu_1: int | None = Field(default=None, ge=0, le=100, strict=True)
    dieu_2: int | None = Field(default=None, ge=0, le=100, strict=True)
    dieu_3: int | None = Field(default=None, ge=0, le=100, strict=True)
    dieu_4: int | None = Field(default=None, ge=0, le=100, strict=True)
    dieu_5: int | None = Field(default=None, ge=0, le=100, strict=True)


class ScheduleRunRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "restrict_to_window": False,
                "include_unassigned_zero_point_events": False,
                "persist": False,
            }
        },
    )

    week_start: date | None = None
    week_end: date | None = None
    restrict_to_window: bool = Field(default=False, strict=True)
    include_unassigned_zero_point_events: bool = Field(default=False, strict=True)
    initial_drl: dict[str, int] | None = None
    persist: bool = Field(default=False, strict=True)

    @field_validator("initial_drl", mode="before")
    @classmethod
    def check_initial_drl(cls, value: Any) -> dict[str, int] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("initial_drl must be an object mapping DRL categories to points")
        return validate_drl_scores(value, require_non_empty=False)

    @model_validator(mode="after")
    def check_week_range(self) -> "ScheduleRunRequest":
        if (
            self.week_start is not None
            and self.week_end is not None
            and self.week_start > self.week_end
        ):
            raise ValueError("week_start must be on or before week_end")
        return self


class ScheduledEventResponse(BaseModel):
    task_id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str
    training_points: int
    drl_category: str
    points_gained: int


class SchedulePersistenceResponse(BaseModel):
    user_id: int
    assigned_task_ids: list[str]
    newly_assigned_count: int
    daily_task_records: list[dict[str, Any]]


class ScheduleRunResponse(BaseModel):
    status: str
    week_start: date
    week_end: date
    total_tasks_loaded: int
    prepared_tasks_count: int
    total_drl_gained: int
    raw_total_drl: int
    final_total_drl: int
    initial_drl: dict[str, int]
    final_drl: dict[str, int]
    selected_events: list[ScheduledEventResponse]
    persistence: SchedulePersistenceResponse | None = None
