from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal


@dataclass(frozen=True, slots=True)
class ClientUser:
    id: str
    username: str
    portal_status: bool = False
    moodle_status: bool = False


@dataclass(frozen=True, slots=True)
class ConnectionStatus:
    portal: bool
    moodle: bool
    portal_configured: bool = False
    moodle_configured: bool = False
    last_sync: datetime | None = None


@dataclass(frozen=True, slots=True)
class SyncResult:
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class TaskDraft:
    title: str
    kind: Literal["class", "assignment", "event", "announcement"]
    scheduled_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    deadline: datetime | None = None
    course: str | None = None
    location: str | None = None
    description: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarItem:
    """Safe, presentation-oriented form of a backend task."""

    id: str
    task_id: str
    title: str
    kind: str
    start: datetime | None = None
    end: datetime | None = None
    deadline: datetime | None = None
    course: str | None = None
    location: str | None = None
    description: str | None = None
    points: int | None = None
    source: str | None = None
    source_url: str | None = None
    is_personal: bool = False

    @property
    def day(self) -> date | None:
        timestamp = self.start or self.deadline
        return timestamp.date() if timestamp else None

    @property
    def time_label(self) -> str:
        if self.start:
            if self.start.time() == time.min and self.end is None:
                return "All day"
            if self.end:
                return f"{self.start:%H:%M}–{self.end:%H:%M}"
            return f"{self.start:%H:%M}"
        if self.deadline:
            if self.deadline.time() == time.min:
                return "Due date"
            return f"Due {self.deadline:%H:%M}"
        return "No date"


@dataclass(slots=True)
class CalendarFilters:
    kind: str = "all"
    query: str = ""


@dataclass(slots=True)
class ClientState:
    user: ClientUser | None = None
    items: list[CalendarItem] = field(default_factory=list)
    visible_month: date = field(default_factory=lambda: date.today().replace(day=1))
    selected_date: date = field(default_factory=date.today)
    selected_item_id: str | None = None
    view: str = "calendar"
    filters: CalendarFilters = field(default_factory=CalendarFilters)
    loading: bool = False
    error: str | None = None

