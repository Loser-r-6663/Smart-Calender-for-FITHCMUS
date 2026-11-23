"""Integration service bridging ExtractedTask/Supabase tasks and BranchAndBoundScheduler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any

from pydantic import BaseModel

from DataProcessor.Standardization.BaseTask import DateDayTime
from DataProcessor.Standardization.ExtractedTask import ExtractedTask
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_repository import UserRepository
from Database.Repository.user_task_preference_repository import UserTaskPreferenceRepository
from Database.Repository.user_task_repository import UserTaskRepository

from .branch_and_bound_models import (
    BranchAndBoundResult,
    FIXED_TASK_TYPES,
    format_location_text,
    normalize_drl_category,
    parse_travel_buffer_value,
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
    if value is None:
        return None
    if isinstance(value, DateDayTime):
        if value.date is not None:
            return datetime.combine(value.date, value.time or time.min, tzinfo=GMT_PLUS_7)
        return None
    if isinstance(value, Mapping) and ("date" in value or "day" in value):
        d_raw = value.get("date")
        t_raw = value.get("time") or value.get("time_")
        if d_raw is not None:
            d_obj = date.fromisoformat(d_raw) if isinstance(d_raw, str) else d_raw
            t_obj = time.fromisoformat(t_raw) if isinstance(t_raw, str) else (t_raw or time.min)
            return datetime.combine(d_obj, t_obj, tzinfo=GMT_PLUS_7)
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
    """Extract weekly (weekday_index, start_time, end_time) from DateDayTime objects or dicts."""
    def _to_day_time(val: Any) -> tuple[str | None, time | None]:
        if isinstance(val, DateDayTime):
            if val.date is not None:
                return None, None
            return val.day, val.time
        if isinstance(val, Mapping) and ("day" in val or "time" in val or "time_" in val):
            if val.get("date") is not None:
                return None, None
            day = val.get("day")
            t_raw = val.get("time") if "time" in val else val.get("time_")
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
) -> tuple[str, datetime | None, datetime | None, int | dict[str, int] | None]:
    if pref is None:
        return "default", None, None, None
    if isinstance(pref, Mapping):
        pin_raw = pref.get("pin_status", "default")
        c_st = pref.get("custom_start_time")
        c_et = pref.get("custom_end_time")
        t_buf = pref.get("travel_buffer_minutes")
    else:
        pin_raw = getattr(pref, "pin_status", "default")
        c_st = getattr(pref, "custom_start_time", None)
        c_et = getattr(pref, "custom_end_time", None)
        t_buf = getattr(pref, "travel_buffer_minutes", None)

    pin_status = str(getattr(pin_raw, "value", pin_raw) or "default").lower()
    parsed_buf = parse_travel_buffer_value(t_buf)
    return pin_status, _coerce_datetime(c_st), _coerce_datetime(c_et), parsed_buf


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
        pin_status, custom_st, custom_et, pref_travel_buf = _extract_user_task_pref(
            user_task_prefs.get(task_id) if user_task_prefs is not None else data
        )
        if pin_status == "rejected":
            continue

        if pref_travel_buf is not None:
            data["travel_buffer_minutes"] = pref_travel_buf

        orig_interval = _effective_interval(data)
        if orig_interval is not None:
            data["_original_window_start"] = orig_interval[0]
            data["_original_window_end"] = orig_interval[1]

        if custom_st is not None and custom_et is not None and custom_st < custom_et:
            data["start_time"] = custom_st
            data["end_time"] = custom_et
            data["_daytime_recurrence"] = None
            data["_has_custom_time"] = True

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


def create_custom_task(
    title: str,
    start_time: datetime | str,
    end_time: datetime | str | None = None,
    *,
    task_id: str | None = None,
    task_type: str = "personal",
    location: str = "EXTERNAL",
    travel_buffer_minutes: int | Mapping[str, int] | str | None = None,
    estimated_hours: float | None = None,
    training_points: int = 0,
    drl_category: str | None = None,
    user_id: str | int | None = None,
) -> dict[str, Any]:
    """
    Tạo một Task do user tự nhập (hỗ trợ cả lịch bận cố định 'personal'/'class',
    bài tập linh hoạt 'assignment', hoặc hoạt động ĐRL tự thêm 'event'),
    kèm thời gian di chuyển ước tính (travel_buffer_minutes: int hoặc {'cs1': x, 'cs2': y}).
    """
    st_dt = _coerce_datetime(start_time)
    if st_dt is None:
        raise ValueError(f"Thời gian bắt đầu không hợp lệ: {start_time}")

    et_dt = _coerce_datetime(end_time) if end_time is not None else None
    if et_dt is None:
        dur_h = float(estimated_hours or (3.5 if task_type == "assignment" else 2.0))
        et_dt = st_dt + timedelta(hours=dur_h)
    if st_dt >= et_dt:
        raise ValueError("Thời gian kết thúc phải lớn hơn thời gian bắt đầu!")

    parsed_buf = parse_travel_buffer_value(travel_buffer_minutes)

    return {
        "id": task_id or f"user-custom-{int(datetime.now(GMT_PLUS_7).timestamp() * 1000)}",
        "user_id": user_id,
        "title": title.strip() or "Công việc cá nhân",
        "type": task_type.strip().lower() or "personal",
        "start_time": st_dt,
        "end_time": et_dt,
        "location": location.strip() or "EXTERNAL",
        "travel_buffer_minutes": parsed_buf,
        "estimated_hours": float(estimated_hours) if estimated_hours is not None else (et_dt - st_dt).total_seconds() / 3600.0,
        "training_points": max(0, int(training_points or 0)),
        "drl_category": normalize_drl_category(drl_category) or "dieu_3",
        "is_manual": True,
        "status": "active",
    }


def _parse_user_datetime_input(raw_str: str, default_date: date) -> datetime | None:
    """
    Hỗ trợ user nhập linh hoạt:
    - 'YYYY-MM-DD HH:MM' (VD: 2026-11-18 14:00)
    - 'DD/MM HH:MM' hoặc 'DD/MM/YYYY HH:MM' (VD: 18/11 14:00)
    - 'HH:MM' (dùng ngày default_date)
    """
    text = raw_str.strip()
    if not text:
        return None
    dt = _coerce_datetime(text)
    if dt is not None:
        return dt
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=GMT_PLUS_7)
        except ValueError:
            pass
    try:
        parsed_dm = datetime.strptime(text, "%d/%m %H:%M")
        return datetime(
            default_date.year,
            parsed_dm.month,
            parsed_dm.day,
            parsed_dm.hour,
            parsed_dm.minute,
            tzinfo=GMT_PLUS_7,
        )
    except ValueError:
        pass
    try:
        parsed_hm = datetime.strptime(text, "%H:%M").time()
        return datetime.combine(default_date, parsed_hm, tzinfo=GMT_PLUS_7)
    except ValueError:
        return None


class SchedulingService:
    """Coordinates reading tasks from Supabase repositories (or in-memory lists) and running B&B."""

    def __init__(
        self,
        task_repository: TaskRepository | None = None,
        user_task_repository: UserTaskRepository | None = None,
        user_task_preference_repository: UserTaskPreferenceRepository | None = None,
        scheduler: BranchAndBoundScheduler | None = None,
    ) -> None:
        self.task_repository = task_repository
        self.user_task_repository = user_task_repository
        self.user_task_preference_repository = user_task_preference_repository
        self.scheduler = scheduler or BranchAndBoundScheduler()

    def run_for_tasks(
        self,
        tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]],
        *,
        custom_tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]] | None = None,
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
        combined_tasks = list(tasks)
        merged_assigned_ids = set(assigned_task_ids) if assigned_task_ids is not None else set()
        if custom_tasks:
            for c_task in custom_tasks:
                combined_tasks.append(c_task)
                c_id = c_task.get("id") if isinstance(c_task, Mapping) else getattr(c_task, "id", None)
                if c_id:
                    merged_assigned_ids.add(str(c_id))

        prepared_tasks = prepare_tasks_for_scheduler(
            combined_tasks,
            week_start=resolved_start,
            week_end=resolved_end,
            restrict_to_window=restrict_to_window,
            include_unassigned_zero_point_events=include_unassigned_zero_point_events,
            assigned_task_ids=merged_assigned_ids if (assigned_task_ids is not None or custom_tasks) else None,
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
            total_tasks_loaded=len(combined_tasks),
            prepared_tasks_count=len(prepared_tasks),
        )

    def run_from_supabase(
        self,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        custom_tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]] | None = None,
        initial_drl: Mapping[str, int] | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
        restrict_to_window: bool = True,
        user_task_prefs: Mapping[str, Any] | None = None,
    ) -> ScheduleRunResult:
        task_repo = self.task_repository or TaskRepository(access_token=access_token)
        public_tasks = task_repo.get_tasks()

        personal_tasks: list[ExtractedTask] = []
        resolved_prefs = user_task_prefs
        if user_id is not None:
            user_task_repo = self.user_task_repository or UserTaskRepository(
                access_token=access_token, user_id=user_id
            )
            personal_tasks = user_task_repo.get_tasks()

            if resolved_prefs is None:
                try:
                    pref_repo = self.user_task_preference_repository or UserTaskPreferenceRepository(
                        access_token=access_token, user_id=user_id
                    )
                    resolved_prefs = pref_repo.get_preferences()
                except Exception:
                    resolved_prefs = None

        assigned_ids = {t.id for t in personal_tasks if t.id}
        all_tasks = list(public_tasks) + list(personal_tasks)
        return self.run_for_tasks(
            all_tasks,
            custom_tasks=custom_tasks,
            user_id=user_id,
            initial_drl=initial_drl,
            week_start=week_start,
            week_end=week_end,
            restrict_to_window=restrict_to_window,
            assigned_task_ids=assigned_ids or None,
            user_task_prefs=resolved_prefs,
        )

    def print_full_weekly_timetable(self, run_result: ScheduleRunResult) -> None:
        """In toàn bộ Lịch biểu tổng hợp trong tuần (Lịch học + Task cá nhân + Bài tập linh hoạt + Sự kiện ĐRL)."""
        res = run_result.schedule
        print("\n" + "=" * 88)
        print(
            f"LỊCH BIỂU TỔNG HỢP TUẦN ({run_result.week_start.strftime('%d/%m/%Y')} -> "
            f"{run_result.week_end.strftime('%d/%m/%Y')})"
        )
        print("=" * 88)

        def _fmt_travel_note(buf: Any) -> str:
            if not buf:
                return ""
            if isinstance(buf, Mapping):
                parts = [f"{k.upper()} ±{v}p" for k, v in sorted(buf.items())]
                return f" | Di chuyển: {', '.join(parts)}"
            return f" | Di chuyển: ±{buf}p"

        timeline: list[tuple[datetime, datetime, str, str, str]] = []
        for ft in res.fixed_tasks_summary:
            t_type = str(ft.get("type") or "personal").upper()
            buf_note = _fmt_travel_note(ft.get("travel_buffer_minutes"))
            loc = ft.get("location") or "CS1"
            timeline.append((
                ft["start_time"],
                ft["end_time"],
                f"[{t_type}]",
                ft["title"],
                f"{loc}{buf_note}",
            ))

        for ev in res.selected_events:
            flex_tag = " [Linh hoạt]" if ev.is_flexible else ""
            pin_tag = " [Đã ghim]" if ev.is_pinned else ""
            buf_note = _fmt_travel_note(ev.travel_buffer_minutes)
            timeline.append((
                ev.start_time,
                ev.end_time,
                f"[ĐRL +{ev.points_gained}đ {ev.drl_category}]{flex_tag}{pin_tag}",
                ev.title,
                f"{ev.location}{buf_note}",
            ))

        timeline.sort(key=lambda x: (x[0], x[1]))

        if not timeline:
            print("  (Chưa có hoạt động cố định hoặc sự kiện ĐRL nào trong tuần này).")
        else:
            for idx, (st, et, tag, title, loc_info) in enumerate(timeline, 1):
                st_str = st.strftime("%a %d/%m %H:%M")
                et_str = et.strftime("%H:%M") if st.date() == et.date() else et.strftime("%a %d/%m %H:%M")
                print(f"  {idx:>2}. [{st_str} -> {et_str}] {tag} {title} ({loc_info})")

        if res.flexible_tasks_summary:
            print("-" * 88)
            print("CÁC NHIỆM VỤ / BÀI TẬP LINH HOẠT ĐƯỢC BẢO VỆ QUỸ GIỜ TỰ HỌC (TIER 4):")
            for idx, wl in enumerate(res.flexible_tasks_summary, 1):
                w_st = wl["start_time"].strftime("%a %d/%m %H:%M")
                w_et = wl["end_time"].strftime("%a %d/%m %H:%M")
                print(
                    f"  {idx:>2}. [Hạn: {w_st} -> {w_et}] (Cần {wl['estimated_hours']:.1f}h) | {wl['title']}"
                )
        print("=" * 88)

    def interactive_adjust_schedule(
        self,
        base_tasks: Sequence[ExtractedTask | BaseModel | Mapping[str, Any]],
        initial_run: ScheduleRunResult,
        *,
        user_id: str | int | None = None,
        access_token: str | None = None,
        persist_to_db: bool = False,
        initial_user_prefs: Mapping[str, Any] | None = None,
        initial_drl: Mapping[str, int] | None = None,
        week_start: date | None = None,
        week_end: date | None = None,
        restrict_to_window: bool = True,
    ) -> ScheduleRunResult:
        """
        Menu tương tác cho phép User:
        1. Tự thêm Task cá nhân (lịch bận cố định / bài tập linh hoạt / sự kiện ĐRL) kèm thời gian di chuyển ước tính.
        2. Đổi khung giờ của Sự kiện ĐRL (đặc biệt là sự kiện linh hoạt) hoặc Task cá nhân trên lịch.
        3. Ghim (Pin - Bắt buộc chọn) một hoạt động ĐRL ứng viên.
        4. Loại bỏ (Reject - Bỏ qua) một hoạt động ĐRL trên lịch.
        5. Xem toàn bộ Lịch biểu tổng hợp trong tuần.
        """
        current_run = initial_run
        custom_tasks: list[dict[str, Any]] = []
        user_prefs: dict[str, dict[str, Any]] = {
            str(k): (v.model_dump() if hasattr(v, "model_dump") else dict(v))
            for k, v in (initial_user_prefs or {}).items()
        }
        current_drl: dict[str, int] = dict(
            initial_drl
            or initial_run.schedule.initial_drl
            or {"dieu_1": 0, "dieu_2": 0, "dieu_3": 0, "dieu_4": 0, "dieu_5": 0}
        )

        def _persist_custom_task(task_dict: dict[str, Any]) -> None:
            if not persist_to_db or user_id is None:
                return
            try:
                repo = self.user_task_repository or UserTaskRepository(
                    access_token=access_token, user_id=str(user_id)
                )
                resp = repo.save_tasks([task_dict])
                rows = resp.json() if hasattr(resp, "json") else []
                if isinstance(rows, list) and rows and rows[0].get("id"):
                    task_dict["id"] = str(rows[0]["id"])
                print("  [DB] Đã lưu Task cá nhân vào bảng 'user_task' trên Supabase.")
            except Exception as exc:
                print(f"  [!] Chưa thể lưu Task vào DB (chỉ lưu trong phiên hiện tại): {exc}")

        def _persist_preference(task_id: str, pref_entry: Mapping[str, Any]) -> None:
            if not persist_to_db or user_id is None:
                return
            try:
                pref_repo = self.user_task_preference_repository or UserTaskPreferenceRepository(
                    access_token=access_token, user_id=str(user_id)
                )
                pref_repo.upsert_preference(
                    task_id,
                    pin_status=str(pref_entry.get("pin_status") or "default"),
                    custom_start_time=pref_entry.get("custom_start_time"),
                    custom_end_time=pref_entry.get("custom_end_time"),
                    travel_buffer_minutes=pref_entry.get("travel_buffer_minutes"),
                )
                print("  [DB] Đã lưu tùy chỉnh lịch vào bảng 'user_task_preferences' trên Supabase.")
            except Exception as exc:
                print(f"  [!] Chưa thể lưu tùy chỉnh vào DB (chỉ lưu trong phiên hiện tại): {exc}")

        def _persist_schedule_outcome(run_res: ScheduleRunResult) -> None:
            if not persist_to_db or user_id is None:
                return
            try:
                pref_repo = self.user_task_preference_repository or UserTaskPreferenceRepository(
                    access_token=access_token, user_id=str(user_id)
                )
                pref_repo.save_schedule_outcome(
                    run_res.schedule.selected_events,
                    user_id=str(user_id),
                    existing_prefs=user_prefs,
                )
            except Exception:
                pass

        def _recompute() -> ScheduleRunResult:
            nonlocal current_run
            current_run = self.run_for_tasks(
                base_tasks,
                custom_tasks=custom_tasks,
                user_id=user_id,
                initial_drl=current_drl,
                week_start=week_start or current_run.week_start,
                week_end=week_end or current_run.week_end,
                restrict_to_window=restrict_to_window,
                user_task_prefs=user_prefs,
            )
            _persist_schedule_outcome(current_run)
            print("\n>>> ĐÃ CẬP NHẬT & TỐI ƯU LẠI LỊCH BIỂU! <<<")
            current_run.schedule.print_summary()
            return current_run

        while True:
            print("\n" + "-" * 88)
            print("MENU ĐIỀU CHỈNH LỊCH & THÊM TASK CÁ NHÂN:")
            print("  [1] Thêm Task cá nhân mới (kèm thời gian di chuyển ước tính)")
            print("  [2] Đổi khung giờ của hoạt động ĐRL trên lịch (Reschedule)")
            print("  [3] Ghim (Pin - Bắt buộc tham gia) một hoạt động ĐRL khác trong tuần")
            print("  [4] Loại bỏ (Reject - Không tham gia) một hoạt động ĐRL đang có trên lịch")
            print("  [5] Xem Lịch biểu tổng hợp cả tuần (Lịch học + Task cá nhân + ĐRL)")
            print("  [6] Cập nhật điểm ĐRL hiện có theo 5 Điều (dieu_1 -> dieu_5)")
            print("  [0] Hoàn tất & Kết thúc")
            print("-" * 88)

            try:
                choice = input("Chọn thao tác (0-6): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nKết thúc điều chỉnh lịch.")
                break

            if choice in {"0", "q", "quit", "exit", ""}:
                break

            elif choice == "1":
                print("\n--- [1] THÊM TASK CÁ NHÂN MỚI ---")
                title = input("  • Tên công việc (VD: Học IELTS / Họp nhóm / Làm thêm): ").strip()
                if not title:
                    print("  [!] Đã hủy thêm task (tên trống).")
                    continue

                print("  • Loại công việc: [1] Lịch bận cố định (mặc định) | [2] Bài tập/Tự học linh hoạt | [3] Sự kiện ĐRL tự thêm")
                t_choice = input("    Chọn loại (1/2/3): ").strip()
                task_type = "personal"
                t_points = 0
                drl_cat = "dieu_3"
                if t_choice == "2":
                    task_type = "assignment"
                elif t_choice == "3":
                    task_type = "event"
                    pts_raw = input("    Số điểm ĐRL của sự kiện (VD: 5): ").strip()
                    t_points = int(pts_raw) if pts_raw.isdigit() else 5
                    cat_raw = input("    Điều mấy (1-5, mặc định 3): ").strip()
                    drl_cat = f"dieu_{cat_raw}" if cat_raw in {"1", "2", "3", "4", "5"} else "dieu_3"

                st_raw = input(
                    f"  • Thời gian bắt đầu (VD: {current_run.week_start.strftime('%d/%m')} 18:00 hoặc YYYY-MM-DD HH:MM): "
                ).strip()
                st_dt = _parse_user_datetime_input(st_raw, current_run.week_start)
                if st_dt is None:
                    print("  [!] Không nhận diện được thời gian bắt đầu. Vui lòng nhập theo định dạng DD/MM HH:MM.")
                    continue

                et_raw = input(
                    f"  • Thời gian kết thúc / hạn chót (VD: {st_dt.strftime('%d/%m')} 20:00 hoặc HH:MM): "
                ).strip()
                et_dt = _parse_user_datetime_input(et_raw, st_dt.date())
                if et_dt is None or et_dt <= st_dt:
                    print("  [!] Thời gian kết thúc không hợp lệ (phải sau thời gian bắt đầu).")
                    continue

                est_h: float | None = None
                if task_type == "assignment":
                    est_raw = input("  • Số giờ cần thiết để hoàn thành (mặc định 3.5h): ").strip()
                    if est_raw:
                        try:
                            est_h = max(0.5, float(est_raw))
                        except ValueError:
                            est_h = 3.5

                location = input("  • Địa điểm (VD: Trung tâm Q3 / CS1 / CS2 / ONLINE, mặc định EXTERNAL): ").strip() or "EXTERNAL"
                travel_buf: int | dict[str, int] | None = None
                if "online" not in location.lower() and task_type != "assignment":
                    buf_raw = input(
                        "  • Thời gian di chuyển ước tính (phút) — nhập 'CS1, CS2' (VD: 15, 50) hoặc 1 số chung (VD: 30): "
                    ).strip()
                    if buf_raw:
                        travel_buf = parse_travel_buffer_value(buf_raw)

                new_task = create_custom_task(
                    title=title,
                    start_time=st_dt,
                    end_time=et_dt,
                    task_type=task_type,
                    location=location,
                    travel_buffer_minutes=travel_buf,
                    estimated_hours=est_h,
                    training_points=t_points,
                    drl_category=drl_cat,
                    user_id=user_id,
                )
                custom_tasks.append(new_task)
                _persist_custom_task(new_task)
                if t_points > 0 or travel_buf is not None:
                    pref_entry = dict(user_prefs.get(new_task["id"]) or {})
                    if t_points > 0:
                        pref_entry["pin_status"] = "pinned"
                    else:
                        pref_entry.setdefault("pin_status", "default")
                    if travel_buf is not None:
                        pref_entry["travel_buffer_minutes"] = travel_buf
                    user_prefs[new_task["id"]] = pref_entry
                    _persist_preference(new_task["id"], pref_entry)
                _recompute()

            elif choice == "2":
                selected = current_run.schedule.selected_events
                if not selected:
                    print("  [!] Hiện không có sự kiện ĐRL nào trên lịch để đổi giờ.")
                    continue
                print("\n--- [2] ĐỔI KHUNG GIỜ HOẠT ĐỘNG ĐRL TRÊN LỊCH ---")
                for idx, ev in enumerate(selected, 1):
                    flex_note = (
                        f" (Linh hoạt trong khoảng: {ev.window_start.strftime('%d/%m %H:%M')} -> {ev.window_end.strftime('%d/%m %H:%M')})"
                        if ev.is_flexible and ev.window_start and ev.window_end
                        else " (Sự kiện cố định)"
                    )
                    print(
                        f"  {idx}. [{ev.start_time.strftime('%a %d/%m %H:%M')} -> {ev.end_time.strftime('%H:%M')}] "
                        f"{ev.title}{flex_note}"
                    )
                idx_raw = input(f"  Chọn số thứ tự hoạt động muốn đổi giờ (1-{len(selected)}): ").strip()
                if not idx_raw.isdigit() or not (1 <= int(idx_raw) <= len(selected)):
                    print("  [!] Lựa chọn không hợp lệ.")
                    continue
                target_ev = selected[int(idx_raw) - 1]
                new_st_raw = input(
                    f"  • Nhập thời gian bắt đầu mới (VD: {target_ev.start_time.strftime('%d/%m')} 20:00): "
                ).strip()
                new_st = _parse_user_datetime_input(new_st_raw, target_ev.start_time.date())
                if new_st is None:
                    print("  [!] Thời gian bắt đầu không hợp lệ.")
                    continue

                default_dur = (target_ev.end_time - target_ev.start_time)
                new_et_raw = input(
                    f"  • Nhập thời gian kết thúc mới (Enter để giữ nguyên thời lượng {int(default_dur.total_seconds() // 60)} phút): "
                ).strip()
                if not new_et_raw:
                    new_et = new_st + default_dur
                else:
                    new_et = _parse_user_datetime_input(new_et_raw, new_st.date())

                if new_et is None or new_et <= new_st:
                    print("  [!] Thời gian kết thúc không hợp lệ.")
                    continue

                if target_ev.window_start and target_ev.window_end:
                    if new_st < target_ev.window_start or new_et > target_ev.window_end:
                        print(
                            f"  [!] Cảnh báo: Khung giờ mới nằm ngoài thời hạn mở của sự kiện "
                            f"({target_ev.window_start.strftime('%d/%m %H:%M')} -> {target_ev.window_end.strftime('%d/%m %H:%M')})."
                        )
                        confirm = input("  Bạn vẫn muốn áp dụng khung giờ này? (y/n): ").strip().lower()
                        if confirm != "y":
                            continue

                pref_entry = dict(user_prefs.get(target_ev.task_id) or {})
                pref_entry["custom_start_time"] = new_st
                pref_entry["custom_end_time"] = new_et
                pref_entry["pin_status"] = "pinned"
                user_prefs[target_ev.task_id] = pref_entry
                _persist_preference(target_ev.task_id, pref_entry)
                _recompute()

            elif choice == "3":
                unselected = current_run.schedule.unselected_events
                if not unselected:
                    print("  [!] Không còn hoạt động ĐRL khả thi nào khác trong tuần chưa được chọn.")
                    continue
                print("\n--- [3] GHIM (BẮT BUỘC THAM GIA) HOẠT ĐỘNG ĐRL KHÁC TRONG TUẦN ---")
                for idx, ev in enumerate(unselected, 1):
                    st_str = ev.start_time.strftime("%a %d/%m %H:%M")
                    et_str = (
                        ev.end_time.strftime("%H:%M")
                        if ev.start_time.date() == ev.end_time.date()
                        else ev.end_time.strftime("%a %d/%m %H:%M")
                    )
                    print(
                        f"  {idx}. [{st_str} -> {et_str}] (+{ev.training_points}đ {ev.drl_category}) | {ev.title} [{ev.location}]"
                    )
                idx_raw = input(f"  Chọn số thứ tự sự kiện muốn Ghim (1-{len(unselected)}): ").strip()
                if not idx_raw.isdigit() or not (1 <= int(idx_raw) <= len(unselected)):
                    print("  [!] Lựa chọn không hợp lệ.")
                    continue
                target_ev = unselected[int(idx_raw) - 1]
                pref_entry = dict(user_prefs.get(target_ev.task_id) or {})
                pref_entry["pin_status"] = "pinned"
                user_prefs[target_ev.task_id] = pref_entry
                _persist_preference(target_ev.task_id, pref_entry)
                _recompute()

            elif choice == "4":
                selected = current_run.schedule.selected_events
                if not selected:
                    print("  [!] Hiện không có sự kiện ĐRL nào trên lịch để loại bỏ.")
                    continue
                print("\n--- [4] LOẠI BỎ (REJECT) HOẠT ĐỘNG ĐRL KHỎI LỊCH ---")
                for idx, ev in enumerate(selected, 1):
                    print(
                        f"  {idx}. [{ev.start_time.strftime('%a %d/%m %H:%M')} -> {ev.end_time.strftime('%H:%M')}] "
                        f"(+{ev.points_gained}đ {ev.drl_category}) | {ev.title}"
                    )
                idx_raw = input(f"  Chọn số thứ tự sự kiện muốn loại bỏ (1-{len(selected)}): ").strip()
                if not idx_raw.isdigit() or not (1 <= int(idx_raw) <= len(selected)):
                    print("  [!] Lựa chọn không hợp lệ.")
                    continue
                target_ev = selected[int(idx_raw) - 1]
                user_prefs[target_ev.task_id] = {"pin_status": "rejected"}
                _persist_preference(target_ev.task_id, user_prefs[target_ev.task_id])
                custom_tasks = [t for t in custom_tasks if str(t.get("id")) != target_ev.task_id]
                _recompute()

            elif choice == "5":
                self.print_full_weekly_timetable(current_run)

            elif choice == "6":
                print("\n--- [6] CẬP NHẬT ĐIỂM ĐRL HIỆN CÓ (5 ĐIỀU) ---")
                print("  (Nhấn Enter để giữ nguyên điểm hiện tại của từng Điều)")
                for dieu_key in ("dieu_1", "dieu_2", "dieu_3", "dieu_4", "dieu_5"):
                    cur_val = current_drl.get(dieu_key, 0)
                    raw_val = input(f"  • {dieu_key} (hiện tại {cur_val}đ): ").strip()
                    if raw_val:
                        try:
                            current_drl[dieu_key] = max(0, int(raw_val))
                        except ValueError:
                            print(f"    [!] Giá trị '{raw_val}' không hợp lệ, giữ nguyên {cur_val}đ.")
                if persist_to_db and user_id is not None:
                    try:
                        UserRepository(access_token=access_token).update_drl_scores(
                            str(user_id), current_drl
                        )
                        print("  [DB] Đã lưu điểm ĐRL 5 Điều vào bảng 'users' trên Supabase.")
                    except Exception as exc:
                        print(f"  [!] Chưa thể lưu ĐRL vào DB (chỉ áp dụng trong phiên hiện tại): {exc}")
                _recompute()

            else:
                print("  [!] Vui lòng chọn từ 0 đến 6.")

        return current_run


__all__ = [
    "GMT_PLUS_7",
    "ScheduleRunResult",
    "SchedulingService",
    "create_custom_task",
    "current_week_bounds",
    "normalize_to_gmt7",
    "parse_recurrence",
    "prepare_tasks_for_scheduler",
]
