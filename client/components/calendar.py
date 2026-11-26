from __future__ import annotations

import calendar as month_calendar
from collections.abc import Callable
from datetime import date

from nicegui import ui

from client.core.controller import ClientController


WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def render_calendar(
    controller: ClientController,
    *,
    on_select_date: Callable[[date], None],
    on_select_item: Callable[[date, str], None],
) -> None:
    month = controller.state.visible_month
    weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(
        month.year, month.month
    )

    with ui.element("div").classes("month-grid"):
        for label in WEEKDAY_LABELS:
            ui.label(label).classes("weekday-label")

        for week in weeks:
            for day in week:
                day_items = controller.items_for_date(day)
                classes = ["day-cell"]
                if day.month != month.month:
                    classes.append("outside-month")
                if day == date.today():
                    classes.append("today")
                if day == controller.state.selected_date:
                    classes.append("selected")

                with ui.element("section").classes(" ".join(classes)):
                    ui.button(
                        str(day.day), on_click=lambda selected=day: on_select_date(selected)
                    ).props("flat round dense").classes("day-number")
                    with ui.column().classes("day-events gap-1 w-full"):
                        for item in day_items[:3]:
                            with ui.element("button").classes(
                                f"event-pill kind-{item.kind}"
                            ).on(
                                "click",
                                lambda selected=item, selected_day=day: on_select_item(
                                    selected_day, selected.id
                                ),
                            ):
                                with ui.element("span").classes("event-pill-content"):
                                    ui.label(item.title).classes("event-title")
                                    if item.kind == "event" and item.points:
                                        ui.label(f"+{item.points}").classes(
                                            "event-points"
                                        )
                        if len(day_items) > 3:
                            ui.label(f"+{len(day_items) - 3} more").classes("more-events")
