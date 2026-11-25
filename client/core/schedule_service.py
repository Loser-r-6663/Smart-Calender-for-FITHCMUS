from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from DataProcessor.Standardization.BaseTask import DateDayTime, Location
from DataProcessor.Standardization.Task import Task
from Database.Repository.local_task_repository import LocalTaskRepository
from Scheduler.scheduler import BranchAndBoundScheduler, DRL_CAPS
from client.core.models import (
    CalendarItem,
    ScheduleProposal,
    ScheduleViewData,
    TaskDraft,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DRL_ARTICLES = ("Articles 1", "Articles 2", "Articles 3", "Articles 4", "Articles 5")


def normalize_drl(points: dict[str, int] | None) -> dict[str, int]:
    raw = points or {}
    return {
        cat: min(max(0, int(raw.get(cat, 0) or 0)), DRL_CAPS[cat])
        for cat in DRL_ARTICLES
    }


def apply_draft_to_task(
    draft: TaskDraft,
    existing: Task | None = None,
    *,
    task_id: str | None = None,
) -> Task:
    recurrence = bool(draft.recurrence and draft.weekday)
    if recurrence:
        start_dt = DateDayTime(day=draft.weekday, time=draft.start_time)
        end_dt = (
            DateDayTime(day=draft.weekday, time=draft.end_time)
            if draft.end_time
            else None
        )
    else:
        start_dt = (
            DateDayTime(date=draft.scheduled_date, time=draft.start_time)
            if draft.scheduled_date
            else None
        )
        end_dt = (
            DateDayTime(date=draft.scheduled_date, time=draft.end_time)
            if draft.scheduled_date and draft.end_time
            else None
        )

    loc = None
    if draft.location or draft.campus:
        loc = Location(
            room=draft.location,
            campus=draft.campus,
            detail=existing.location.detail if existing and existing.location else None,
        )

    points = draft.training_points
    category = draft.training_point_category
    if points == 0:
        category = None

    compulsory = draft.compulsory
    flexible = draft.flexible
    if draft.kind == "class" and existing is None and not draft.compulsory:
        compulsory = True
    if draft.kind == "assignment" and existing is None and not draft.flexible:
        compulsory = True
        flexible = True

    source_platform = existing.source_platform if existing else "Custom"
    source_url = (
        draft.source_url
        if draft.source_url is not None
        else (existing.source_url if existing else "")
    )
    status = existing.status if existing and existing.status == "rejected" else "proposed"

    return Task(
        id=task_id or (existing.id if existing else str(uuid4())),
        title=draft.title,
        type=draft.kind,
        course=draft.course,
        description=draft.description,
        target_audience=existing.target_audience if existing else None,
        location=loc,
        registration_start=existing.registration_start if existing else None,
        registration_end=existing.registration_end if existing else None,
        start_time=start_dt,
        end_time=end_dt,
        deadline=draft.deadline,
        training_points=points,
        training_point_category=category,
        estimated_hours=draft.estimated_hours,
        source_url=source_url or "",
        source_platform=source_platform,
        updated_at=datetime.now(VN_TZ),
        recurrence=recurrence,
        status=status,
        compulsory=compulsory,
        flexible=flexible,
        user_modified=True,
    )


def task_to_calendar_item(
    task: Task,
    *,
    schedule_reason: str | None = None,
    is_personal: bool | None = None,
) -> CalendarItem:
    raw_id = task.id or str(uuid4())
    base_task_id = raw_id.split("#s")[0]
    is_allocated = "#s" in raw_id or (
        task.flexible and task.status == "scheduled" and task.start_time is not None and task.start_time.time is not None
    )

    start_at: datetime | None = None
    end_at: datetime | None = None
    weekday: str | None = None

    if task.start_time:
        weekday = task.start_time.day
        if task.start_time.date:
            start_at = datetime.combine(
                task.start_time.date,
                task.start_time.time or time.min,
                tzinfo=VN_TZ,
            )
    if task.end_time and (task.end_time.date or (task.start_time and task.start_time.date)):
        end_date = task.end_time.date or task.start_time.date
        if end_date and task.end_time.time:
            end_at = datetime.combine(end_date, task.end_time.time, tzinfo=VN_TZ)

    room = task.location.room if task.location else None
    campus = task.location.campus if task.location else None
    detail = task.location.detail if task.location else None
    loc_parts = [p.strip() for p in (room, campus, detail) if p and p.strip()]
    loc_label = " · ".join(dict.fromkeys(loc_parts)) or None

    personal_flag = (
        is_personal
        if is_personal is not None
        else task.source_platform in {"Custom", "Portal", "Moodle"}
    )

    return CalendarItem(
        id=f"sched:{raw_id}",
        task_id=base_task_id,
        title=task.title,
        kind=task.type,
        start=start_at,
        end=end_at,
        deadline=task.deadline,
        course=task.course,
        location=loc_label,
        room=room,
        campus=campus,
        description=task.description,
        points=task.training_points,
        training_point_category=task.training_point_category,
        estimated_hours=task.estimated_hours,
        source=task.source_platform,
        source_url=task.source_url or None,
        is_personal=personal_flag,
        status=task.status,
        recurrence=task.recurrence,
        weekday=weekday,
        flexible=task.flexible,
        compulsory=task.compulsory,
        schedule_reason=schedule_reason,
        is_allocated_session=is_allocated,
    )


def build_schedule_view_data(
    tasks: list[Task],
    *,
    initial_drl: dict[str, int] | None = None,
    database: LocalTaskRepository | None = None,
    week_anchor: date | None = None,
) -> ScheduleViewData:
    now = datetime.now(VN_TZ)
    today = now.date()
    anchor = week_anchor or today
    week_start = anchor - timedelta(days=anchor.weekday())
    week_end = week_start + timedelta(days=6)

    current_week_start = today - timedelta(days=today.weekday())
    if week_start == current_week_start:
        ref_dt = now
    else:
        ref_dt = datetime.combine(week_start, time(0, 0), tzinfo=VN_TZ)

    clean_initial = normalize_drl(initial_drl)
    scheduler = BranchAndBoundScheduler(database)
    result = scheduler.schedule(
        tasks,
        initial_drl=clean_initial,
        reference_time=ref_dt,
        include_past_fixed_in_week=True,
    )

    scheduled_items = sorted(
        [task_to_calendar_item(t) for t in result.scheduled_tasks],
        key=lambda item: (
            item.start or datetime.max.replace(tzinfo=VN_TZ),
            item.end or datetime.max.replace(tzinfo=VN_TZ),
        ),
    )
    unschedulable = [
        ScheduleProposal(
            item=task_to_calendar_item(info.task, schedule_reason=info.reason),
            reason=info.reason,
        )
        for info in result.unschedulable_tasks
    ]
    unselected = [
        ScheduleProposal(
            item=task_to_calendar_item(info.task, schedule_reason=info.reason),
            reason=info.reason,
        )
        for info in result.unselected_tasks
    ]
    rejected_items = [
        task_to_calendar_item(t, schedule_reason="Removed from schedule by user")
        for t in tasks
        if t.status == "rejected"
    ]

    return ScheduleViewData(
        week_start=week_start,
        week_end=week_end,
        scheduled_items=scheduled_items,
        unschedulable=unschedulable,
        unselected=unselected,
        rejected_items=rejected_items,
        initial_drl=clean_initial,
        final_drl=dict(result.final_drl),
        drl_caps=dict(DRL_CAPS),
    )
