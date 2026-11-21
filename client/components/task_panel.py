from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from client.core.controller import ClientController


def render_task_panel(
    controller: ClientController,
    *,
    on_select_item: Callable[[str], None],
) -> None:
    selected_date = controller.state.selected_date
    items = controller.items_for_date(selected_date)
    selected = controller.selected_item

    with ui.element("aside").classes("task-panel"):
        ui.label("Selected date").classes("eyebrow")
        ui.label(f"{selected_date:%A, %B} {selected_date.day}").classes("selected-date")
        ui.label(f"{len(items)} item{'s' if len(items) != 1 else ''}").classes(
            "selected-count"
        )

        with ui.column().classes("selected-list gap-2 w-full"):
            if not items:
                with ui.column().classes("empty-day items-center gap-2 w-full"):
                    ui.icon("event_available", size="32px")
                    ui.label("No items on this date").classes("empty-title")
            for item in items:
                with ui.element("button").classes(
                    " ".join(
                        (
                            "selected-item",
                            f"selected-kind-{item.kind}",
                            "active" if selected and selected.id == item.id else "",
                        )
                    )
                ).on("click", lambda chosen=item: on_select_item(chosen.id)):
                    ui.element("span").classes(f"item-dot kind-{item.kind}")
                    with ui.column().classes("gap-0 items-start min-w-0"):
                        ui.label(item.title).classes("selected-item-title")
                        ui.label(item.time_label).classes("selected-item-meta")

        if selected:
            ui.separator().classes("panel-separator")
            with ui.column().classes(
                f"task-detail detail-kind-{selected.kind} gap-3 w-full"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label(selected.kind.title()).classes(
                        f"type-badge solid-kind-{selected.kind}"
                    )
                    if selected.points is not None:
                        ui.label(f"+{selected.points} training points").classes("points-label")
                ui.label(selected.title).classes("detail-title")
                if selected.description:
                    ui.label(selected.description).classes("detail-description")
                for icon, value in (
                    ("schedule", selected.time_label),
                    ("school", selected.course),
                    ("location_on", selected.location),
                    ("storage", selected.source),
                ):
                    if value:
                        with ui.row().classes("detail-row items-start gap-2"):
                            ui.icon(icon, size="18px")
                            ui.label(value)
                if selected.source_url:
                    ui.link(
                        "Open official source",
                        selected.source_url,
                        new_tab=True,
                    ).classes("source-link")

