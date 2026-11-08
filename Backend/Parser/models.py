"""Opaque input and immutable pre-persistence data-processor values."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


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


@dataclass(frozen=True, slots=True)
class RawCrawlerInput:
    """An opaque envelope supplied by a crawler implementation elsewhere."""

    # The payload remains opaque here so crawler-specific parsing stays isolated.
    payload: Any
    source_platform: SourcePlatform | None = None
    source_alias: str | None = None
    captured_at: datetime | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class TaskCandidate:
    """Immutable data-processor output before task persistence."""

    # Candidates are immutable between extraction and persistence.
    title: str
    type: TaskType
    course: str | None = None
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
    drl_category: DRLCategory | None = None
    recurrence: str | None = None
    status: TaskStatus = TaskStatus.ACTIVE
    is_manual: bool = False
    source_url: str | None = None
    source_platform: SourcePlatform = SourcePlatform.CUSTOM
    embedding: tuple[float, ...] | None = None
    updated_at: datetime | None = None
    id: str | None = None
