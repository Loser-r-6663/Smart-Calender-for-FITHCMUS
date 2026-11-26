from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from nicegui import app, ui

from client.components.agenda import render_agenda
from client.components.calendar import render_calendar
from client.components.filters import SearchPanel, render_calendar_filters
from client.components.search_details import SearchDetailsDialog
from client.components.header import render_header
from client.components.schedule_view import ARTICLE_LABELS, render_schedule_view
from client.components.task_panel import render_task_panel
from client.config import AppConfig
from client.core.backend import ClientBackend
from client.core.controller import ClientController
from client.core.models import ClientUser, TaskDraft
from client.theme import apply_theme


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

WEEKDAY_OPTIONS = {
    "T2": "Monday (T2)",
    "T3": "Tuesday (T3)",
    "T4": "Wednesday (T4)",
    "T5": "Thursday (T5)",
    "T6": "Friday (T6)",
    "T7": "Saturday (T7)",
    "CN": "Sunday (CN)",
}

CAMPUS_OPTIONS = {
    "": "Unspecified",
    "Nguyễn Văn Cừ (cơ sở 1)": "Nguyễn Văn Cừ (cơ sở 1)",
    "Thủ Đức (cơ sở 2)": "Thủ Đức (cơ sở 2)",
}

DRL_CATEGORY_OPTIONS = {
    "": "Select DRL category",
    "Articles 1": "Articles 1 · Học tập & NCKH (max 30)",
    "Articles 2": "Articles 2 · Nội quy & Kỷ luật (max 20)",
    "Articles 3": "Articles 3 · Đoàn - Hội, Văn thể mỹ (max 25)",
    "Articles 4": "Articles 4 · Tình nguyện, Cộng đồng (max 25)",
    "Articles 5": "Articles 5 · Khuyến khích (max 30)",
}

DRL_CAPS_BY_KEY = {
    "Articles 1": 30,
    "Articles 2": 20,
    "Articles 3": 25,
    "Articles 4": 25,
    "Articles 5": 30,
}


def _shift_month(month: date, offset: int) -> date:
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _safe_notify(message: str, *, positive: bool = True) -> None:
    try:
        ui.notify(
            message,
            type="positive" if positive else "negative",
            position="bottom-right",
        )
    except RuntimeError:
        pass


