from __future__ import annotations

from datetime import timedelta, timezone

from nicegui import ui

from academic_search import SearchFilterError

VN_TZ = timezone(timedelta(hours=7))
WEEKDAYS = dict(zip(("T2", "T3", "T4", "T5", "T6", "T7", "CN"),
                        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))


FILTERS = (
    ("all", "All"),
    ("class", "Classes"),
    ("assignment", "Assignments"),
    ("event", "Events"),
    ("announcement", "Notices"),
)


class SearchPanel:
    """Retain control drafts while the calendar page refreshes."""

    def __init__(self, controller, *, on_select=None):
        self.controller = controller
        self.on_select = on_select
        self.query = controller.state.filters.query
        self.course = None
        self.deadline_start = ""
        self.deadline_end = ""
        self.sort = "auto"
        self._result_buttons = {}

    def render(self, *, on_filter, on_view) -> None:
        with ui.element("section").classes("loaded-search"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label("Search loaded tasks").classes("search-heading")
                with ui.row().classes("view-switch"):
                    for view, label in (("calendar", "Calendar"), ("agenda", "Agenda")):
                        ui.button(label, on_click=lambda value=view: on_view(value)).props("flat no-caps").classes(
                            "active" if self.controller.state.view == view else ""
                        )
            with ui.row().classes("filter-group items-center gap-1"):
                for value, label in FILTERS:
                    ui.button(label, on_click=lambda kind=value: on_filter(kind)).props("flat no-caps").classes(
                        f"filter-button {'active' if self.controller.state.filters.kind == value else ''}"
                    )
            with ui.row().classes("search-query-row w-full"):
                ui.input("Query", placeholder="Title, course or Vietnamese keywords").bind_value(
                    self, "query"
                ).props("outlined dense").classes("search-query").on("keydown.enter", self.submit)
                ui.button("Search", icon="search", on_click=self.submit, color="positive").props("no-caps unelevated")
                ui.button("Clear", on_click=lambda: self.clear(on_filter), color="positive").props("flat no-caps")
            courses = sorted({record.course for record in self.controller.state.search_snapshot.records
                              if record.course}, key=str.casefold)
            with ui.element("div").classes("search-controls"):
                ui.select(courses, label="Course", clearable=True, value=self.course,
                          on_change=lambda event: self.update("course", event.value)).props(
                    'outlined dense aria-label="Course"'
                )
                ui.input("Deadline from", value=self.deadline_start,
                         on_change=lambda event: self.update("deadline_start", event.value)).props(
                    'outlined dense type=date'
                )
                ui.input("Deadline through", value=self.deadline_end,
                         on_change=lambda event: self.update("deadline_end", event.value)).props(
                    'outlined dense type=date'
                )
                ui.select(SORT_OPTIONS, label="Sort", value=self.sort,
                          on_change=lambda event: self.update("sort", event.value)).props(
                    'outlined dense aria-label="Sort"'
                )
            self.results()

    def update(self, field, value) -> None:
        setattr(self, field, value)
        self.submit()

    def clear(self, on_filter) -> None:
        self.query = ""
        self.course = None
        self.deadline_start = ""
        self.deadline_end = ""
        self.sort = "auto"
        self.controller.state.selected_search_key = None
        self.controller.search("")
        on_filter("all")

    def submit(self) -> None:
        self.results.refresh()

    def select(self, key, session, opener) -> None:
        accepted = self.controller.select_search_record(key, session=session)
        if not accepted:
            self.results.refresh()
        for result_key, button in self._result_buttons.items():
            selected = result_key == self.controller.state.selected_search_key
            button.props(f'aria-pressed="{str(selected).lower()}"')
            button.classes(add="selected" if selected else "", remove="" if selected else "selected")
        if self.on_select is not None:
            self.on_select(opener if accepted else None)

    @ui.refreshable
    def results(self) -> None:
        self._result_buttons = {}
        state = self.controller.state
        if state.loading:
            ui.label("Loading tasks…").props('role=status')
            return
        if state.session_expired:
            ui.label("Session expired. Sign in again.").props('role=alert')
            return
        if state.error:
            ui.label("Could not load tasks. Try refreshing.").props('role=alert')
            return
        filters = {}
        if self.course:
            filters["course"] = self.course
        if self.deadline_start:
            filters["deadline_start"] = self.deadline_start
        if self.deadline_end:
            filters["deadline_end"] = self.deadline_end
        try:
            result = self.controller.search(
                self.query, filters=filters, sort=None if self.sort == "auto" else self.sort,
            )
        except SearchFilterError as error:
            ui.label(str(error)).props('role=alert').classes("search-error")
            return
        points = point_label(result.effective_filters)
        if points:
            ui.label(points).classes("search-points").props('role=status')
        ui.label(f"{len(result.hits)} tasks · {SORT_OPTIONS[result.sort]}").classes("search-count")
        if not result.hits:
            ui.label("No matching tasks").props('role=status')
            return
        with ui.column().classes("search-results w-full"):
            for record in result.hits:
                selected = record.key == state.selected_search_key
                with ui.button(on_click=lambda event, key=record.key, session=self.controller.selection_session:
                               self.select(key, session, event.sender), color="positive").props(
                    f'flat no-caps align=left data-search-key="{record.scope}:{record.id}" '
                    f'aria-pressed="{str(selected).lower()}"'
                ).classes(f"search-result {'selected' if selected else ''}") as button:
                    self._result_buttons[record.key] = button
                    with ui.column().classes("gap-1 items-start"):
                        ui.label(record.title).classes("search-result-title")
                        ui.label(f"{record.scope.title()} · {record_date(record)}").classes("search-result-meta")


SORT_OPTIONS = {
    "auto": "Default",
    "best_match": "Best match",
    "soonest_deadline": "Soonest deadline",
    "latest_deadline": "Latest deadline",
    "title": "Title A–Z",
}


def point_label(filters):
    minimum, maximum = filters.get("min_training_points"), filters.get("max_training_points")
    if minimum is not None and minimum == maximum:
        return f"Exactly {minimum} points"
    if minimum is not None and maximum is not None:
        return f"{minimum}–{maximum} points"
    if minimum is not None:
        return f"At least {minimum} points"
    if maximum is not None:
        return f"At most {maximum} points"
    return ""


def record_date(record):
    if record.deadline is not None:
        return "Due " + record.deadline.astimezone(VN_TZ).strftime("%d %b %Y, %H:%M")
    for label, value in (("Starts", record.start_time), ("Ends", record.end_time)):
        if value is not None and value.date is not None:
            clock = value.time.strftime(", %H:%M") if value.time is not None else ""
            return label + " " + value.date.strftime("%d %b %Y") + clock
    for value in (record.start_time, record.end_time):
        if value is not None and value.day:
            day = WEEKDAYS[value.day]
            clock = value.time.strftime(", %H:%M") if value.time is not None else ""
            return f"Date not provided · Every {day}{clock}"
    return "Date not provided"
