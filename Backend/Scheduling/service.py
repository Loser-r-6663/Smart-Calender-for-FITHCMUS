"""Integration service bridging ExtractedTask/Supabase tasks and BranchAndBoundScheduler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any

from pydantic import BaseModel

from Backend.Regulation.BaseTask import DayTime
from Backend.Regulation.ExtractedTask import ExtractedTask
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository

from .branch_and_bound_models import (
    BranchAndBoundResult,
    FIXED_TASK_TYPES,
    format_location_text,
    normalize_drl_category,
)
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


@dataclass(frozen=True, slots=True)
class ScheduleRunResult:
    """Combined output of a scheduling run over tasks."""

    schedule: BranchAndBoundResult
    week_start: date
    week_end: date
    total_tasks_loaded: int
    prepared_tasks_count: int


def normalize_to_gmt7(value: datetime) -> datetime:
    """Normalize a datetime to GMT+7, treating naive datetimes as GMT+7."""
    if value.tzinfo is None:
        return value.replace(tzinfo=GMT_PLUS_7)
    return value.astimezone(GMT_PLUS_7)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, DayTime):
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


def _extract_daytime_recurrence(
    start_val: Any, end_val: Any
) -> tuple[int, time, time] | None:
    """Extract weekly (weekday_index, start_time, end_time) from DayTime objects or dicts."""
    def _to_day_time(val: Any) -> tuple[str | None, time | None]:
        if isinstance(val, DayTime):
            return val.day, val.time_
        if isinstance(val, Mapping) and ("day" in val or "time_" in val):
            day = val.get("day")
            t_raw = val.get("time_")
            if isinstance(t_raw, str):
                try:
                    t_raw = time.fromisoformat(t_raw)
                except ValueError:
                    t_raw = None
            return day, t_raw if isinstance(t_raw, time) else None
        return None, None

    s_day, s_time = _to_day_time(start_val)
    e_day, e_time = _to_day_time(end_val)
    day_key = s_day or e_day
    if day_key not in _WEEKDAY_MAP or s_time is None or e_time is None:
        return None
    if s_time >= e_time:
        return None
    return _WEEKDAY_MAP[day_key], s_time, e_time


def current_week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return the (Monday, Sunday) dates for the week of reference_date."""
    anchor = reference_date or datetime.now(GMT_PLUS_7).date()
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _to_task_dict(task: ExtractedTask | BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(task, BaseModel):
        data = task.model_dump()
        raw_st = getattr(task, "start_time", data.get("start_time"))
        raw_et = getattr(task, "end_time", data.get("end_time"))
        raw_loc = getattr(task, "location", data.get("location"))
    else:
        data = dict(task)
        raw_st = data.get("start_time")
        raw_et = data.get("end_time")
        raw_loc = data.get("location")

    data["_daytime_recurrence"] = _extract_daytime_recurrence(raw_st, raw_et)
    data["start_time"] = _coerce_datetime(raw_st)
    data["end_time"] = _coerce_datetime(raw_et)
    data["deadline"] = _coerce_datetime(data.get("deadline"))
    data["registration_start"] = _coerce_datetime(data.get("registration_start"))
    data["registration_end"] = _coerce_datetime(data.get("registration_end"))
    data["location"] = format_location_text(raw_loc) or raw_loc

    drl_cat = normalize_drl_category(
        data.get("drl_category") or data.get("training_point_category")
    )
    if drl_cat:
        data["drl_category"] = drl_cat
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
    dl = data.get("deadline") or data.get("registration_end")
    t_points = int(data.get("training_points") or 0)
    task_type = str(data.get("type") or "").lower()

    if isinstance(st, datetime) and isinstance(et, datetime) and st < et:
        return st, et

    if isinstance(st, datetime) and et is None:
        if isinstance(dl, datetime) and dl > st:
            return st, dl
        duration_hours = float(data.get("estimated_hours") or 2.0)
        return st, st + timedelta(hours=duration_hours)

    if st is None and isinstance(et, datetime):
        if task_type == "assignment":
            return et - timedelta(hours=24), et
        duration_hours = float(data.get("estimated_hours") or 2.0)
        return et - timedelta(hours=duration_hours), et

    if st is None and et is None and isinstance(dl, datetime):
        if t_points > 0:
            dur_h = float(data.get("estimated_hours") or 0.5)
            return dl - timedelta(hours=dur_h), dl
        if task_type == "assignment":
            return dl - timedelta(hours=24), dl
    return None


def _should_keep_task(
    data: Mapping[str, Any],
    *,
    include_unassigned_zero_point_events: bool,
    assigned_task_ids: set[str] | None,
    target_user_id: str | int | None = None,
) -> bool:
    status = str(data.get("status") or "active").lower()
    if status in _INACTIVE_STATUSES:
        return False

    task_type = str(data.get("type") or "").lower()
    if task_type == "announcement":
        return False

    task_id = str(data.get("id") or "")
    task_user_id = data.get("user_id")
    if target_user_id is not None and task_user_id is not None:
        if str(task_user_id) != str(target_user_id):
            return False

    training_points = int(data.get("training_points") or 0)

    if task_type == "personal":
        if target_user_id is not None and task_user_id is not None:
            return str(task_user_id) == str(target_user_id)
        return assigned_task_ids is None or task_id in assigned_task_ids

    if task_type in {"class", "exam"} or task_type == "assignment" or training_points > 0:
        return True

    if include_unassigned_zero_point_events or bool(data.get("is_manual")):
        return True

    return assigned_task_ids is not None and task_id in assigned_task_ids


def _extract_user_task_pref(
    pref: Any,
) -> tuple[str, datetime | None, datetime | None]:
    if pref is None:
        return "default", None, None
    if isinstance(pref, Mapping):
        pin_raw = pref.get("pin_status", "default")
        c_st = pref.get("custom_start_time")
        c_et = pref.get("custom_end_time")
    else:
        pin_raw = getattr(pref, "pin_status", "default")
        c_st = getattr(pref, "custom_start_time", None)
        c_et = getattr(pref, "custom_end_time", None)

    pin_status = str(getattr(pin_raw, "value", pin_raw) or "default").lower()
    return pin_status, _coerce_datetime(c_st), _coerce_datetime(c_et)


def _tag_cs1_for_class_exam(task_dict: dict[str, Any], task_type: str) -> None:
    if task_type not in {"class", "exam"}:
        return
    loc = format_location_text(task_dict.get("location"))
    if not loc:
        task_dict["location"] = "Cơ sở 1"
    elif (
        "cơ sở 1" not in loc.lower()
        and "cs1" not in loc.lower()
        and "cơ sở 2" not in loc.lower()
        and "cs2" not in loc.lower()
        and "linh trung" not in loc.lower()
        and "thủ đức" not in loc.lower()
    ):
        task_dict["location"] = f"{loc}, Cơ sở 1"


def prepare_tasks_for_scheduler(
    tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]],
    *,
    week_start: date | None = None,
    week_end: date | None = None,
    restrict_to_window: bool = False,
    include_unassigned_zero_point_events: bool = False,
    assigned_task_ids: set[str] | None = None,
    user_task_prefs: Mapping[str, Any] | None = None,
    target_user_id: str | int | None = None,
) -> list[dict[str, Any]]:
    """
    Convert ExtractedTask / dicts into scheduler-ready dicts with GMT+7 datetimes
    and expanded weekly recurrence slots (from DayTime or recurrence string).
    """
    if assigned_task_ids is None and user_task_prefs is not None:
        assigned_task_ids = set(user_task_prefs.keys())

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
        task_id = str(data.get("id") or "")
        pin_status, custom_st, custom_et = _extract_user_task_pref(
            user_task_prefs.get(task_id) if user_task_prefs is not None else data
        )
        if pin_status == "rejected":
            continue

        if custom_st is not None and custom_et is not None and custom_st < custom_et:
            data["start_time"] = custom_st
            data["end_time"] = custom_et
            data["_daytime_recurrence"] = None

        if not _should_keep_task(
            data,
            include_unassigned_zero_point_events=include_unassigned_zero_point_events,
            assigned_task_ids=assigned_task_ids,
            target_user_id=target_user_id,
        ):
            continue

        task_type = str(data.get("type") or "").lower()
        parsed_recurrence = data.get("_daytime_recurrence") or parse_recurrence(
            data.get("recurrence")
        )
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
                    _tag_cs1_for_class_exam(occurrence, task_type)
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
            if (eff_end - eff_start) >= timedelta(hours=3.5):
                clamped_start = max(eff_start, win_start_dt)
                clamped_end = min(eff_end, win_end_dt - timedelta(seconds=1))
                if clamped_start < clamped_end:
                    interval = (clamped_start, clamped_end)

        task_entry = dict(data)
        eff_start, eff_end = interval
        task_entry["start_time"] = eff_start
        task_entry["end_time"] = eff_end
        if restrict_to_window and isinstance(task_entry.get("deadline"), datetime):
            if task_entry["deadline"] >= win_end_dt:
                task_entry["deadline"] = eff_end
        task_entry["pin_status"] = pin_status
        task_entry["is_pinned"] = bool(data.get("is_pinned")) or pin_status == "pinned"
        _tag_cs1_for_class_exam(task_entry, task_type)
        prepared.append(task_entry)

    return prepared


