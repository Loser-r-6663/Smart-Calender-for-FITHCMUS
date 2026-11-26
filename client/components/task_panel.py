from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit
from client.components.filters import VN_TZ, WEEKDAYS

from nicegui import ui

from client.core.controller import ClientController


STATUS_LABELS = {
    "scheduled": ("Scheduled", "scheduled"),
    "rejected": ("Removed", "rejected"),
    "proposed": ("Unscheduled", "proposed"),
}


def render_task_panel(
    controller: ClientController,
    *,
    on_select_item: Callable[[str], None],
    on_edit_task: Callable[[str], None],
    on_remove_from_schedule: Callable[[str], None],
    on_restore_to_schedule: Callable[[str], None],
    on_delete_task: Callable[[str], None],
) -> None:
    selected_date = controller.state.selected_date
    if (
        controller.state.view == "schedule"
        and controller.state.schedule is not None
    ):
        items = [
            it
            for it in controller.state.schedule.scheduled_items
            if it.day == selected_date
        ]
    else:
        items = controller.items_for_date(selected_date)
    selected = controller.selected_item

    with ui.element("aside").classes("task-panel"):
        ui.label(
            "Scheduled on date"
            if controller.state.view == "schedule"
            else "Selected date"
        ).classes("eyebrow")
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
            status_text, status_cls = STATUS_LABELS.get(
                selected.status, ("Unscheduled", "proposed")
            )
            with ui.column().classes(
                f"task-detail detail-kind-{selected.kind} gap-3 w-full"
            ) as detail_container:
                scope = selected.scope
                record = controller.state.search_snapshot.get_task((scope, selected.task_id)) if scope else None
                if record is not None:
                    detail_container.classes(remove="task-detail")
                    ui.label(status_text).classes(f"status-chip {status_cls}")
                    render_record_details(record, occurrence=selected)
                else:
                    with ui.row().classes("items-center justify-between w-full wrap gap-1"):
                        with ui.row().classes("items-center gap-1"):
                            ui.label(selected.kind.title()).classes(
                                f"type-badge solid-kind-{selected.kind}"
                            )
                            ui.label(status_text).classes(f"status-chip {status_cls}")
                            if selected.flexible:
                                ui.label("Flexible").classes("status-chip proposed")
                        if selected.points is not None and selected.points > 0:
                            pts_text = f"+{selected.points} pts"
                            if selected.training_point_category:
                                pts_text += f" · {selected.training_point_category}"
                            ui.label(pts_text).classes("points-label")

                    ui.label(selected.title).classes("detail-title")

                    if selected.schedule_reason:
                        ui.label(selected.schedule_reason).classes(
                            "reason-pill warning"
                            if selected.status != "rejected"
                            else "reason-pill neutral"
                        )

                    if selected.description:
                        ui.label(selected.description).classes("detail-description")

                    deadline_str = (
                        selected.deadline.strftime("%d %b %Y, %H:%M")
                        if selected.deadline
                        else None
                    )
                    est_str = (
                        f"{selected.estimated_hours:g}h estimated"
                        if selected.estimated_hours
                        else None
                    )
                    for icon, value in (
                        ("schedule", selected.time_label),
                        ("flag", f"Deadline: {deadline_str}" if deadline_str else None),
                        ("hourglass_bottom", est_str),
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

                with ui.column().classes("w-full gap-2 mt-1"):
                    with ui.row().classes("gap-2 wrap w-full"):
                        ui.button(
                            "Edit / Complete info",
                            icon="edit",
                            on_click=lambda tid=selected.task_id: on_edit_task(tid),
                        ).props("outline dense no-caps")
                        if selected.status == "rejected":
                            ui.button(
                                "Restore to schedule",
                                icon="restore",
                                on_click=lambda tid=selected.task_id: on_restore_to_schedule(
                                    tid
                                ),
                            ).props("outline dense no-caps color=positive")
                        else:
                            ui.button(
                                "Remove from schedule",
                                icon="visibility_off",
                                on_click=lambda tid=selected.task_id: on_remove_from_schedule(
                                    tid
                                ),
                            ).props("outline dense no-caps")
                    ui.button(
                        "Delete task",
                        icon="delete_outline",
                        on_click=lambda tid=selected.task_id: on_delete_task(tid),
                    ).props("flat dense no-caps color=negative").classes("self-start")


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
