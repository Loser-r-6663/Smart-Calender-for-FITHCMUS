from __future__ import annotations

import calendar as month_calendar
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dataclasses import replace
from academic_search import SearchSnapshot, search_records
from client.core.backend import ClientBackend, SessionExpiredError
from client.core.models import CalendarItem, ClientState, ClientUser


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WEEKDAYS = {"T2": 0, "T3": 1, "T4": 2, "T5": 3, "T6": 4, "T7": 5, "CN": 6}


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        exact_date = _parse_date(_value(value, "date")) if value is not None else None
        if exact_date is None:
            return None
        exact_time = _parse_time(_value(value, "time"))
        return datetime.combine(exact_date, exact_time or time.min, tzinfo=VN_TZ)
    return result.replace(tzinfo=VN_TZ) if result.tzinfo is None else result.astimezone(VN_TZ)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return time.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _weekly_time(value: Any) -> tuple[str, int, time | None] | None:
    day = _value(value, "day") if value is not None else None
    raw_time = _value(value, "time") if value is not None else None
    if raw_time is None and value is not None:
        raw_time = _value(value, "time_")
    if day not in WEEKDAYS:
        return None
    parsed_time = _parse_time(raw_time) if raw_time is not None else None
    return day, WEEKDAYS[day], parsed_time


def _location_fields(value: Any) -> tuple[str | None, str | None, str | None]:
    if value is None:
        return None, None, None
    if isinstance(value, str):
        clean = value.strip() or None
        return clean, clean, None
    room = _value(value, "room")
    campus = _value(value, "campus")
    detail = _value(value, "detail")
    parts = [room, campus, detail]
    compact = [str(part).strip() for part in parts if part]
    label = " · ".join(dict.fromkeys(compact)) or None
    return label, room, campus


class TaskMapper:
    """Translate backend records into stable calendar presentation models."""

    @classmethod
    def map_range(
        cls, record: Any, range_start: date, range_end: date
    ) -> list[CalendarItem]:
        task_id = str(_value(record, "id") or f"task-{id(record)}")
        scheduled = _value(record, "scheduled_occurrences", [])
        if scheduled:
            occurrences = []
            for occurrence in scheduled:
                values = record.model_dump() if hasattr(record, "model_dump") else dict(record)
                values.update(start_time=_value(occurrence, "start_time"), end_time=_value(occurrence, "end_time"),
                              scheduled_occurrences=[])
                for item in cls.map_range(values, range_start, range_end):
                    occurrences.append(replace(item, id=f"{task_id}:{item.start.isoformat()}"))
            return occurrences

        loc_label, room, campus = _location_fields(_value(record, "location"))
        raw_source = _value(record, "source_platform")
        is_personal = bool(
            _value(record, "user_id")
            or raw_source in {"Custom", "Portal", "Moodle"}
            or (raw_source is None and not isinstance(record, dict))
        )
        source = raw_source or ("Custom" if is_personal else None)
        status = str(_value(record, "status") or "proposed")
        raw_start = _value(record, "start_time")
        raw_end = _value(record, "end_time")
        weekly_start = _weekly_time(raw_start)
        weekly_end = _weekly_time(raw_end)
        kind = str(_value(record, "type") or "announcement")

        recurrence = _value(record, "recurrence")
        if recurrence is None:
            recurrence = weekly_start is not None

        compulsory = _value(record, "compulsory")
        if compulsory is None:
            compulsory = kind in {"class", "assignment", "personal"}

        flexible = _value(record, "flexible")
        if flexible is None:
            flexible = kind == "assignment"

        common = {
            "task_id": task_id,
            "title": str(_value(record, "title") or "Untitled task"),
            "kind": kind,
            "course": _value(record, "course"),
            "location": loc_label,
            "room": room,
            "campus": campus,
            "description": _value(record, "description"),
            "points": _value(record, "training_points"),
            "training_point_category": _value(record, "training_point_category"),
            "estimated_hours": _value(record, "estimated_hours"),
            "source": source,
            "source_url": _value(record, "source_url"),
            "is_personal": is_personal,
            "status": status,
            "recurrence": bool(recurrence),
            "weekday": weekly_start[0] if weekly_start else None,
            "flexible": bool(flexible),
            "compulsory": bool(compulsory),
        }

        exact_start = _parse_datetime(raw_start)
        exact_end = _parse_datetime(raw_end)
        deadline = _parse_datetime(_value(record, "deadline"))

        if exact_start:
            return [
                CalendarItem(
                    id=task_id,
                    start=exact_start,
                    end=exact_end,
                    deadline=deadline,
                    **common,
                )
            ]

        if weekly_start and weekly_start[2] is not None:
            _, weekday, start_clock = weekly_start
            end_clock = weekly_end[2] if weekly_end else None
            current = range_start
            occurrences: list[CalendarItem] = []
            while current <= range_end:
                if current.weekday() == weekday:
                    start_at = datetime.combine(current, start_clock, tzinfo=VN_TZ)
                    end_at = (
                        datetime.combine(current, end_clock, tzinfo=VN_TZ)
                        if end_clock
                        else None
                    )
                    occurrences.append(
                        CalendarItem(
                            id=f"{task_id}:{current.isoformat()}",
                            start=start_at,
                            end=end_at,
                            deadline=deadline,
                            **common,
                        )
                    )
                current += timedelta(days=1)
            return occurrences

        return [
            CalendarItem(
                id=task_id,
                deadline=deadline,
                **common,
            )
        ]


