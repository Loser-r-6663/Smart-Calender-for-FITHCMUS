from __future__ import annotations

from collections.abc import Callable

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
            ):
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
