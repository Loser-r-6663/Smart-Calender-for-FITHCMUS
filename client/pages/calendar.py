from __future__ import annotations

from datetime import date

from nicegui import app, ui

from client.components.agenda import render_agenda
from client.components.calendar import render_calendar
from client.components.filters import SearchPanel
from client.components.header import render_header
from client.components.task_panel import render_task_panel
from client.config import AppConfig
from client.core.backend import ClientBackend
from client.core.controller import ClientController
from client.core.models import ClientUser
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

        def logout() -> None:
            controller.logout()
            app.storage.user.clear()
            ui.navigate.to("/login")

        async def sync() -> None:
            result = await backend.sync(user)
            await load_month()
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
            await load_month(month)
            body.refresh()

        async def go_today() -> None:
            today = date.today()
            controller.state.selected_date = today
            await load_month(today.replace(day=1))
            body.refresh()

        search_panel = SearchPanel(controller)

        render_header(
            user,
            active="calendar",
            mode=config.mode,
            on_sync=sync,
            on_logout=logout,
        )

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

                    search_panel.render(on_filter=apply_filter, on_view=set_view)

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
                        render_task_panel(controller, on_select_item=select_item)

        refresh_body = body.refresh
        body()
