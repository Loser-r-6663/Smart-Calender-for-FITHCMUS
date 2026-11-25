from __future__ import annotations

from nicegui import app, ui

from client.components.header import render_header
from client.config import AppConfig
from client.core.backend import ClientBackend
from client.core.models import ClientUser
from client.core.source_preferences import SOURCE_GROUPS
from client.theme import apply_theme


def register_settings_page(backend: ClientBackend, config: AppConfig) -> None:
    @ui.page("/settings")
    async def settings_page() -> None:
        apply_theme()
        stored_user = app.storage.user.get("user")
        if not stored_user:
            ui.navigate.to("/login")
            return

        user = ClientUser(**stored_user)
        status = await backend.get_connection_status(user)
        disabled_sources = await backend.get_disabled_sources(user)
        ui.page_title("Settings · Smart Calendar")

        def last_updated_text() -> str:
            if status.last_sync is None:
                return "Not refreshed in this session"
            return f"Last updated {status.last_sync.astimezone():%d %b %Y, %H:%M}"

        def logout() -> None:
            app.storage.user.clear()
            ui.navigate.to("/login")

        async def sync() -> None:
            nonlocal status
            result = await backend.sync(user)
            status = await backend.get_connection_status(user)
            try:
                last_updated_label.set_text(last_updated_text())
                ui.notify(
                    result.message,
                    type="positive" if result.ok else "negative",
                    position="bottom-right",
                )
            except RuntimeError:
                pass

        render_header(
            user,
            active="settings",
            mode=config.mode,
            on_sync=sync,
            on_logout=logout,
        )

        with ui.dialog() as password_dialog, ui.card().classes("credential-dialog"):
            ui.label("Change password").classes("form-title credential-title")
            ui.label(
                "You will be signed out after your password is changed."
            ).classes("connection-copy credential-note")
            current_password = ui.input("Current password", password=True).props(
                "outlined password-toggle autocomplete=current-password"
            ).classes("w-full")
            new_password = ui.input("New password", password=True).props(
                "outlined password-toggle autocomplete=new-password"
            ).classes("w-full")
            confirm_password = ui.input("Confirm new password", password=True).props(
                "outlined password-toggle autocomplete=new-password"
            ).classes("w-full")
            password_message = ui.label().classes("login-error")
            password_message.visible = False

            async def submit_password_change() -> None:
                password_message.visible = False
                if not current_password.value:
                    password_message.text = "Enter your current password."
                    password_message.visible = True
                    return
                if len(new_password.value or "") < 8:
                    password_message.text = (
                        "New password must contain at least 8 characters."
                    )
                    password_message.visible = True
                    return
                if new_password.value != confirm_password.value:
                    password_message.text = "New passwords do not match."
                    password_message.visible = True
                    return

                save_password_button.props(add="loading disable")
                try:
                    result = await backend.change_password(
                        user,
                        current_password.value,
                        new_password.value,
                    )
                    if not result.ok:
                        password_message.text = result.message
                        password_message.visible = True
                        return
                    current_password.value = ""
                    new_password.value = ""
                    confirm_password.value = ""
                    password_dialog.close()
                    app.storage.user.clear()
                    ui.navigate.to("/login")
                finally:
                    save_password_button.props(remove="loading disable")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Cancel", on_click=password_dialog.close).props(
                    "flat no-caps"
                )
                save_password_button = ui.button(
                    "Change password", on_click=submit_password_change
                ).props("unelevated no-caps color=positive")
            confirm_password.on("keydown.enter", submit_password_change)

        with ui.dialog() as portal_dialog, ui.card().classes("credential-dialog"):
            ui.label("Connect Student Portal").classes("form-title credential-title")
            ui.label(
                "Credentials are stored encrypted. Open Portal in a tab to check "
                "your account. To connect the crawler, save the credentials and "
                "run a personal crawl; the tab's login session is not shared."
            ).classes("connection-copy credential-note")
            ui.link(
                "Open Student Portal in a new tab",
                "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fsinh-vien%2fket-qua-dkhp",
                new_tab=True,
            ).classes("source-link")
            portal_username = ui.input("Student ID").props(
                "outlined autocomplete=username"
            ).classes("w-full")
            portal_password = ui.input("Portal password", password=True).props(
                "outlined password-toggle autocomplete=current-password"
            ).classes("w-full")
            portal_message = ui.label().classes("login-error")
            portal_message.visible = False

            async def save_portal_credentials() -> None:
                nonlocal status
                portal_message.visible = False
                save_portal_button.props(add="loading disable")
                try:
                    result = await backend.save_portal_credentials(
                        user,
                        portal_username.value or "",
                        portal_password.value or "",
                    )
                    if not result.ok:
                        portal_message.text = result.message
                        portal_message.visible = True
                        return
                    status = await backend.get_connection_status(user)
                    portal_password.value = ""
                    portal_dialog.close()
                    connection_cards.refresh()
                    ui.notify(result.message, type="positive", position="bottom-right")
                finally:
                    save_portal_button.props(remove="loading disable")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Cancel", on_click=portal_dialog.close).props(
                    "flat no-caps"
                )
                save_portal_button = ui.button(
                    "Save credentials", on_click=save_portal_credentials
                ).props("unelevated no-caps color=positive")

        with ui.dialog() as moodle_dialog, ui.card().classes("credential-dialog"):
            ui.label("Connect Moodle").classes("form-title credential-title")
            ui.label(
                "You can open Moodle in a new tab, but its login session is not "
                "shared with the crawler. To connect Moodle for crawling, use "
                "Capture session below; a separate browser window will open. "
                "Complete Google sign-in there, not in this app."
            ).classes("connection-copy credential-note")
            ui.link(
                "Open Moodle in a new tab",
                "https://courses.ctda.hcmus.edu.vn/login/index.php",
                new_tab=True,
            ).classes("source-link")
            moodle_message = ui.label().classes("login-error")
            moodle_message.visible = False

            async def connect_moodle() -> None:
                nonlocal status
                moodle_message.visible = False
                connect_moodle_button.props(add="loading disable")
                ui.notify(
                    "Complete Moodle's Google sign-in in the separate browser window.",
                    type="info",
                    position="bottom-right",
                )
                try:
                    result = await backend.connect_moodle(user)
                    if not result.ok:
                        moodle_message.text = result.message
                        moodle_message.visible = True
                        return
                    status = await backend.get_connection_status(user)
                    moodle_dialog.close()
                    connection_cards.refresh()
                    ui.notify(result.message, type="positive", position="bottom-right")
                finally:
                    connect_moodle_button.props(remove="loading disable")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Cancel", on_click=moodle_dialog.close).props(
                    "flat no-caps"
                )
                connect_moodle_button = ui.button(
                    "Capture Moodle session", on_click=connect_moodle
                ).props("unelevated no-caps color=positive")

        @ui.refreshable
        def connection_cards() -> None:
            with ui.column().classes("connection-list gap-3 w-full"):
                for icon, name, connected, configured, copy, action in (
                    (
                        "account_balance",
                        "Student Portal",
                        status.portal,
                        status.portal_configured,
                        "Class timetable and registered courses",
                        portal_dialog.open,
                    ),
                    (
                        "school",
                        "Moodle",
                        status.moodle,
                        status.moodle_configured,
                        "Assignments and course deadlines via Google sign-in",
                        moodle_dialog.open,
                    ),
                ):
                    if connected:
                        status_text, status_class = "Connected", "status-connected"
                    elif configured:
                        status_text, status_class = (
                            "Credentials saved",
                            "status-configured",
                        )
                    else:
                        status_text, status_class = "Not configured", "status-neutral"

                    with ui.element("article").classes("connection-card"):
                        with ui.element("div").classes("connection-icon"):
                            ui.icon(icon, size="22px")
                        with ui.column().classes("gap-0 flex-grow"):
                            ui.label(name).classes("connection-name")
                            ui.label(copy).classes("connection-copy")
                        with ui.row().classes("connection-controls items-center gap-2"):
                            ui.badge(status_text).classes(status_class)
                            ui.button(
                                (
                                    "Update credentials"
                                    if name == "Student Portal" and configured
                                    else "Reconnect" if name == "Moodle" and configured
                                    else "Connect"
                                ),
                                on_click=action,
                            ).props("outline no-caps").classes("connection-action")

        with ui.element("main").classes("settings-main"):
            ui.label("Settings").classes("page-title")
            ui.label("Account and connected university services.").classes(
                "settings-subtitle"
            )

            with ui.element("section").classes("settings-section"):
                ui.label("Calendar account").classes("settings-section-title")
                with ui.element("article").classes("account-card"):
                    with ui.element("div").classes("connection-icon"):
                        ui.icon("person", size="22px")
                    with ui.column().classes("gap-0 flex-grow"):
                        ui.label(user.username).classes("connection-name")
                        ui.label(
                            "Supabase account email"
                            if config.mode == "live"
                            else "Smart Calendar username"
                        ).classes("connection-copy")
                    ui.button(
                        "Change password", on_click=password_dialog.open
                    ).props("outline no-caps").classes("connection-action")

            with ui.element("section").classes("settings-section"):
                ui.label("Connected accounts").classes("settings-section-title")
                connection_cards()

            with ui.element("section").classes("settings-section"):
                with ui.row().classes(
                    "source-section-heading items-end justify-between w-full"
                ):
                    with ui.column().classes("gap-0"):
                        ui.label("Information sources").classes(
                            "settings-section-title source-title"
                        )
                        ui.label(
                            "Choose which crawler sources appear in your calendar."
                        ).classes("connection-copy")
                    with ui.row().classes("source-actions gap-1"):
                        ui.button(
                            "Enable all",
                            on_click=lambda: toggle_all_sources(True),
                        ).props("flat no-caps").classes("source-action")
                        ui.button(
                            "Disable all",
                            on_click=lambda: toggle_all_sources(False),
                        ).props("flat no-caps").classes("source-action")

                async def update_source(source_name: str, enabled: bool) -> None:
                    try:
                        await backend.set_source_enabled(user, source_name, enabled)
                    except Exception:
                        ui.notify(
                            "Could not save this source preference.",
                            type="negative",
                            position="bottom-right",
                        )
                        source_list.refresh()
                        return
                    if enabled:
                        disabled_sources.discard(source_name)
                    else:
                        disabled_sources.add(source_name)

                def backend_source_status(source_name: str) -> tuple[str, str] | None:
                    connected = {
                        "Portal": status.portal,
                        "Moodle": status.moodle,
                    }.get(source_name)
                    if connected is None:
                        return None
                    return (
                        ("Connected", "source-status-connected")
                        if connected
                        else ("Needs attention", "source-status-warning")
                    )

                async def toggle_all_sources(enabled: bool) -> None:
                    try:
                        await backend.set_all_sources_enabled(user, enabled)
                    except Exception:
                        ui.notify(
                            "Could not save source preferences.",
                            type="negative",
                            position="bottom-right",
                        )
                        return
                    disabled_sources.clear()
                    if not enabled:
                        disabled_sources.update(
                            source.name
                            for _, sources in SOURCE_GROUPS
                            for source in sources
                        )
                    source_list.refresh()

                @ui.refreshable
                def source_list() -> None:
                    with ui.element("div").classes("source-groups"):
                        for group_name, sources in SOURCE_GROUPS:
                            with ui.element("div").classes("source-group"):
                                ui.label(group_name).classes("source-group-title")
                                for source in sources:
                                    with ui.element("article").classes("source-row"):
                                        with ui.column().classes("gap-0 flex-grow"):
                                            with ui.row().classes(
                                                "source-name-row items-center gap-1"
                                            ):
                                                ui.link(
                                                    source.name,
                                                    source.url,
                                                    new_tab=True,
                                                ).classes("source-name source-site-link")
                                                ui.icon(
                                                    "open_in_new", size="14px"
                                                ).classes("source-link-icon")
                                            ui.label(source.detail).classes("source-detail")
                                        source_health = backend_source_status(source.name)
                                        if source_health:
                                            ui.label(source_health[0]).classes(
                                                f"source-status {source_health[1]}"
                                            )
                                        ui.switch(
                                            value=source.name not in disabled_sources,
                                            on_change=lambda event, name=source.name: update_source(
                                                name, bool(event.value)
                                            ),
                                        ).props("color=positive")

                source_list()

            with ui.element("section").classes("settings-section"):
                ui.label("Data").classes("settings-section-title")
                with ui.element("article").classes("data-card"):
                    with ui.column().classes("gap-0"):
                        ui.label("Calendar data").classes("connection-name")
                        ui.label(
                            "Run your personal crawler and reload calendar data."
                            if config.mode == "live"
                            else "Simulate your personal crawler and reload calendar data."
                        ).classes("connection-copy")
                        last_updated_label = ui.label(last_updated_text()).classes(
                            "last-updated"
                        )
                    ui.button(
                        "Run personal crawl",
                        icon="sync",
                        on_click=sync,
                    ).props("unelevated no-caps color=positive").classes(
                        "refresh-button"
                    )

