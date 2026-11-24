from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from client.core.models import ClientUser


def render_header(
    user: ClientUser,
    *,
    active: str,
    mode: str,
    on_sync: Callable,
    on_logout: Callable,
) -> None:
    with ui.header().classes("app-header"):
        with ui.row().classes("brand-block items-center gap-3"):
            with ui.element("div").classes("brand-mark"):
                ui.icon("calendar_month", size="22px")
            with ui.column().classes("gap-0"):
                ui.label("Smart Calendar").classes("brand-name")
                ui.label("FIT · HCMUS").classes("brand-kicker")

        with ui.row().classes("header-nav items-center gap-2"):
            ui.link("Calendar", "/calendar").classes(
                f"nav-link {'active' if active == 'calendar' else ''}"
            )
            ui.link("Settings", "/settings").classes(
                f"nav-link {'active' if active == 'settings' else ''}"
            )
            if mode == "mock":
                ui.badge("MOCK").props("outline").classes("mock-badge")
            ui.button(
                "Run personal crawl",
                icon="sync",
                on_click=on_sync,
            ).props(
                "flat no-caps"
            ).classes("sync-button")
            with ui.button(icon="person").props("round flat").classes("account-button"):
                with ui.menu().classes("account-menu"):
                    ui.label(user.username).classes("account-name")
                    ui.separator()
                    ui.menu_item("Calendar", on_click=lambda: ui.navigate.to("/calendar"))
                    ui.menu_item("Settings", on_click=lambda: ui.navigate.to("/settings"))
                    ui.separator()
                    ui.menu_item("Log out", on_click=on_logout)

