from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from nicegui import app, ui

from client.components.agenda import render_agenda
from client.components.calendar import render_calendar
from client.components.filters import render_filters
from client.components.header import render_header
from client.components.task_panel import render_task_panel
from client.config import AppConfig
from client.core.backend import ClientBackend
from client.core.controller import ClientController
from client.core.models import ClientUser, TaskDraft
from client.theme import apply_theme


def _shift_month(month: date, offset: int) -> date:
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def register_calendar_page(backend: ClientBackend, config: AppConfig) -> None:
    @ui.page("/calendar")
    async def calendar_page() -> None:
        apply_theme()
        stored_user = app.storage.user.get("user")
        if not stored_user:
            ui.navigate.to("/login")
            return

        user = ClientUser(**stored_user)
        controller = ClientController(backend, user)
        await controller.load_month()
        ui.page_title("Calendar · Smart Calendar")

        def logout() -> None:
            app.storage.user.clear()
            ui.navigate.to("/login")

        async def sync() -> None:
            result = await backend.sync(user)
            await controller.load_month()
            body.refresh()
            ui.notify(
                result.message,
                type="positive" if result.ok else "negative",
                position="bottom-right",
            )

        def select_date(selected: date) -> None:
            controller.select_date(selected)
            body.refresh()

        def select_calendar_item(selected: date, item_id: str) -> None:
            controller.select_date(selected)
            controller.select_item(item_id)
            body.refresh()

        def select_item(item_id: str) -> None:
            controller.select_item(item_id)
            selected = controller.selected_item
            if selected and selected.day:
                controller.state.selected_date = selected.day
            body.refresh()

        def apply_filter(kind: str) -> None:
            controller.set_filter(kind)
            body.refresh()

        def set_view(view: str) -> None:
            controller.set_view(view)
            body.refresh()

        async def change_month(offset: int) -> None:
            month = _shift_month(controller.state.visible_month, offset)
            controller.state.selected_date = month
            await controller.load_month(month)
            body.refresh()

        async def go_today() -> None:
            today = date.today()
            controller.state.selected_date = today
            await controller.load_month(today.replace(day=1))
            body.refresh()

        render_header(
            user,
            active="calendar",
            mode=config.mode,
            on_sync=sync,
            on_logout=logout,
        )

        editing_task_id: str | None = None
        with ui.dialog() as create_task_dialog, ui.card().classes(
            "w-full max-w-2xl"
        ):
            task_form_title = ui.label("Create a task").classes("form-title")
            ui.label(
                "Date and time are optional. Tasks without a date appear in Agenda."
            ).classes("connection-copy")
            task_title = ui.input("Title *").props(
                "outlined maxlength=200"
            ).classes("w-full")
            task_kind = ui.select(
                {
                    "class": "Class",
                    "assignment": "Assignment",
                    "event": "Event",
                    "announcement": "Notice",
                },
                value="event",
                label="Type",
            ).props("outlined").classes("w-full")

            with ui.row().classes("w-full"):
                scheduled_date = ui.input("Date").props(
                    "type=date outlined"
                ).classes("flex-grow")
                start_clock = ui.input("Start time").props(
                    "type=time outlined"
                ).classes("flex-grow")
                end_clock = ui.input("End time").props(
                    "type=time outlined"
                ).classes("flex-grow")

            with ui.row().classes("w-full"):
                deadline_date = ui.input("Deadline date").props(
                    "type=date outlined"
                ).classes("flex-grow")
                deadline_clock = ui.input("Deadline time").props(
                    "type=time outlined"
                ).classes("flex-grow")

            task_course = ui.input("Course (optional)").props(
                "outlined"
            ).classes("w-full")
            task_location = ui.input("Location (optional)").props(
                "outlined"
            ).classes("w-full")
            task_description = ui.textarea("Description (optional)").props(
                "outlined autogrow"
            ).classes("w-full")
            task_source_url = ui.input("Source link (optional)").props(
                "outlined"
            ).classes("w-full")
            create_task_error = ui.label().classes("login-error")
            create_task_error.visible = False

            async def submit_task() -> None:
                nonlocal editing_task_id
                create_task_error.visible = False
                clean_title = (task_title.value or "").strip()
                if not clean_title:
                    create_task_error.text = "Enter a task title."
                    create_task_error.visible = True
                    return

                try:
                    scheduled_day = (
                        date.fromisoformat(scheduled_date.value)
                        if scheduled_date.value
                        else None
                    )
                    start_time = (
                        time.fromisoformat(start_clock.value)
                        if start_clock.value
                        else None
                    )
                    end_time = (
                        time.fromisoformat(end_clock.value)
                        if end_clock.value
                        else None
                    )
                    due_day = (
                        date.fromisoformat(deadline_date.value)
                        if deadline_date.value
                        else None
                    )
                    due_time = (
                        time.fromisoformat(deadline_clock.value)
                        if deadline_clock.value
                        else None
                    )
                except ValueError:
                    create_task_error.text = "Enter valid dates and times."
                    create_task_error.visible = True
                    return

                if (start_time or end_time) and scheduled_day is None:
                    create_task_error.text = "Choose a date for the start and end times."
                    create_task_error.visible = True
                    return
                if end_time and not start_time:
                    create_task_error.text = "Enter a start time before the end time."
                    create_task_error.visible = True
                    return
                if start_time and end_time and end_time <= start_time:
                    create_task_error.text = "End time must be after start time."
                    create_task_error.visible = True
                    return
                if due_time and due_day is None:
                    create_task_error.text = "Choose a date for the deadline time."
                    create_task_error.visible = True
                    return

                draft = TaskDraft(
                    title=clean_title,
                    kind=task_kind.value or "event",
                    scheduled_date=scheduled_day,
                    start_time=start_time,
                    end_time=end_time,
                    deadline=(
                        datetime.combine(
                            due_day,
                            due_time or time.min,
                            tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
                        )
                        if due_day
                        else None
                    ),
                    course=(task_course.value or "").strip() or None,
                    location=(task_location.value or "").strip() or None,
                    description=(task_description.value or "").strip() or None,
                    source_url=(task_source_url.value or "").strip() or None,
                )

                create_task_button.props(add="loading disable")
                try:
                    if editing_task_id:
                        result = await backend.update_task(
                            user,
                            editing_task_id,
                            draft,
                        )
                    else:
                        result = await backend.create_task(user, draft)
                    if not result.ok:
                        create_task_error.text = result.message
                        create_task_error.visible = True
                        return

                    editing_task_id = None
                    controller.set_filter("all")
                    controller.set_query("")
                    task_form_title.set_text("Create a task")
                    create_task_button.set_text("Create task")
                    task_title.value = ""
                    task_kind.value = "event"
                    scheduled_date.value = ""
                    start_clock.value = ""
                    end_clock.value = ""
                    deadline_date.value = ""
                    deadline_clock.value = ""
                    task_course.value = ""
                    task_location.value = ""
                    task_description.value = ""
                    task_source_url.value = ""
                    create_task_dialog.close()
                    target_day = scheduled_day or (
                        draft.deadline.date() if draft.deadline else None
                    )
                    if target_day:
                        controller.state.selected_date = target_day
                        await controller.load_month(target_day)
                    else:
                        controller.set_view("agenda")
                        await controller.load_month()
                    body.refresh()
                    ui.notify(result.message, type="positive", position="bottom-right")
                finally:
                    create_task_button.props(remove="loading disable")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Cancel", on_click=create_task_dialog.close).props(
                    "flat no-caps"
                )
                create_task_button = ui.button(
                    "Create task", on_click=submit_task
                ).props("unelevated no-caps color=positive")

        def open_create_task_dialog() -> None:
            nonlocal editing_task_id
            editing_task_id = None
            create_task_error.visible = False
            task_form_title.set_text("Create a task")
            create_task_button.set_text("Create task")
            task_title.value = ""
            task_kind.value = "event"
            scheduled_date.value = ""
            start_clock.value = ""
            end_clock.value = ""
            deadline_date.value = ""
            deadline_clock.value = ""
            task_course.value = ""
            task_location.value = ""
            task_description.value = ""
            task_source_url.value = ""
            create_task_dialog.open()

        def open_edit_task_dialog(task_id: str) -> None:
            nonlocal editing_task_id
            item = next(
                (
                    candidate
                    for candidate in controller.state.items
                    if candidate.task_id == task_id
                    and candidate.source == "Custom"
                    and candidate.is_personal
                ),
                None,
            )
            if item is None:
                ui.notify(
                    "Only your custom tasks can be edited.",
                    type="negative",
                    position="bottom-right",
                )
                return

            editing_task_id = task_id
            create_task_error.visible = False
            task_form_title.set_text("Edit task")
            create_task_button.set_text("Save changes")
            task_title.value = item.title
            task_kind.value = item.kind
            scheduled_date.value = item.start.date().isoformat() if item.start else ""
            start_clock.value = (
                item.start.strftime("%H:%M")
                if item.start and (item.start.time() != time.min or item.end)
                else ""
            )
            end_clock.value = item.end.strftime("%H:%M") if item.end else ""
            deadline_date.value = (
                item.deadline.date().isoformat() if item.deadline else ""
            )
            deadline_clock.value = (
                item.deadline.strftime("%H:%M")
                if item.deadline and item.deadline.time() != time.min
                else ""
            )
            task_course.value = item.course or ""
            task_location.value = item.location or ""
            task_description.value = item.description or ""
            task_source_url.value = item.source_url or ""
            create_task_dialog.open()

        pending_delete_task_id: str | None = None
        with ui.dialog() as delete_task_dialog, ui.card():
            ui.label("Delete task?").classes("form-title")
            delete_task_message = ui.label()
            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Cancel", on_click=delete_task_dialog.close).props(
                    "flat no-caps"
                )

                async def confirm_delete_task() -> None:
                    nonlocal pending_delete_task_id
                    if not pending_delete_task_id:
                        return
                    task_id = pending_delete_task_id
                    delete_task_button.props(add="loading disable")
                    try:
                        result = await backend.delete_task(user, task_id)
                        if not result.ok:
                            ui.notify(
                                result.message,
                                type="negative",
                                position="bottom-right",
                            )
                            return

                        delete_task_dialog.close()
                        pending_delete_task_id = None
                        controller.state.selected_item_id = None
                        await controller.load_month()
                        body.refresh()
                        ui.notify(
                            result.message,
                            type="positive",
                            position="bottom-right",
                        )
                    finally:
                        delete_task_button.props(remove="loading disable")

                delete_task_button = ui.button(
                    "Delete", on_click=confirm_delete_task
                ).props("unelevated no-caps color=negative")

        def open_delete_task_dialog(task_id: str) -> None:
            nonlocal pending_delete_task_id
            item = next(
                (
                    candidate
                    for candidate in controller.state.items
                    if candidate.task_id == task_id
                    and candidate.source == "Custom"
                    and candidate.is_personal
                ),
                None,
            )
            if item is None:
                ui.notify(
                    "Only your custom tasks can be deleted.",
                    type="negative",
                    position="bottom-right",
                )
                return
            pending_delete_task_id = task_id
            delete_task_message.set_text(
                f"“{item.title}” will be permanently deleted."
            )
            delete_task_dialog.open()

        @ui.refreshable
        def body() -> None:
            items = controller.filtered_items
            counts = {
                kind: len([item for item in items if item.kind == kind])
                for kind in ("class", "assignment", "event")
            }

            with ui.element("main").classes("app-main"):
                with ui.row().classes("summary-row items-end justify-between w-full"):
                    with ui.column().classes("gap-1"):
                        ui.label("My calendar").classes("page-eyebrow")
                        ui.label(controller.state.visible_month.strftime("%B %Y")).classes(
                            "page-title"
                        )
                    with ui.row().classes("summary-groups items-center"):
                        with ui.row().classes("summary-stats items-center"):
                            for value, label, kind in (
                                (counts["class"], "classes", "class"),
                                (counts["assignment"], "deadlines", "assignment"),
                                (counts["event"], "events", "event"),
                            ):
                                with ui.element("div").classes("summary-stat"):
                                    ui.element("span").classes(f"summary-dot kind-{kind}")
                                    ui.label(str(value)).classes("summary-number")
                                    ui.label(label).classes("summary-label")
                        with ui.element("div").classes("points-summary"):
                            ui.icon("workspace_premium", size="20px")
                            # Placeholder: these totals are computed from loaded
                            # events until the backend scheduler exposes its
                            # authoritative monthly and overall point estimates.
                            for value, label in (
                                (
                                    controller.training_points_this_month,
                                    "available this month",
                                ),
                                (controller.training_points_overall, "available overall"),
                            ):
                                with ui.element("div").classes("points-stat"):
                                    ui.label(f"{value} pts").classes("points-number")
                                    ui.label(label).classes("points-caption")

                with ui.element("section").classes("calendar-card"):
                    with ui.row().classes("calendar-toolbar items-center justify-between w-full"):
                        with ui.row().classes("month-controls items-center gap-1"):
                            ui.button(icon="chevron_left", on_click=lambda: change_month(-1)).props(
                                "round flat dense"
                            )
                            ui.label(
                                controller.state.visible_month.strftime("%B %Y")
                            ).classes("month-label")
                            ui.button(icon="chevron_right", on_click=lambda: change_month(1)).props(
                                "round flat dense"
                            )
                            ui.button("Today", on_click=go_today).props(
                                "flat no-caps"
                            ).classes("today-button")
                            ui.button(
                                "New task",
                                icon="add",
                                on_click=open_create_task_dialog,
                            ).props("unelevated no-caps color=positive")

                    render_filters(
                        controller.state,
                        controller.state.items,
                        on_filter=apply_filter,
                        on_view=set_view,
                        on_search_result=select_item,
                    )

                    if controller.state.error:
                        with ui.element("div").classes("error-banner"):
                            ui.icon("error_outline")
                            ui.label(controller.state.error)

                    with ui.element("div").classes("calendar-layout"):
                        with ui.element("div").classes("calendar-content"):
                            if controller.state.view == "calendar":
                                render_calendar(
                                    controller,
                                    on_select_date=select_date,
                                    on_select_item=select_calendar_item,
                                )
                            else:
                                render_agenda(controller, on_select_item=select_item)
                        render_task_panel(
                            controller,
                            on_select_item=select_item,
                            on_edit_task=open_edit_task_dialog,
                            on_delete_task=open_delete_task_dialog,
                        )

        body()