class ClientController:
    def __init__(self, backend: ClientBackend, user: ClientUser | None = None) -> None:
        self.backend = backend
        self.state = ClientState(user=user)
        self._schedule_generation = 0
        self._generation = 0
        self._selection_session = 0
        self._loaded_tasks = None
        self._search_filters = {}
        self._search_sort = None
        self.backend.watch(self)

    def _clear_tasks(self) -> None:
        self._loaded_tasks = None
        self.state.schedule = None
        self.state.items = []
        self.state.search_snapshot = SearchSnapshot((), (), None)
        self.state.selected_item_id = None
        self.state.selected_search_key = None

    def set_user(self, user: ClientUser | None) -> None:
        self._generation += 1
        self._selection_session += 1
        self._schedule_generation += 1
        self._clear_tasks()
        self.state.user = user
        self.state.search_query = ""
        self.state.filters.query = ""
        self.state.filters.kind = "all"
        self._search_filters = {}
        self._search_sort = None
        self.state.error = None
        self.state.session_expired = False
        self.state.loading = False

    def logout(self) -> None:
        if self.state.user is not None:
            self.backend.logout(self.state.user)
        else:
            self.set_user(None)

    async def login(self, username: str, password: str) -> ClientUser:
        self.logout()
        generation = self._generation
        user = await self.backend.login(username, password)
        if generation != self._generation:
            raise SessionExpiredError("Session changed during sign in.")
        self.set_user(user)
        return user

    @staticmethod
    def month_bounds(month: date) -> tuple[date, date]:
        weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(
            month.year, month.month
        )
        return weeks[0][0], weeks[-1][-1]

    async def load_month(self, month: date | None = None) -> None:
        if self.state.user is None:
            return
        if month is not None:
            self.state.visible_month = month.replace(day=1)
        self._generation += 1
        generation = self._generation
        user = self.state.user
        self.state.loading = True
        self.state.error = None
        selected_search_key = self.state.selected_search_key
        self._clear_tasks()
        try:
            loaded = await self.backend.load_tasks(user)
            if generation != self._generation or self.state.user is not user:
                return
            self._loaded_tasks = loaded
            self.state.search_snapshot = loaded.snapshot
            self.show_month(self.state.visible_month)
            if selected_search_key is not None:
                if loaded.snapshot.get_task(selected_search_key) is not None:
                    self.state.selected_search_key = selected_search_key
        except SessionExpiredError:
            if generation == self._generation and self.state.user is user:
                self.backend.logout(user)
                self.state.session_expired = True
                self.state.error = "Session expired. Sign in again."
        except Exception as exc:
            if generation == self._generation and self.state.user is user:
                self.state.error = str(exc)
        finally:
            if generation == self._generation:
                self.state.loading = False

    def show_month(self, month: date) -> None:
        self.state.visible_month = month.replace(day=1)
        if self._loaded_tasks is None:
            return
        start, end = self.month_bounds(self.state.visible_month)
        self.state.items = [
            replace(item, id=f"{key[0]}:{item.id}", scope=key[0], is_personal=key[0] == "personal")
            for task, key in zip(self._loaded_tasks.tasks, self._loaded_tasks.calendar_keys or
                                 tuple(record.key for record in self._loaded_tasks.snapshot.records))
            for item in TaskMapper.map_range(task, start, end)
            if item.day is not None and start <= item.day <= end
        ]
        self.select_date(self.state.selected_date)

    def search(self, query: str, *, filters=None, sort=None):
        self.state.search_query = query
        self._search_filters = {} if filters is None else dict(filters)
        self._search_sort = sort
        return self.search_results

    @property
    def search_results(self):
        filters = dict(self._search_filters)
        return search_records(self.state.search_snapshot.records, self.state.search_query,
                              filters=filters, sort=self._search_sort)

    @property
    def selected_search_record(self):
        return self.state.search_snapshot.get_task(self.state.selected_search_key)

    @property
    def selection_session(self) -> int:
        return self._selection_session

    def select_search_record(self, key, *, session: int) -> bool:
        if (session != self._selection_session or self.state.user is None
                or self.state.search_snapshot.get_task(key) is None):
            return False
        self.state.selected_search_key = key
        return True

    def select_date(self, selected: date) -> None:
        self.state.selected_date = selected
        day_items = self.items_for_date(selected)
        self.state.selected_item_id = day_items[0].id if day_items else None

    def select_item(self, item_id: str) -> None:
        self.state.selected_item_id = item_id

    @property
    def filtered_items(self) -> list[CalendarItem]:
        kind = self.state.filters.kind
        query = self.state.filters.query.strip().casefold()
        items = self.active_items
        if kind != "all":
            items = [item for item in items if item.kind == kind]
        if query:
            items = [
                item
                for item in items
                if query
                in " ".join(
                    value
                    for value in (item.title, item.course or "", item.source or "")
                    if value
                ).casefold()
            ]
        return items

    @property
    def training_points_this_month(self) -> int:
        """Temporary client-side total until the backend scheduler is integrated.

        This sums point-bearing events already loaded by the client. Replace it
        with the scheduler's authoritative monthly result once that service is
        merged into the active backend and exposed through ClientBackend.
        """
        month = self.state.visible_month
        return sum(
            item.points or 0
            for item in self._unique_point_events()
            if item.day and item.day.year == month.year and item.day.month == month.month
        )

    @property
    def training_points_overall(self) -> int:
        """Temporary client-side total until the backend scheduler is integrated.

        This is an aggregate of loaded event records, not an optimized or
        expected score. Replace it with the scheduler response when available.
        """
        return sum(record.training_points or 0 for record in self.state.search_snapshot.records
                   if record.type == "event")

    def _unique_point_events(self) -> list[CalendarItem]:
        unique: dict[str, CalendarItem] = {}
        for item in self.state.items:
            if item.kind == "event" and item.points:
                unique.setdefault(item.task_id, item)
        return list(unique.values())

    def items_for_date(self, selected: date) -> list[CalendarItem]:
        return sorted(
            [item for item in self.filtered_items if item.day == selected],
            key=lambda item: item.start or item.deadline or datetime.max.replace(tzinfo=VN_TZ),
        )

    @property
    def selected_item(self) -> CalendarItem | None:
        target = self.state.selected_item_id
        if not target:
            return None
        for item in self.filtered_items:
            if item.id == target:
                return item
        for item in self._all_schedule_items():
            if item.id == target:
                return item
        for item in self.state.items:
            if item.id == target or item.task_id == target:
                return item
        return None

    def set_filter(self, kind: str) -> None:
        self.state.filters.kind = kind
        self.select_date(self.state.selected_date)

    def set_query(self, query: str) -> None:
        self.search(query)

    def set_view(self, view: str) -> None:
        self.state.view = view

    def week_anchor_date(self) -> date:
        return date.today() + timedelta(days=7 * self.state.schedule_week_offset)

    @property
    def active_items(self) -> list[CalendarItem]:
        """Calendar/Agenda items excluding tasks explicitly removed from schedule."""
        items = list(self.state.items)
        if self.state.view == "agenda" and self._loaded_tasks is not None:
            start, end = self.month_bounds(self.state.visible_month)
            keys = self._loaded_tasks.calendar_keys or tuple(r.key for r in self._loaded_tasks.snapshot.records)
            items.extend(
                replace(item, id=f"{key[0]}:{item.id}", scope=key[0], is_personal=key[0] == "personal")
                for task, key in zip(self._loaded_tasks.tasks, keys)
                for item in TaskMapper.map_range(task, start, end) if item.day is None
            )
        return [item for item in items if item.status != "rejected"]

    @property
    def scheduled_drl_total(self) -> int | None:
        if self.state.schedule is None:
            return None
        return min(100, sum(self.state.schedule.final_drl.values()))

    @property
    def scheduled_drl_gain(self) -> int | None:
        if self.state.schedule is None:
            return None
        base = sum(self.state.schedule.initial_drl.values())
        final = sum(self.state.schedule.final_drl.values())
        return max(0, final - base)

    def find_item_by_task_id(self, task_id: str) -> CalendarItem | None:
        if self.state.schedule is not None:
            for candidate in self._all_schedule_items():
                if candidate.task_id == task_id and not candidate.is_allocated_session:
                    return candidate
        for candidate in self.state.items:
            if candidate.task_id == task_id:
                return candidate
        if self.state.schedule is not None:
            for candidate in self._all_schedule_items():
                if candidate.task_id == task_id:
                    return candidate
        return None

    def _all_schedule_items(self) -> list[CalendarItem]:
        sched = self.state.schedule
        if sched is None:
            return []
        return [
            *sched.scheduled_items,
            *(p.item for p in sched.unschedulable),
            *(p.item for p in sched.unselected),
            *sched.rejected_items,
        ]

    def set_schedule_tab(self, tab: str) -> None:
        self.state.schedule_tab = tab

    async def load_schedule(self, week_offset: int | None = None) -> None:
        if self.state.user is None:
            return
        if week_offset is not None:
            self.state.schedule_week_offset = week_offset
        self._schedule_generation += 1
        schedule_generation = self._schedule_generation
        generation, user = self._generation, self.state.user
        self.state.loading = True
        self.state.error = None
        try:
            result = await self.backend.run_schedule(
                self.state.user,
                week_anchor=self.week_anchor_date(),
            )
            if generation != self._generation or schedule_generation != self._schedule_generation or self.state.user is not user:
                return
            self.state.schedule = result
            # Select the first populated review tab.
            sched = self.state.schedule
            if self.state.schedule_tab == "needs_info" and not sched.unschedulable:
                if sched.unselected:
                    self.state.schedule_tab = "suggestions"
                elif sched.rejected_items:
                    self.state.schedule_tab = "removed"
        except Exception as exc:
            if generation == self._generation and self.state.user is user:
                self.state.error = str(exc)
        finally:
            if generation == self._generation and schedule_generation == self._schedule_generation:
                self.state.loading = False