def _safe_refresh(refreshable_fn) -> None:
    try:
        refreshable_fn.refresh()
    except RuntimeError:
        pass


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
        refresh_body = None

        async def load_month(month=None) -> None:
            controller.state.loading = True
            if refresh_body is not None:
                refresh_body()
            await controller.load_month(month)
            if controller.state.session_expired:
                app.storage.user.clear()
                ui.navigate.to("/login")

        await load_month()
        if controller.state.session_expired:
            return
        ui.page_title("Calendar · Smart Calendar")

        async def _refresh_data_and_schedule() -> None:
            await load_month()
            if (
                controller.state.view == "schedule"
                or controller.state.schedule is not None
            ):
                await controller.load_schedule()
            _safe_refresh(body)

        def logout() -> None:
            controller.logout()
            app.storage.user.clear()
            ui.navigate.to("/login")

        async def sync() -> None:
            result = await backend.sync(user)
            await _refresh_data_and_schedule()
            _safe_notify(result.message, positive=result.ok)

        def select_date(selected: date) -> None:
            controller.select_date(selected)
            _safe_refresh(calendar_content)

        def select_calendar_item(selected: date, item_id: str) -> None:
            controller.select_date(selected)
            controller.select_item(item_id)
            _safe_refresh(calendar_content)

        def select_item(item_id: str) -> None:
            controller.select_item(item_id)
            selected = controller.selected_item
            if selected and selected.day:
                controller.state.selected_date = selected.day
            _safe_refresh(calendar_content)

        def apply_filter(kind: str) -> None:
            controller.set_filter(kind)
            _safe_refresh(body)

        async def set_view(view: str) -> None:
            controller.set_view(view)
            if view == "schedule" and controller.state.schedule is None:
                await controller.load_schedule()
            _safe_refresh(body)

        async def run_auto_schedule() -> None:
            controller.set_view("schedule")
            await controller.load_schedule()
            _safe_refresh(body)
            if controller.state.schedule is not None:
                n_sched = len(controller.state.schedule.scheduled_items)
                n_missing = len(controller.state.schedule.unschedulable)
                msg = f"Weekly schedule updated ({n_sched} blocks"
                if n_missing:
                    msg += f", {n_missing} need info"
                msg += ")."
                _safe_notify(msg, positive=True)

        async def shift_schedule_week(delta: int) -> None:
            new_offset = controller.state.schedule_week_offset + delta
            await controller.load_schedule(new_offset)
            if controller.state.schedule is not None:
                controller.state.selected_date = controller.state.schedule.week_start
            _safe_refresh(body)

        async def reset_schedule_this_week() -> None:
            await controller.load_schedule(0)
            controller.state.selected_date = date.today()
            _safe_refresh(body)

        def switch_schedule_tab(tab_key: str) -> None:
            controller.set_schedule_tab(tab_key)
            _safe_refresh(body)

        async def remove_task_from_schedule(task_id: str) -> None:
            result = await backend.set_task_schedule_state(
                user, task_id, status="rejected"
            )
            await _refresh_data_and_schedule()
            _safe_notify(result.message, positive=result.ok)

        async def restore_task_to_schedule(task_id: str) -> None:
            result = await backend.set_task_schedule_state(
                user, task_id, status="proposed"
            )
            await _refresh_data_and_schedule()
            _safe_notify(result.message, positive=result.ok)

        async def pin_task_to_schedule(task_id: str) -> None:
            result = await backend.set_task_schedule_state(
                user, task_id, status="proposed", compulsory=True
            )
            await _refresh_data_and_schedule()
            _safe_notify(result.message, positive=result.ok)

        async def change_month(offset: int) -> None:
            month = _shift_month(controller.state.visible_month, offset)
            controller.state.selected_date = month
            controller.show_month(month)
            _safe_refresh(body)

        async def go_today() -> None:
            today = date.today()
            controller.state.selected_date = today
            controller.show_month(today.replace(day=1))
            _safe_refresh(body)

        render_header(
            user,
            active="calendar",
            mode=config.mode,
            on_sync=sync,
            on_logout=logout,
        )

        # --- DRL Baseline Dialog ---
        drl_inputs: dict[str, ui.number] = {}
        with ui.dialog() as drl_dialog, ui.card().classes("w-full max-w-lg gap-3"):
            ui.label("Current Training Points (DRL)").classes("form-title")
            ui.label(
                "Enter your accumulated points per Article so the scheduler respects category caps (max 100 total)."
            ).classes("connection-copy")
            for cat_key, cat_label in ARTICLE_LABELS:
                cap = DRL_CAPS_BY_KEY[cat_key]
                drl_inputs[cat_key] = ui.number(
                    label=f"{cat_label} (0 – {cap})",
                    value=0,
                    min=0,
                    max=cap,
                    precision=0,
                ).props("outlined dense").classes("w-full")

            async def save_drl_baseline() -> None:
                payload = {
                    key: max(0, min(DRL_CAPS_BY_KEY[key], int(inp.value or 0)))
                    for key, inp in drl_inputs.items()
                }
                result = await backend.save_initial_drl(user, payload)
                drl_dialog.close()
                await controller.load_schedule()
                _safe_refresh(body)
                _safe_notify(result.message, positive=result.ok)

            with ui.row().classes("justify-end w-full gap-2 mt-2"):
                ui.button("Cancel", on_click=drl_dialog.close).props("flat no-caps")
                ui.button(
                    "Save & Re-optimize",
                    icon="auto_awesome",
                    on_click=save_drl_baseline,
                ).props("unelevated no-caps color=positive")

        async def open_drl_dialog() -> None:
            current_pts = await backend.get_initial_drl(user)
            for key, inp in drl_inputs.items():
                inp.value = current_pts.get(key, 0)
            drl_dialog.open()

        # --- Create / Edit / Complete Info Task Dialog ---
        editing_task_id: str | None = None
        with ui.dialog() as create_task_dialog, ui.card().classes(
            "w-full max-w-2xl gap-3"
        ):
            task_form_title = ui.label("Create a task").classes("form-title")
            missing_reason_banner = ui.element("div").classes("dialog-hint-banner")
            with missing_reason_banner:
                ui.icon("warning_amber", size="18px")
                missing_reason_label = ui.label()
            missing_reason_banner.visible = False

            ui.label(
                "Fill in scheduling fields (date/weekday, time, deadline, or estimated hours) to include this task in your weekly schedule."
            ).classes("connection-copy")

            task_title = ui.input("Title *").props(
                "outlined dense maxlength=200"
            ).classes("w-full")

            with ui.row().classes("w-full gap-3"):
                task_kind = ui.select(
                    {
                        "class": "Class",
                        "assignment": "Assignment",
                        "event": "Event (DRL)",
                        "personal": "Personal",
                        "announcement": "Notice",
                    },
                    value="event",
                    label="Type",
                ).props("outlined dense").classes("flex-1")
                task_course = ui.input("Course (optional)").props(
                    "outlined dense"
                ).classes("flex-1")

            with ui.row().classes("w-full items-center gap-4 wrap"):
                recurrence_check = ui.checkbox("Weekly recurring (by weekday)")
                flexible_check = ui.checkbox("Flexible time (auto-allocate slots)")
                compulsory_check = ui.checkbox("Pin to schedule (compulsory)")

            with ui.row().classes("w-full gap-2"):
                scheduled_date = ui.input("Date").props(
                    "type=date outlined dense"
                ).classes("flex-1")
                weekday_select = ui.select(
                    WEEKDAY_OPTIONS,
                    value="T2",
                    label="Weekday",
                ).props("outlined dense").classes("flex-1")
                weekday_select.visible = False
                start_clock = ui.input("Start time").props(
                    "type=time outlined dense"
                ).classes("flex-1")
                end_clock = ui.input("End time").props(
                    "type=time outlined dense"
                ).classes("flex-1")

            def _sync_recurrence_visibility() -> None:
                is_rec = bool(recurrence_check.value)
                weekday_select.visible = is_rec
                scheduled_date.visible = not is_rec

            recurrence_check.on_value_change(lambda _: _sync_recurrence_visibility())

            with ui.row().classes("w-full gap-2"):
                deadline_date = ui.input("Deadline date").props(
                    "type=date outlined dense"
                ).classes("flex-1")
                deadline_clock = ui.input("Deadline time").props(
                    "type=time outlined dense"
                ).classes("flex-1")
                estimated_hours_input = ui.number(
                    "Estimated hours",
                    min=0.5,
                    max=100,
                    step=0.5,
                    precision=1,
                ).props("outlined dense clearable").classes("flex-1")

            drl_row = ui.row().classes("w-full gap-2")
            with drl_row:
                training_points_input = ui.number(
                    "Training points (0–24)",
                    min=0,
                    max=24,
                    step=1,
                    precision=0,
                ).props("outlined dense clearable").classes("flex-1")
                drl_category_select = ui.select(
                    DRL_CATEGORY_OPTIONS,
                    value="",
                    label="DRL Category",
                ).props("outlined dense").classes("flex-2")

            def _on_kind_change() -> None:
                kind_val = task_kind.value
                drl_row.visible = kind_val == "event"
                if editing_task_id is None:
                    if kind_val == "assignment":
                        flexible_check.value = True
                        compulsory_check.value = True
                    elif kind_val in {"class", "personal"}:
                        flexible_check.value = False
                        compulsory_check.value = True

            task_kind.on_value_change(lambda _: _on_kind_change())

            with ui.row().classes("w-full gap-2"):
                task_location = ui.input("Room / Online (optional)").props(
                    "outlined dense"
                ).classes("flex-1")
                campus_select = ui.select(
                    CAMPUS_OPTIONS,
                    value="",
                    label="Campus (optional)",
                ).props("outlined dense").classes("flex-1")

            task_description = ui.textarea("Description (optional)").props(
                "outlined dense autogrow"
            ).classes("w-full")
            task_source_url = ui.input("Source link (optional)").props(
                "outlined dense"
            ).classes("w-full")
            create_task_error = ui.label().classes("login-error")
            create_task_error.visible = False

            def _reset_task_form() -> None:
                create_task_error.visible = False
                missing_reason_banner.visible = False
                task_title.value = ""
                task_kind.value = "event"
                recurrence_check.value = False
                flexible_check.value = False
                compulsory_check.value = False
                scheduled_date.value = ""
                weekday_select.value = "T2"
                start_clock.value = ""
                end_clock.value = ""
                deadline_date.value = ""
                deadline_clock.value = ""
                estimated_hours_input.value = None
                training_points_input.value = None
                drl_category_select.value = ""
                task_course.value = ""
                task_location.value = ""
                campus_select.value = ""
                task_description.value = ""
                task_source_url.value = ""
                _sync_recurrence_visibility()
                _on_kind_change()

            async def submit_task() -> None:
                nonlocal editing_task_id
                create_task_error.visible = False
                clean_title = (task_title.value or "").strip()
                if not clean_title:
                    create_task_error.text = "Enter a task title."
                    create_task_error.visible = True
                    return

                is_rec = bool(recurrence_check.value)
                try:
                    scheduled_day = (
                        date.fromisoformat(scheduled_date.value)
                        if (not is_rec and scheduled_date.value)
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

                if not is_rec and (start_time or end_time) and scheduled_day is None:
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

                est_hours: float | None = None
                if estimated_hours_input.value is not None and estimated_hours_input.value != "":
                    est_hours = float(estimated_hours_input.value)
                    if est_hours <= 0:
                        create_task_error.text = "Estimated hours must be greater than 0."
                        create_task_error.visible = True
                        return

                pts: int | None = None
                if (
                    task_kind.value == "event"
                    and training_points_input.value is not None
                    and training_points_input.value != ""
                ):
                    pts = int(training_points_input.value)
                    if not (0 <= pts <= 24):
                        create_task_error.text = "Training points must be between 0 and 24."
                        create_task_error.visible = True
                        return

                drl_cat = (drl_category_select.value or "").strip() or None
                if pts and pts > 0 and not drl_cat:
                    create_task_error.text = "Select a DRL category (Articles 1–5) when training points > 0."
                    create_task_error.visible = True
                    return

                campus_val = (campus_select.value or "").strip() or None

                draft = TaskDraft(
                    title=clean_title,
                    kind=task_kind.value or "event",
                    scheduled_date=scheduled_day,
                    weekday=weekday_select.value if is_rec else None,
                    start_time=start_time,
                    end_time=end_time,
                    deadline=(
                        datetime.combine(
                            due_day,
                            due_time or time.min,
                            tzinfo=VN_TZ,
                        )
                        if due_day
                        else None
                    ),
                    course=(task_course.value or "").strip() or None,
                    location=(task_location.value or "").strip() or None,
                    campus=campus_val,  # type: ignore[arg-type]
                    description=(task_description.value or "").strip() or None,
                    source_url=(task_source_url.value or "").strip() or None,
                    estimated_hours=est_hours,
                    training_points=pts,
                    training_point_category=drl_cat,  # type: ignore[arg-type]
                    recurrence=is_rec,
                    flexible=bool(flexible_check.value),
                    compulsory=bool(compulsory_check.value),
                )

                create_task_button.props(add="loading disable")
                try:
                    was_editing = editing_task_id is not None
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
                    _reset_task_form()
                    create_task_dialog.close()

                    if controller.state.view == "schedule":
                        await _refresh_data_and_schedule()
                    else:
                        target_day = scheduled_day or (
                            draft.deadline.date() if draft.deadline else None
                        )
                        if target_day:
                            controller.state.selected_date = target_day
                            await controller.load_month(target_day)
                        elif not is_rec and not was_editing:
                            controller.set_view("agenda")
                            await controller.load_month()
                        else:
                            await controller.load_month()
                        if controller.state.schedule is not None:
                            await controller.load_schedule()
                        _safe_refresh(body)
                    _safe_notify(result.message, positive=True)
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
            _reset_task_form()
            task_form_title.set_text("Create a task")
            create_task_button.set_text("Create task")
            create_task_dialog.open()

        def open_edit_task_dialog(task_id: str) -> None:
            nonlocal editing_task_id
            item = controller.find_item_by_task_id(task_id)
            if item is None:
                _safe_notify("Task could not be found.", positive=False)
                return

            editing_task_id = task_id
            create_task_error.visible = False
            task_form_title.set_text("Edit / Complete task info")
            create_task_button.set_text("Save changes")

            if item.schedule_reason and item.status != "rejected":
                missing_reason_label.set_text(item.schedule_reason)
                missing_reason_banner.visible = True
            else:
                missing_reason_banner.visible = False

            task_title.value = item.title
            task_kind.value = item.kind if item.kind in {"class", "assignment", "event", "personal", "announcement"} else "event"
            drl_row.visible = task_kind.value == "event"

            recurrence_check.value = bool(item.recurrence and item.weekday)
            _sync_recurrence_visibility()
            weekday_select.value = item.weekday or "T2"
            flexible_check.value = bool(item.flexible)
            compulsory_check.value = bool(item.compulsory)

            scheduled_date.value = (
                item.start.date().isoformat()
                if (item.start and not recurrence_check.value)
                else ""
            )
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
            estimated_hours_input.value = item.estimated_hours
            training_points_input.value = item.points
            drl_category_select.value = item.training_point_category or ""
            task_course.value = item.course or ""
            task_location.value = item.room or item.location or ""
            campus_select.value = item.campus or ""
            task_description.value = item.description or ""
            task_source_url.value = item.source_url or ""
            create_task_dialog.open()

        # --- Delete Task Dialog (Permanent Delete) ---
        pending_delete_task_id: str | None = None
        with ui.dialog() as delete_task_dialog, ui.card().classes("max-w-md gap-3"):
            ui.label("Delete task permanently?").classes("form-title")
            delete_task_message = ui.label().classes("connection-copy")
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
                            _safe_notify(result.message, positive=False)
                            return

                        delete_task_dialog.close()
                        pending_delete_task_id = None
                        controller.state.selected_item_id = None
                        await _refresh_data_and_schedule()
                        _safe_notify(result.message, positive=True)
                    finally:
                        delete_task_button.props(remove="loading disable")

                delete_task_button = ui.button(
                    "Delete permanently", on_click=confirm_delete_task
                ).props("unelevated no-caps color=negative")

        def open_delete_task_dialog(task_id: str) -> None:
            nonlocal pending_delete_task_id
            item = controller.find_item_by_task_id(task_id)
            if item is None:
                _safe_notify("Task could not be found.", positive=False)
                return
            pending_delete_task_id = task_id
            delete_task_message.set_text(
                f"“{item.title}” will be permanently deleted. "
                "(Tip: use 'Remove from schedule' if you only want to hide it from your timetable.)"
            )
            delete_task_dialog.open()

        search_details = SearchDetailsDialog(controller)

        @ui.refreshable
        def task_panel() -> None:
            render_task_panel(
                controller, on_select_item=select_item,
                on_edit_task=open_edit_task_dialog,
                on_remove_from_schedule=remove_task_from_schedule,
                on_restore_to_schedule=restore_task_to_schedule,
                on_delete_task=open_delete_task_dialog,
            )

        def open_search_details(opener) -> None:
            task_panel.refresh()
            search_details.open(opener)

        search_panel = SearchPanel(controller, on_select=open_search_details)

        @ui.refreshable
        def calendar_content():
            with ui.element("div").classes("calendar-layout"):
                with ui.element("div").classes("calendar-content"):
                    if controller.state.view == "calendar":
                        render_calendar(
                            controller,
                            on_select_date=select_date,
                            on_select_item=select_calendar_item,
                        )
                    elif controller.state.view == "schedule":
                        render_schedule_view(
                            controller,
                            on_run_schedule=run_auto_schedule,
                            on_shift_week=shift_schedule_week,
                            on_this_week=reset_schedule_this_week,
                            on_open_drl_dialog=open_drl_dialog,
                            on_select_item=select_item,
                            on_edit_task=open_edit_task_dialog,
                            on_remove_from_schedule=remove_task_from_schedule,
                            on_restore_to_schedule=restore_task_to_schedule,
                            on_pin_to_schedule=pin_task_to_schedule,
                            on_delete_task=open_delete_task_dialog,
                            on_switch_tab=switch_schedule_tab,
                        )
                    else:
                        render_agenda(controller, on_select_item=select_item)
                task_panel()

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
                        ui.label(
                            "Weekly schedule"
                            if controller.state.view == "schedule"
                            else "My calendar"
                        ).classes("page-eyebrow")
                        ui.label(
                            controller.state.visible_month.strftime("%B %Y")
                        ).classes("page-title")
                    with ui.row().classes("summary-groups items-center"):
                        with ui.row().classes("summary-stats items-center"):
                            for value, label, kind in (
                                (counts["class"], "classes", "class"),
                                (counts["assignment"], "deadlines", "assignment"),
                                (counts["event"], "events", "event"),
                            ):
                                with ui.element("div").classes("summary-stat"):
                                    ui.element("span").classes(
                                        f"summary-dot kind-{kind}"
                                    )
                                    ui.label(str(value)).classes("summary-number")
                                    ui.label(label).classes("summary-label")
                        with ui.element("div").classes("points-summary"):
                            ui.icon("workspace_premium", size="20px")
                            if controller.scheduled_drl_total is not None:
                                point_pairs = (
                                    (
                                        f"{controller.scheduled_drl_total}/100",
                                        "projected DRL",
                                    ),
                                    (
                                        f"+{controller.scheduled_drl_gain or 0} pts",
                                        "gained this week",
                                    ),
                                )
                            else:
                                point_pairs = (
                                    (
                                        f"{controller.training_points_this_month} pts",
                                        "available this month",
                                    ),
                                    (
                                        f"{controller.training_points_overall} pts",
                                        "available overall",
                                    ),
                                )
                            for value_str, label in point_pairs:
                                with ui.element("div").classes("points-stat"):
                                    ui.label(value_str).classes("points-number")
                                    ui.label(label).classes("points-caption")

                with ui.element("section").classes("calendar-card"):
                    with ui.row().classes(
                        "calendar-toolbar items-center justify-between w-full wrap gap-2"
                    ):
                        with ui.row().classes("month-controls items-center gap-1"):
                            ui.button(
                                icon="chevron_left",
                                on_click=lambda: change_month(-1),
                            ).props("round flat dense")
                            ui.label(
                                controller.state.visible_month.strftime("%B %Y")
                            ).classes("month-label")
                            ui.button(
                                icon="chevron_right",
                                on_click=lambda: change_month(1),
                            ).props("round flat dense")
                            ui.button("Today", on_click=go_today).props(
                                "flat no-caps"
                            ).classes("today-button")

                        with ui.row().classes("items-center gap-2"):
                            ui.button(
                                "Auto-schedule",
                                icon="auto_awesome",
                                on_click=run_auto_schedule,
                            ).props("outline no-caps color=primary")
                            ui.button(
                                "New task",
                                icon="add",
                                on_click=open_create_task_dialog,
                            ).props("unelevated no-caps color=positive")

                    render_calendar_filters(controller, apply_filter, set_view, search_panel, lambda _: _safe_refresh(body))

                    if controller.state.error:
                        with ui.element("div").classes("error-banner"):
                            ui.icon("error_outline")
                            ui.label(controller.state.error)

                    calendar_content()

        refresh_body = body.refresh
        body()
        selection_session = controller.selection_session

        def invalidate_session_ui():
            nonlocal selection_session
            if controller.selection_session != selection_session:
                selection_session = controller.selection_session
                search_panel.clear(lambda _: body.refresh())

        ui.timer(0.1, invalidate_session_ui)
