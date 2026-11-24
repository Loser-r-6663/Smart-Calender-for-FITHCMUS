from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from DataProcessor.Standardization.BaseTask import BaseTask, DateDayTime, Location, TargetAudience
from DataProcessor.Standardization.ExtractedTask import ExtractedTask


class Task(BaseTask):
    """A complete task belonging to one user."""

    id: str | None = None
    title: str
    type: Literal["class", "assignment", "announcement", "event", "personal"]
    course: str | None = None
    description: str | None = None
    target_audience: TargetAudience | None = None
    location: Location | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: DateDayTime | None = None
    end_time: DateDayTime | None = None
    deadline: datetime | None = None
    training_points: int | None = None
    training_point_category: Literal[
        "Articles 1", "Articles 2", "Articles 3", "Articles 4", "Articles 5"
    ] | None = None
    estimated_hours: float | None = None
    source_url: str
    source_platform: Literal[
        "Portal", "Moodle", "Khoa Công nghệ thông tin",
        "Trường đại học Khoa học tự nhiên", "Phòng Công tác sinh viên",
        "VNUHCMUS", "Đoàn trường Khoa học tự nhiên",
        "Đoàn khoa - Liên chi hội khoa Môi trường",
        "Đoàn khoa - Liên chi hội khoa Hóa học",
        "Đoàn khoa - Liên chi hội khoa Sinh học",
        "Đoàn khoa - Liên chi hội khoa Địa chất",
        "Đoàn khoa - Liên chi hội khoa Vật lý",
        "Facebook Khoa Công nghệ thông tin",
    ]
    updated_at: datetime
    recurrence: bool = Field(default=False, description="Task có thời gian lặp lại hay không")
    status: Literal["scheduled", "proposed", "rejected"] = Field(
        default="proposed", description="Trạng thái lên lịch của task"
    )
    compulsory: bool = Field(default=False, description="Task có bắt buộc phải lên lịch hay không")
    flexible: bool = Field(default=False, description="Task có thời gian linh hoạt hay không")

    @model_validator(mode="after")
    def validate_event(self):
        if self.type == "event":
            if self.training_points is None or not 0 <= self.training_points <= 24:
                raise ValueError("training_points phải nằm trong khoảng 0-24 cho sự kiện.")
            if self.training_points > 0 and self.training_point_category is None:
                raise ValueError("training_point_category bắt buộc phải có khi training_points > 0.")
            if self.training_points == 0 and self.training_point_category is not None:
                raise ValueError("training_point_category phải là None khi training_points = 0.")
            if self.estimated_hours is None or self.estimated_hours <= 0:
                raise ValueError("estimated_hours phải được cung cấp cho các nhiệm vụ khi type là 'event'.")
        if self.type == "assignment" and self.estimated_hours is not None and self.estimated_hours <= 0:
            raise ValueError("estimated_hours phải lớn hơn 0 cho assignment.")
        return self

    @field_validator("deadline", "registration_start", "registration_end", mode="after")
    @classmethod
    def ensure_vn_tz(cls, value: datetime | None):
        return ExtractedTask._to_vn_time(value)

    @classmethod
    def from_extracted_task(cls, task: ExtractedTask) -> "Task":
        if not isinstance(task, ExtractedTask):
            raise TypeError("task must be an instance of ExtractedTask")
        data = task.model_dump(exclude={"user_id"})
        if task.type == "class":
            data.update(recurrence=True, compulsory=True)
        elif task.type == "assignment":
            data.update(compulsory=True, flexible=True)
        return cls.model_validate(data)