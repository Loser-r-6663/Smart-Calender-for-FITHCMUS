from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from DataProcessor.Standardization.BaseTask import BaseTask, DateDayTime, Location, TargetAudience
from DataProcessor.Standardization.ExtractedTask import ExtractedTask

VN_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
VALID_PLATFORMS = {
    "Portal",
    "Moodle",
    "Khoa Công nghệ thông tin",
    "Trường đại học Khoa học tự nhiên",
    "Phòng Công tác sinh viên",
    "VNUHCMUS",
    "VNUHMCUS",
    "Đoàn trường Khoa học tự nhiên",
    "Đoàn khoa - Liên chi hội khoa Môi trường",
    "Đoàn khoa - Liên chi hội khoa Hóa học",
    "Đoàn khoa - Liên chi hội khoa Sinh học",
    "Đoàn khoa - Liên chi hội khoa Địa chất",
    "Đoàn khoa - Liên chi hội khoa Vật lý",
    "Facebook Khoa Công nghệ thông tin",
    "Custom",
}


def _coerce_date_day_time(value: Any) -> DateDayTime | None:
    if value is None or isinstance(value, DateDayTime):
        return value
    if isinstance(value, datetime):
        dt = value.replace(tzinfo=VN_ZONE) if value.tzinfo is None else value.astimezone(VN_ZONE)
        return DateDayTime(date=dt.date(), time=dt.time().replace(tzinfo=None))
    if isinstance(value, date):
        return DateDayTime(date=value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=VN_ZONE) if dt.tzinfo is None else dt.astimezone(VN_ZONE)
            return DateDayTime(date=dt.date(), time=dt.time().replace(tzinfo=None))
        except ValueError:
            try:
                return DateDayTime(date=date.fromisoformat(text))
            except ValueError:
                return None
    if isinstance(value, dict):
        raw_time = value.get("time") if value.get("time") is not None else value.get("time_")
        parsed_date = value.get("date")
        if isinstance(parsed_date, str) and parsed_date:
            try:
                parsed_date = date.fromisoformat(parsed_date)
            except ValueError:
                parsed_date = None
        parsed_time = raw_time
        if isinstance(raw_time, str) and raw_time:
            try:
                parsed_time = time.fromisoformat(raw_time).replace(tzinfo=None)
            except ValueError:
                parsed_time = None
        day = value.get("day")
        if parsed_date is None and day is None and parsed_time is None:
            return None
        return DateDayTime(date=parsed_date, day=day, time=parsed_time)
    return None


def _coerce_location(value: Any) -> Location | None:
    if value is None or isinstance(value, Location):
        return value
    if isinstance(value, str):
        clean = value.strip()
        return Location(room=clean) if clean else None
    if isinstance(value, dict):
        return Location(
            room=value.get("room"),
            campus=value.get("campus") if value.get("campus") in {
                "Nguyễn Văn Cừ (cơ sở 1)",
                "Thủ Đức (cơ sở 2)",
            } else None,
            detail=value.get("detail"),
        )
    return None


class ScheduledOccurrence(BaseTask):
    start_time: DateDayTime
    end_time: DateDayTime


