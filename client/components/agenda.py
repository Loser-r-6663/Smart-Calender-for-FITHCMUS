from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from nicegui import ui

from client.core.controller import ClientController


def render_agenda(
    controller: ClientController,
    *,
    on_select_item: Callable[[str], None],
) -> None:
    dated = defaultdict(list)
    undated = []
    for item in controller.filtered_items:
        if item.day:
            dated[item.day].append(item)
        else:
            undated.append(item)

    with ui.column().classes("agenda-list w-full gap-5"):
        if not dated and not undated:
            with ui.column().classes("empty-state items-center"):
                ui.icon("event_busy", size="34px")
                ui.label("No items match these filters")

        for day in sorted(dated):
            with ui.element("section").classes("agenda-day"):
                ui.label(day.strftime("%A, %d %B")).classes("agenda-date")
                for item in sorted(
                    dated[day], key=lambda entry: entry.start or entry.deadline
                ):
                    with ui.element("button").classes("agenda-item").on(
                        "click", lambda selected=item: on_select_item(selected.id)
                    ):
                        ui.element("span").classes(f"agenda-marker kind-{item.kind}")
                        with ui.column().classes("gap-0 items-start"):
                            ui.label(item.title).classes("agenda-title")
                            ui.label(
                                " · ".join(
                                    part
                                    for part in (
                                        item.time_label,
                                        item.course,
                                        item.location,
                                    )
                                    if part
                                )
                            ).classes("agenda-meta")

        if undated:
            with ui.element("section").classes("agenda-day"):
                ui.label("Undated notices").classes("agenda-date")
                for item in undated:
                    with ui.element("button").classes("agenda-item").on(
                        "click", lambda selected=item: on_select_item(selected.id)
                    ):
                        ui.element("span").classes(f"agenda-marker kind-{item.kind}")
                        with ui.column().classes("gap-0 items-start"):
                            ui.label(item.title).classes("agenda-title")
                            ui.label(item.source or "Announcement").classes("agenda-meta")

