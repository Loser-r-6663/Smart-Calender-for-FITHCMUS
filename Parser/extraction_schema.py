"""Provider-facing extraction envelope, intentionally separate from TaskCandidate."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskTypeValue = Literal["class", "assignment", "exam", "event", "personal", "tuition"]


class ExtractedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    type: TaskTypeValue | None = None
    course_code: str | None = None
    description: str | None = None
    target_audience: str | None = None
    location: str | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = None
    training_points: int | None = None
    recurrence: str | None = None


class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[ExtractedTask] = Field(default_factory=list)


def parse_envelope(value: Any) -> ExtractionEnvelope:
    return value if isinstance(value, ExtractionEnvelope) else ExtractionEnvelope.model_validate(value)
