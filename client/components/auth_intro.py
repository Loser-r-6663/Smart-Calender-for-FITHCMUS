from nicegui import ui


def render_auth_intro() -> None:
    """Shared left-hand introduction for sign-in and sign-up pages."""
    with ui.element("section").classes("login-intro"):
        with ui.element("div").classes("login-brand"):
            ui.icon("calendar_month", size="28px")
            ui.label("Smart Calendar")
        with ui.column().classes("login-features gap-4"):
            for icon, title, copy, kind in (
                (
                    "school",
                    "Class timetable",
                    "Recurring Portal classes at a glance.",
                    "class",
                ),
                (
                    "assignment",
                    "Upcoming work",
                    "Moodle deadlines beside your schedule.",
                    "assignment",
                ),
                (
                    "event",
                    "Training-point opportunities",
                    "Find campus events and see the points you can earn.",
                    "event",
                ),
            ):
                with ui.row().classes(
                    f"feature-row feature-{kind} items-start gap-3"
                ):
                    ui.icon(icon, size="20px")
                    with ui.column().classes("gap-0"):
                        ui.label(title).classes("feature-title")
                        ui.label(copy).classes("feature-copy")
