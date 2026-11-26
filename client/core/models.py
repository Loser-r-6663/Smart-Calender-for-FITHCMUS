from __future__ import annotations

from dataclasses import dataclass, field
from academic_search import SearchSnapshot
from datetime import date, datetime, time
from typing import Literal


TaskKind = Literal["class", "assignment", "event", "announcement", "personal"]
WeekdayCode = Literal["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
CampusName = Literal["Nguyễn Văn Cừ (cơ sở 1)", "Thủ Đức (cơ sở 2)"]
DrlCategory = Literal[
    "Articles 1", "Articles 2", "Articles 3", "Articles 4", "Articles 5"
]


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
    kind: TaskKind
    scheduled_date: date | None = None
    weekday: WeekdayCode | None = None
    start_time: time | None = None
    end_time: time | None = None
    deadline: datetime | None = None
    course: str | None = None
    location: str | None = None
    campus: CampusName | None = None
    description: str | None = None
    source_url: str | None = None
    estimated_hours: float | None = None
    training_points: int | None = None
    training_point_category: DrlCategory | None = None
    recurrence: bool = False
    flexible: bool = False
    compulsory: bool = False


@dataclass(frozen=True, slots=True)
class CalendarItem:
    """Safe, presentation-oriented form of a backend task."""

    id: str
    task_id: str
    title: str
    kind: str
    scope: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    deadline: datetime | None = None
    course: str | None = None
    location: str | None = None
    room: str | None = None
    campus: str | None = None
    description: str | None = None
    points: int | None = None
    training_point_category: str | None = None
    estimated_hours: float | None = None
    source: str | None = None
    source_url: str | None = None
    is_personal: bool = False
    status: str = "proposed"
    recurrence: bool = False
    weekday: str | None = None
    flexible: bool = False
    compulsory: bool = False
    schedule_reason: str | None = None
    is_allocated_session: bool = False

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
        if self.weekday:
            return f"Every {self.weekday}"
        if self.deadline:
            if self.deadline.time() == time.min:
                return "Due date"
            return f"Due {self.deadline:%H:%M}"
        return "No date"


@dataclass(frozen=True, slots=True)
class ScheduleProposal:
    item: CalendarItem
    reason: str


@dataclass(frozen=True, slots=True)
class ScheduleViewData:
    week_start: date
    week_end: date
    scheduled_items: list[CalendarItem]
    unschedulable: list[ScheduleProposal]
    unselected: list[ScheduleProposal]
    rejected_items: list[CalendarItem]
    initial_drl: dict[str, int]
    final_drl: dict[str, int]
    drl_caps: dict[str, int]


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
    schedule: ScheduleViewData | None = None
    schedule_tab: str = "needs_info"
    schedule_week_offset: int = 0
    loading: bool = False
    error: str | None = None
    session_expired: bool = False
    search_snapshot: SearchSnapshot = field(default_factory=lambda: SearchSnapshot((), (), None))
    search_query: str = ""
    selected_search_key: tuple[str, str] | None = None
