from __future__ import annotations

import calendar as month_calendar
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from client.core.backend import ClientBackend
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
        return None
    return result.replace(tzinfo=VN_TZ) if result.tzinfo is None else result.astimezone(VN_TZ)


def _weekly_time(value: Any) -> tuple[int, time] | None:
    day = _value(value, "day") if value is not None else None
    raw_time = _value(value, "time_") if value is not None else None
    if day not in WEEKDAYS or raw_time is None:
        return None
    if isinstance(raw_time, time):
        parsed_time = raw_time
    else:
        try:
            parsed_time = time.fromisoformat(str(raw_time))
        except ValueError:
            return None
    return WEEKDAYS[day], parsed_time


def _location_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    parts = [
        _value(value, "room"),
        _value(value, "campus"),
        _value(value, "detail"),
    ]
    compact = [str(part).strip() for part in parts if part]
    return " · ".join(dict.fromkeys(compact)) or None


class TaskMapper:
    """Translate backend records into stable calendar presentation models."""

    @classmethod
    def map_range(
        cls, record: Any, range_start: date, range_end: date
    ) -> list[CalendarItem]:
        task_id = str(_value(record, "id") or f"task-{id(record)}")
        common = {
            "task_id": task_id,
            "title": str(_value(record, "title") or "Untitled task"),
            "kind": str(_value(record, "type") or "announcement"),
            "course": _value(record, "course"),
            "location": _location_label(_value(record, "location")),
            "description": _value(record, "description"),
            "points": _value(record, "training_points"),
            "source": _value(record, "source_platform"),
            "source_url": _value(record, "source_url"),
            "is_personal": bool(_value(record, "user_id")),
        }

        raw_start = _value(record, "start_time")
        raw_end = _value(record, "end_time")
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

        weekly_start = _weekly_time(raw_start)
        weekly_end = _weekly_time(raw_end)
        if weekly_start:
            weekday, start_clock = weekly_start
            end_clock = weekly_end[1] if weekly_end else None
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

    async def login(self, username: str, password: str) -> ClientUser:
        user = await self.backend.login(username, password)
        self.state.user = user
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
        start, end = self.month_bounds(self.state.visible_month)
        self.state.loading = True
        self.state.error = None
        try:
            tasks = await self.backend.get_tasks(self.state.user)
            self.state.items = [
                item
                for task in tasks
                for item in TaskMapper.map_range(task, start, end)
            ]
            self.select_date(self.state.selected_date)
        except Exception as exc:
            self.state.error = str(exc)
        finally:
            self.state.loading = False

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
        items = self.state.items
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
        return sum(item.points or 0 for item in self._unique_point_events())

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
        return next(
            (
                item
                for item in self.filtered_items
                if item.id == self.state.selected_item_id
            ),
            None,
        )

    def set_filter(self, kind: str) -> None:
        self.state.filters.kind = kind
        self.select_date(self.state.selected_date)

    def set_query(self, query: str) -> None:
        self.state.filters.query = query
        self.select_date(self.state.selected_date)

    def set_view(self, view: str) -> None:
        self.state.view = view