class SchedulingService:
    """Coordinates reading tasks from Supabase repositories (or in-memory lists) and running B&B."""

    def __init__(
        self,
        task_repository: TaskRepository | None = None,
        user_task_repository: UserTaskRepository | None = None,
        scheduler: BranchAndBoundScheduler | None = None,
    ) -> None:
        self.task_repository = task_repository
        self.user_task_repository = user_task_repository
        self.scheduler = scheduler or BranchAndBoundScheduler()

    def run_for_tasks(
        self,
        tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]],
        *,
        user_id: str | int | None = None,
        initial_drl: Mapping[str, int] | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
        restrict_to_window: bool = True,
        include_unassigned_zero_point_events: bool = False,
        assigned_task_ids: set[str] | None = None,
        user_task_prefs: Mapping[str, Any] | None = None,
    ) -> ScheduleRunResult:
        resolved_start, resolved_end = _resolve_window(week_start, week_end)
        prepared_tasks = prepare_tasks_for_scheduler(
            tasks,
            week_start=resolved_start,
            week_end=resolved_end,
            restrict_to_window=restrict_to_window,
            include_unassigned_zero_point_events=include_unassigned_zero_point_events,
            assigned_task_ids=assigned_task_ids,
            user_task_prefs=user_task_prefs,
            target_user_id=user_id,
        )
        schedule_result = self.scheduler.schedule(
            prepared_tasks,
            initial_drl=dict(initial_drl) if initial_drl is not None else None,
        )
        return ScheduleRunResult(
            schedule=schedule_result,
            week_start=resolved_start,
            week_end=resolved_end,
            total_tasks_loaded=len(tasks),
            prepared_tasks_count=len(prepared_tasks),
        )

    def run_from_supabase(
        self,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        initial_drl: Mapping[str, int] | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
        restrict_to_window: bool = True,
        user_task_prefs: Mapping[str, Any] | None = None,
    ) -> ScheduleRunResult:
        task_repo = self.task_repository or TaskRepository(access_token=access_token)
        public_tasks = task_repo.get_tasks()

        personal_tasks: list[ExtractedTask] = []
        if user_id is not None:
            user_task_repo = self.user_task_repository or UserTaskRepository(
                access_token=access_token, user_id=user_id
            )
            personal_tasks = user_task_repo.get_tasks()

        assigned_ids = {t.id for t in personal_tasks if t.id}
        all_tasks = list(public_tasks) + list(personal_tasks)
        return self.run_for_tasks(
            all_tasks,
            user_id=user_id,
            initial_drl=initial_drl,
            week_start=week_start,
            week_end=week_end,
            restrict_to_window=restrict_to_window,
            assigned_task_ids=assigned_ids or None,
            user_task_prefs=user_task_prefs,
        )


__all__ = [
    "GMT_PLUS_7",
    "ScheduleRunResult",
    "SchedulingService",
    "current_week_bounds",
    "normalize_to_gmt7",
    "parse_recurrence",
    "prepare_tasks_for_scheduler",
]