class Task(BaseTask):
    """A complete task belonging to one user."""

    id: str | None = None
    owner_id: str | None = None
    scope: Literal["public", "personal", "unknown"] = "unknown"
    scheduled_occurrences: list[ScheduledOccurrence] = Field(default_factory=list)
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
    source_url: str = ""
    source_platform: Literal[
        "Portal", "Moodle", "Khoa Công nghệ thông tin",
        "Trường đại học Khoa học tự nhiên", "Phòng Công tác sinh viên",
        "VNUHCMUS", "VNUHMCUS", "Đoàn trường Khoa học tự nhiên",
        "Đoàn khoa - Liên chi hội khoa Môi trường",
        "Đoàn khoa - Liên chi hội khoa Hóa học",
        "Đoàn khoa - Liên chi hội khoa Sinh học",
        "Đoàn khoa - Liên chi hội khoa Địa chất",
        "Đoàn khoa - Liên chi hội khoa Vật lý",
        "Facebook Khoa Công nghệ thông tin",
        "Custom",
    ] | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(VN_ZONE))
    recurrence: bool = Field(default=False, description="Task có thời gian lặp lại hay không")
    status: Literal["scheduled", "proposed", "rejected"] = Field(
        default="proposed", description="Trạng thái lên lịch của task"
    )
    compulsory: bool = Field(default=False, description="Task có bắt buộc phải lên lịch hay không")
    flexible: bool = Field(default=False, description="Task có thời gian linh hoạt hay không")

    @model_validator(mode="after")
    def validate_event(self):
        if self.training_points is not None and not 0 <= self.training_points <= 24:
            raise ValueError("training_points phải nằm trong khoảng 0-24 cho sự kiện.")
        if self.training_points == 0 and self.training_point_category is not None:
            self.training_point_category = None
        if self.estimated_hours is not None and self.estimated_hours <= 0:
            raise ValueError("estimated_hours phải lớn hơn 0.")
        return self

    @field_validator("deadline", "registration_start", "registration_end", mode="after")
    @classmethod
    def ensure_vn_tz(cls, value: datetime | None):
        return ExtractedTask._to_vn_time(value)

    @classmethod
    def from_extracted_task(cls, task: ExtractedTask, *, owner_id: str | None = None,
                            scope: Literal["public", "personal", "unknown"] = "unknown") -> "Task":
        if not isinstance(task, ExtractedTask):
            raise TypeError("task must be an instance of ExtractedTask")
        data = task.model_dump(exclude={"user_id"})
        if scope != "unknown":
            if not owner_id or not task.id:
                raise ValueError("Verified tasks require an owner and original UUID")
            UUID(task.id)
            if scope == "personal" and task.user_id not in (None, owner_id):
                raise ValueError("Personal task belongs to another owner")
        data.update(owner_id=owner_id, scope=scope)
        if task.type == "class":
            data.update(recurrence=bool(task.start_time and task.start_time.date is None
                                        and task.start_time.day), compulsory=True)
        elif task.type == "assignment":
            data.update(compulsory=True, flexible=True)
        return cls.model_validate(data)

    @classmethod
    def from_any(cls, record: Any) -> "Task":
        if isinstance(record, cls):
            return record.model_copy(deep=True)
        if isinstance(record, ExtractedTask):
            return cls.from_extracted_task(record)
        if not isinstance(record, dict):
            raise TypeError(f"Unsupported task record type: {type(record)!r}")

        kind = str(record.get("type") or "announcement")
        if kind not in {"class", "assignment", "announcement", "event", "personal"}:
            kind = "announcement"

        raw_platform = record.get("source_platform")
        if raw_platform is None:
            platform = None
        else:
            platform_str = str(raw_platform)
            platform = platform_str if platform_str in VALID_PLATFORMS else None

        start_dt = _coerce_date_day_time(record.get("start_time"))
        end_dt = _coerce_date_day_time(record.get("end_time"))
        has_weekday = bool(start_dt and start_dt.day and not start_dt.date)

        recurrence = record.get("recurrence")
        if recurrence is None:
            recurrence = has_weekday

        compulsory = record.get("compulsory")
        if compulsory is None:
            compulsory = kind in {"class", "assignment", "personal"}

        flexible = record.get("flexible")
        if flexible is None:
            flexible = kind == "assignment"

        est_hours = record.get("estimated_hours")
        if est_hours is not None and est_hours <= 0:
            est_hours = None

        points = record.get("training_points")
        if points is not None:
            points = max(0, min(24, int(points)))

        category = record.get("training_point_category")
        if category not in {"Articles 1", "Articles 2", "Articles 3", "Articles 4", "Articles 5"}:
            category = None

        status = record.get("status")
        if status not in {"scheduled", "proposed", "rejected"}:
            status = "proposed"

        updated_raw = record.get("updated_at")
        updated_at = datetime.now(VN_ZONE)
        if isinstance(updated_raw, datetime):
            updated_at = updated_raw
        elif isinstance(updated_raw, str) and updated_raw:
            try:
                updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        return cls.model_validate(
            {
                "id": str(record["id"]) if record.get("id") is not None else None,
                "title": str(record.get("title") or "Untitled task"),
                "type": kind,
                "course": record.get("course"),
                "description": record.get("description"),
                "target_audience": record.get("target_audience"),
                "location": _coerce_location(record.get("location")),
                "registration_start": record.get("registration_start"),
                "registration_end": record.get("registration_end"),
                "start_time": start_dt,
                "end_time": end_dt,
                "deadline": record.get("deadline"),
                "training_points": points,
                "training_point_category": category,
                "estimated_hours": est_hours,
                "source_url": str(record.get("source_url") or ""),
                "source_platform": platform,
                "updated_at": updated_at,
                "recurrence": bool(recurrence),
                "status": status,
                "compulsory": bool(compulsory),
                "flexible": bool(flexible),
            }
        )

    @property
    def key(self) -> tuple[str, str | None]:
        return self.scope, self.id
