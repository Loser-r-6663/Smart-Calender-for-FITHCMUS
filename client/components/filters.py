from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from client.core.models import CalendarItem, ClientState


FILTERS = (
    ("all", "All"),
    ("class", "Classes"),
    ("assignment", "Assignments"),
    ("event", "Events"),
    ("announcement", "Notices"),
)


def render_filters(
    state: ClientState,
    search_items: list[CalendarItem],
    *,
    on_filter: Callable[[str], None],
    on_view: Callable[[str], None],
    on_search_result: Callable[[str], None],
) -> None:
    with ui.row().classes("filter-row items-center justify-between w-full"):
        with ui.row().classes("filter-group items-center gap-1"):
            for value, label in FILTERS:
                ui.button(
                    label,
                    on_click=lambda selected=value: on_filter(selected),
                ).props("flat no-caps").classes(
                    f"filter-button {'active' if state.filters.kind == value else ''}"
                )

        with ui.row().classes("filter-tools items-center gap-2"):
            search_options = {
                item.id: " · ".join(
                    part
                    for part in (
                        item.title,
                        item.day.strftime("%d %b") if item.day else None,
                        item.source,
                    )
                    if part
                )
                for item in search_items
            }
            search = ui.select(
                options=search_options,
                with_input=True,
                clearable=True,
                on_change=lambda event: (
                    on_search_result(str(event.value)) if event.value else None
                ),
            ).props(
                'dense outlined options-dense behavior=menu placeholder="Search tasks"'
            ).classes(
                "search-input"
            )
            with search.add_slot("prepend"):
                ui.icon("search", size="18px")
            with ui.element("div").classes("view-switch"):
                ui.button(
                    "Calendar",
                    icon="calendar_view_month",
                    on_click=lambda: on_view("calendar"),
                ).props("flat no-caps").classes(
                    "active" if state.view == "calendar" else ""
                )
                ui.button(
                    "Agenda",
                    icon="view_agenda",
                    on_click=lambda: on_view("agenda"),
                ).props("flat no-caps").classes(
                    "active" if state.view == "agenda" else ""
                )

