"""Integration service bridging PostgreSQL tasks and BranchAndBoundScheduler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any

from pydantic import BaseModel

from Database.database_manager import DatabaseManager
from Database.enums import TaskStatus
from Database.task_objects import TaskObject

from .branch_and_bound_models import BranchAndBoundResult, FIXED_TASK_TYPES
from .branch_and_bound_scheduler import BranchAndBoundScheduler


GMT_PLUS_7 = timezone(timedelta(hours=7), name="GMT+07:00")
_RECURRENCE_PATTERN = re.compile(
    r"^(T[2-7]|CN)\s+"
    r"((?:[01]\d|2[0-3]):[0-5]\d)-"
    r"((?:[01]\d|2[0-3]):[0-5]\d)$"
)
_WEEKDAY_MAP = {
    "T2": 0,
    "T3": 1,
    "T4": 2,
    "T5": 3,
    "T6": 4,
    "T7": 5,
    "CN": 6,
}
_INACTIVE_STATUSES = frozenset({"done", "archived", "cancelled"})
_MAX_RECURRENCE_SPAN_DAYS = 180


class UserNotFoundError(LookupError):
    """Raised when scheduling targets a user ID that does not exist."""


@dataclass(frozen=True, slots=True)
class SchedulePersistenceSummary:
    """Summary of task assignments and daily schedule rows persisted to DB."""

    user_id: int
    assigned_task_ids: tuple[str, ...]
    newly_assigned_count: int
    daily_task_records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ScheduleRunResult:
    """Combined output of a scheduling run over database tasks."""

    schedule: BranchAndBoundResult
    week_start: date
    week_end: date
    total_tasks_loaded: int
    prepared_tasks_count: int
    persistence: SchedulePersistenceSummary | None = None


def normalize_to_gmt7(value: datetime) -> datetime:
    """Normalize a datetime to GMT+7, treating naive datetimes as GMT+7."""
    if value.tzinfo is None:
        return value.replace(tzinfo=GMT_PLUS_7)
    return value.astimezone(GMT_PLUS_7)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return normalize_to_gmt7(value)
    if isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return normalize_to_gmt7(datetime.fromisoformat(normalized))
        except ValueError:
            return None
    return None


def parse_recurrence(
    recurrence: str | None,
) -> tuple[int, time, time] | None:
    """Parse 'T2 07:30-09:30' into (weekday_index, start_time, end_time)."""
    if not recurrence:
        return None
    match = _RECURRENCE_PATTERN.fullmatch(recurrence.strip())
    if match is None:
        return None

    weekday = _WEEKDAY_MAP[match.group(1)]
    start_t = datetime.strptime(match.group(2), "%H:%M").time()
    end_t = datetime.strptime(match.group(3), "%H:%M").time()
    if start_t >= end_t:
        return None
    return weekday, start_t, end_t


def current_week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return the (Monday, Sunday) dates for the week of reference_date."""
    anchor = reference_date or datetime.now(GMT_PLUS_7).date()
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _to_task_dict(task: TaskObject | Mapping[str, Any]) -> dict[str, Any]:
    data = task.model_dump() if isinstance(task, BaseModel) else dict(task)
    for field in ("start_time", "end_time", "deadline"):
        data[field] = _coerce_datetime(data.get(field))
    return data


def _resolve_window(
    week_start: date | None, week_end: date | None
) -> tuple[date, date]:
    if week_start is not None and week_end is not None:
        if week_start > week_end:
            raise ValueError("week_start must be on or before week_end")
        return week_start, week_end
    if week_start is not None:
        return week_start, week_start + timedelta(days=6)
    if week_end is not None:
        return week_end - timedelta(days=6), week_end
    return current_week_bounds()


def _dated_span(
    normalized_tasks: Sequence[dict[str, Any]],
    base_start: date,
    base_end: date,
) -> tuple[date, date]:
    dates: list[date] = [base_start, base_end]
    for data in normalized_tasks:
        for field in ("start_time", "end_time", "deadline"):
            dt = data.get(field)
            if isinstance(dt, datetime):
                dates.append(dt.date())

    span_start = min(dates)
    span_end = max(dates)
    max_end = span_start + timedelta(days=_MAX_RECURRENCE_SPAN_DAYS)
    if span_end > max_end:
        span_end = max_end
    return span_start, span_end


