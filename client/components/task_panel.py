from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from nicegui import ui

from client.core.controller import ClientController
from client.components.filters import VN_TZ, WEEKDAYS


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
            scope, _, task_id = selected.task_id.partition(":")
            record = controller.state.search_snapshot.get_task((scope, task_id))
            if record is not None:
                ui.separator().classes("panel-separator")
                render_record_details(record, occurrence=selected)
                return
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


def scheduled_time(value) -> str:
    if value.date is not None:
        day = value.date.strftime("%d %b %Y")
    elif value.day is not None:
        day = f"Every {WEEKDAYS[value.day]}"
    else:
        day = "Date not provided"
    return day + (value.time.strftime(", %H:%M") if value.time is not None else "")


def render_record_details(record, *, occurrence=None) -> None:
    with ui.column().classes(f"task-detail detail-kind-{record.type} gap-3 w-full"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Notice" if record.type == "announcement" else record.type.title()).classes(
                f"type-badge solid-kind-{record.type}")
            ui.label(record.scope.title()).classes("detail-scope")
        ui.label(record.title).classes("detail-title")
        ui.label(f"{record.training_points} training points" if record.training_points is not None
                 else "Training points not provided").classes("points-label")
        if record.description:
            ui.label(record.description).classes("detail-description")
        for label, value in (("Course", record.course), ("Publisher", record.publisher)):
            if value:
                ui.label(f"{label}: {value}").classes("detail-row")
        for label, value in (("Deadline", record.deadline),
                             ("Registration opens", record.registration_start),
                             ("Registration closes", record.registration_end)):
            if value is not None:
                ui.label(f"{label}: {value.astimezone(VN_TZ):%d %b %Y, %H:%M} (Vietnam)").classes("detail-row")
        for label, field in (("Scheduled start", "start_time"), ("Scheduled end", "end_time")):
            value = getattr(record, field)
            instant = getattr(occurrence, "start" if field == "start_time" else "end", None)
            if instant is not None:
                text = instant.astimezone(VN_TZ).strftime("%d %b %Y, %H:%M") + " (Vietnam)"
            elif value is not None:
                text = scheduled_time(value)
            else:
                continue
            ui.label(f"{label}: {text}").classes("detail-row")
        if record.deadline is None and not any(
            value is not None and value.date is not None for value in (record.start_time, record.end_time)
        ) and occurrence is None:
            ui.label("Date not provided").classes("detail-row")
        if occurrence is not None and occurrence.location:
            ui.label(f"Location: {occurrence.location}").classes("detail-row")
        try:
            source = urlsplit(record.source_url or "")
        except ValueError:
            return
        if source.scheme in {"http", "https"} and source.netloc:
            ui.link("Open official source", record.source_url, new_tab=True).classes("source-link")
