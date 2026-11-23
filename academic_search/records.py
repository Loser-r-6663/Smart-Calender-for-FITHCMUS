"""Map persisted tasks into scoped, database-independent Search records."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from DataProcessor.Standardization.BaseTask import DateDayTime
from DataProcessor.Standardization.ExtractedTask import ExtractedTask

Scope = Literal["public", "personal"]


@dataclass(frozen=True)
class SearchTime:
    """An absolute date/time or a weekly weekday/time without an occurrence."""

    date: date | None
    day: str | None
    time: time | None


@dataclass(frozen=True)
class SearchRecord:
    scope: Scope
    id: str
    title: str
    description: str | None
    course: str | None
    type: Literal["class", "assignment", "announcement", "event"]
    publisher: str
    source_url: str
    training_points: int | None
    deadline: datetime | None
    start_time: SearchTime | None
    end_time: SearchTime | None
    registration_start: datetime | None = None
    registration_end: datetime | None = None

    @property
    def key(self) -> tuple[Scope, str]:
        return self.scope, self.id


def _map_time(value: DateDayTime | None) -> SearchTime | None:
    if value is None:
        return None
    return SearchTime(date=value.date, day=value.day, time=value.time)


def map_task(task: ExtractedTask, *, scope: Scope) -> SearchRecord:
    """Use public for TaskRepository and personal for UserTaskRepository reads."""
    if not isinstance(task, ExtractedTask):
        raise TypeError("task must be an ExtractedTask")
    if scope not in ("public", "personal"):
        raise ValueError("scope must be public or personal")
    if not isinstance(task.id, str):
        raise ValueError("A persisted task UUID is required")
    try:
        UUID(task.id)
    except ValueError as error:
        raise ValueError("A persisted task UUID is required") from error
    return SearchRecord(
        scope=scope,
        id=task.id,
        title=task.title,
        description=task.description,
        course=task.course,
        type=task.type,
        publisher=task.source_platform,
        source_url=task.source_url,
        training_points=task.training_points,
        deadline=task.deadline,
        start_time=_map_time(task.start_time),
        end_time=_map_time(task.end_time),
        registration_start=task.registration_start,
        registration_end=task.registration_end,
    )