def _effective_interval(data: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    st = data.get("start_time")
    et = data.get("end_time")
    if isinstance(st, datetime) and isinstance(et, datetime) and st < et:
        return st, et

    dl = data.get("deadline")
    t_points = int(data.get("training_points") or 0)
    if st is None and et is None and isinstance(dl, datetime) and t_points > 0:
        return dl - timedelta(minutes=30), dl
    return None


def _should_keep_task(
    data: Mapping[str, Any],
    *,
    include_unassigned_zero_point_events: bool,
    assigned_task_ids: set[str] | None,
) -> bool:
    status = str(data.get("status") or "active").lower()
    if status in _INACTIVE_STATUSES:
        return False

    task_type = str(data.get("type") or "").lower()
    training_points = int(data.get("training_points") or 0)
    if task_type in FIXED_TASK_TYPES or training_points > 0:
        return True

    if include_unassigned_zero_point_events or bool(data.get("is_manual")):
        return True

    task_id = str(data.get("id") or "")
    return assigned_task_ids is not None and task_id in assigned_task_ids


def prepare_tasks_for_scheduler(
    tasks: Sequence[TaskObject | Mapping[str, Any]],
    *,
    week_start: date | None = None,
    week_end: date | None = None,
    restrict_to_window: bool = False,
    include_unassigned_zero_point_events: bool = False,
    assigned_task_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Convert database tasks into scheduler-ready dicts with GMT+7 datetimes
    and expanded weekly recurrence slots.
    """
    base_start, base_end = _resolve_window(week_start, week_end)
    normalized = [_to_task_dict(task) for task in tasks]

    if restrict_to_window:
        expand_start, expand_end = base_start, base_end
    else:
        expand_start, expand_end = _dated_span(normalized, base_start, base_end)

    win_start_dt = datetime.combine(base_start, time.min, tzinfo=GMT_PLUS_7)
    win_end_dt = datetime.combine(
        base_end + timedelta(days=1), time.min, tzinfo=GMT_PLUS_7
    )

    prepared: list[dict[str, Any]] = []
    for data in normalized:
        if not _should_keep_task(
            data,
            include_unassigned_zero_point_events=include_unassigned_zero_point_events,
            assigned_task_ids=assigned_task_ids,
        ):
            continue

        task_type = str(data.get("type") or "").lower()
        parsed_recurrence = parse_recurrence(data.get("recurrence"))
        st = data.get("start_time")
        et = data.get("end_time")

        needs_recurrence_expansion = parsed_recurrence is not None and (
            st is None
            or et is None
            or (
                task_type == "class"
                and restrict_to_window
                and isinstance(st, datetime)
                and (st < win_start_dt or st >= win_end_dt)
            )
        )

        if needs_recurrence_expansion and parsed_recurrence is not None:
            weekday, start_t, end_t = parsed_recurrence
            day = expand_start
            while day <= expand_end:
                if day.weekday() == weekday:
                    occurrence = dict(data)
                    occurrence["start_time"] = datetime.combine(
                        day, start_t, tzinfo=GMT_PLUS_7
                    )
                    occurrence["end_time"] = datetime.combine(
                        day, end_t, tzinfo=GMT_PLUS_7
                    )
                    prepared.append(occurrence)
                day += timedelta(days=1)
            continue

        interval = _effective_interval(data)
        if interval is None:
            continue

        if restrict_to_window:
            eff_start, eff_end = interval
            if not (eff_end > win_start_dt and eff_start < win_end_dt):
                continue

        prepared.append(data)

    return prepared


class SchedulingService:
    """Coordinates reading tasks from PostgreSQL, running B&B, and persisting results."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        scheduler: BranchAndBoundScheduler | None = None,
    ) -> None:
        self.database = database or DatabaseManager()
        self.scheduler = scheduler or BranchAndBoundScheduler()

    def run(
        self,
        *,
        user_id: int | None = None,
        initial_drl: Mapping[str, int] | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
        restrict_to_window: bool = False,
        include_unassigned_zero_point_events: bool = False,
        persist: bool = False,
    ) -> ScheduleRunResult:
        if persist and user_id is None:
            raise ValueError("user_id is required when persist=True")

        assigned_task_ids: set[str] | None = None
        if user_id is not None:
            user = self.database.get_user(user_id)
            if user is None:
                raise UserNotFoundError(f"User {user_id} not found")
            assigned_task_ids = {
                item.task_id for item in self.database.get_user_tasks(user_id)
            }

        resolved_start, resolved_end = _resolve_window(week_start, week_end)
        raw_tasks = self.database.list_tasks(status=TaskStatus.ACTIVE)
        prepared_tasks = prepare_tasks_for_scheduler(
            raw_tasks,
            week_start=resolved_start,
            week_end=resolved_end,
            restrict_to_window=restrict_to_window,
            include_unassigned_zero_point_events=include_unassigned_zero_point_events,
            assigned_task_ids=assigned_task_ids,
        )

        schedule_result = self.scheduler.schedule(
            prepared_tasks,
            initial_drl=dict(initial_drl) if initial_drl is not None else None,
        )

        persistence: SchedulePersistenceSummary | None = None
        if persist and user_id is not None:
            newly_assigned = 0
            assigned_ids: list[str] = []
            daily_records: list[dict[str, Any]] = []
            seen_ids: set[str] = set()

            for event in schedule_result.selected_events:
                if event.task_id not in seen_ids:
                    seen_ids.add(event.task_id)
                    assigned_ids.append(event.task_id)
                    if self.database.assign_task(user_id, event.task_id):
                        newly_assigned += 1

                work_date = normalize_to_gmt7(event.start_time).date()
                daily_record = self.database.set_daily_task(
                    work_date,
                    event.task_id,
                    is_completed_today=False,
                )
                daily_records.append(dict(daily_record))

            persistence = SchedulePersistenceSummary(
                user_id=user_id,
                assigned_task_ids=tuple(assigned_ids),
                newly_assigned_count=newly_assigned,
                daily_task_records=tuple(daily_records),
            )

        return ScheduleRunResult(
            schedule=schedule_result,
            week_start=resolved_start,
            week_end=resolved_end,
            total_tasks_loaded=len(raw_tasks),
            prepared_tasks_count=len(prepared_tasks),
            persistence=persistence,
        )


__all__ = [
    "GMT_PLUS_7",
    "SchedulePersistenceSummary",
    "ScheduleRunResult",
    "SchedulingService",
    "UserNotFoundError",
    "current_week_bounds",
    "normalize_to_gmt7",
    "parse_recurrence",
    "prepare_tasks_for_scheduler",
]

