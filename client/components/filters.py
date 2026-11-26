from __future__ import annotations

from datetime import timedelta, timezone

from nicegui import background_tasks, ui

from academic_search import SearchFilterError, search_records

VN_TZ = timezone(timedelta(hours=7))
WEEKDAYS = dict(zip(("T2", "T3", "T4", "T5", "T6", "T7", "CN"),
                        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))


FILTERS = (
    ("all", "All"),
    ("class", "Classes"),
    ("assignment", "Assignments"),
    ("event", "Events"),
    ("personal", "Personal"),
    ("announcement", "Notices"),
)


class SearchPanel:
    """Retain control drafts while the calendar page refreshes."""

    def __init__(self, controller, *, on_select=None):
        self.controller = controller
        self.on_select = on_select
        self.query = controller.state.search_query
        self.submitted = False
        self.submitted_query = ""
        self.kind = "all"
        self.course = None
        self.deadline_start = ""
        self.deadline_end = ""
        self.sort = "auto"
        self._result_buttons = {}
        self._pending = False
        self._preliminary_result = None
        self._completed_mode = 'keyword'
        self._request_generation = 0
        self._requested_key = self._completed_key = None
        self._requested_snapshot = self._completed_result = self._completed_error = None

        self._snapshot = controller.state.search_snapshot
        with ui.menu().props('persistent no-parent-event no-refocus target=false anchor="bottom right" self="top right"').classes("task-search-popover") as self.menu:
            self.form()
        self.menu.on('show', lambda: self.query_input.run_method('focus'))
        self.menu.on('keydown.escape', self.close_menu, args=[], js_handler="""event => {
            const nested = [...document.querySelectorAll('.q-menu:not(.task-search-popover)')]
                .some(element => element.checkVisibility());
            if (!nested || !event.target.closest('.q-select')) { event.stopPropagation(); emit(); }
        }""")
        self.menu.on('hide', self.restore_focus)

    def render(self, *, on_filter, on_view) -> None:
        with ui.button(on_click=self.toggle_menu).props(
            f'outline no-caps aria-label="Search tasks" data-search-session="{self.controller.selection_session}"'
        ).classes("compact-search-trigger") as self.trigger:
            ui.icon("search")
            ui.label("Search tasks")
            ui.space()
            ui.icon("expand_more")
        self.menu.close()
        if self._snapshot is not self.controller.state.search_snapshot:
            self._snapshot = self.controller.state.search_snapshot
            self.form.refresh()

    def toggle_menu(self):
        if self.menu.value:
            self.menu.close()
        else:
            self.menu.props(f"target=#c{self.trigger.id}")
            self.menu.open()

    def close_menu(self):
        self.menu.close()

    async def restore_focus(self):
        await ui.run_javascript(f"document.getElementById('c{self.trigger.id}')?.focus({{preventScroll: true}})")

    @ui.refreshable
    def form(self):
        with ui.element("section").classes("loaded-search").props(
            f'data-search-session="{self.controller.selection_session}"'
        ):
            with ui.row().classes("search-query-row w-full"):
                self.query_input = ui.input("Search", placeholder="Search tasks...").bind_value(
                    self, "query"
                ).props("outlined dense").classes("search-query").on("keydown.enter", self.submit)
                ui.button("Search", icon="search", on_click=self.submit, color="positive").props("no-caps unelevated")
                ui.button("Clear", on_click=lambda: self.clear(lambda _: None), color="positive").props("flat no-caps")
                ui.button(icon="close", on_click=self.close_menu).props('flat round dense aria-label="Close Search"')
            courses = sorted({record.course for record in self.controller.state.search_snapshot.records
                              if record.course}, key=str.casefold)
            with ui.element("div").classes("search-controls"):
                ui.select(dict((key, "All types" if key == "all" else label) for key, label in FILTERS), label="Type", value=self.kind, on_change=lambda event: self.update("kind", event.value)).props('outlined dense aria-label="Type"')
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
            self._results_container = ui.column().classes("w-full")
            with self._results_container:
                self.results()

    def update(self, field, value) -> None:
        setattr(self, field, value)
        self._completed_key = None
        self.refresh_results()

    def clear(self, on_filter) -> None:
        self._discard_results()
        self.query = ""
        self.course = None
        self.deadline_start = ""
        self.deadline_end = ""
        self.sort = "auto"
        self.controller.state.selected_search_key = None
        self.submitted = False
        self.submitted_query = ""
        self.kind = "all"
        self.controller.search("")
        self._snapshot = self.controller.state.search_snapshot
        self.form.refresh()
        on_filter(self.controller.state.filters.kind)

    def submit(self) -> None:
        self.submitted_query = self.query
        self.submitted = True
        self._completed_key = None
        self.refresh_results()

    def _discard_results(self):
        self._request_generation += 1
        self._pending = False
        self._preliminary_result = None
        self._requested_key = self._completed_key = None
        self._requested_snapshot = self._completed_result = self._completed_error = None

    def _key(self):
        return (self.controller.selection_session, id(self.controller.state.search_snapshot),
                self.submitted_query, self.kind, self.course, self.deadline_start,
                self.deadline_end, self.sort)

    async def _compute(self, key, generation, filters):
        if generation != self._request_generation or key != self._key() or not self.submitted:
            return
        result, error = None, None
        try:
            result = await self.controller.search_async(
                key[2], filters=filters, sort=None if key[-1] == 'auto' else key[-1])
        except SearchFilterError as failure:
            error = str(failure)
        if (generation != self._request_generation or key != self._key() or not self.submitted
                or (result is None and error is None)):
            return
        self._pending = False
        self._preliminary_result = None
        self._completed_mode = 'hybrid' if self.controller.last_search_mode == 'hybrid' else 'fallback'
        self._completed_key = key
        self._completed_result, self._completed_error = result, error
        self.refresh_results()

    def select(self, key, session, opener) -> None:
        accepted = self.controller.select_search_record(key, session=session)
        if not accepted:
            self.refresh_results()
        for result_key, button in self._result_buttons.items():
            selected = result_key == self.controller.state.selected_search_key
            button.props(f'aria-pressed="{str(selected).lower()}" data-search-request="{self._request_generation}"')
            button.classes(add="selected" if selected else "", remove="" if selected else "selected")
        if self.on_select is not None:
            self.on_select(opener if accepted else None)

    def refresh_results(self):
        self._results_container.clear()
        with self._results_container:
            self.results()

    def results(self) -> None:
        self._result_buttons = {}
        state = self.controller.state
        if state.loading:
            self._discard_results()
            ui.label("Loading tasks…").props('role=status')
            return
        if state.session_expired:
            self._discard_results()
            ui.label("Session expired. Sign in again.").props('role=alert')
            return
        if state.error:
            self._discard_results()
            ui.label("Could not load tasks. Try refreshing.").props('role=alert')
            return
        if not self.submitted:
            self._discard_results()
            return
        filters = {}
        if self.kind != "all":
            filters["types"] = [self.kind]
        if self.course:
            filters["course"] = self.course
        if self.deadline_start:
            filters["deadline_start"] = self.deadline_start
        if self.deadline_end:
            filters["deadline_end"] = self.deadline_end
        key = self._key()
        if self._completed_key != key:
            if not self._pending or self._requested_key != key:
                try:
                    literal = search_records(state.search_snapshot.records, self.submitted_query,
                        filters=filters, sort=None if self.sort == 'auto' else self.sort)
                except SearchFilterError as error:
                    self._discard_results()
                    ui.label(str(error)).props('role=alert').classes('search-error')
                    return
                if not self.controller._hybrid_search.needs_semantic(literal):
                    self._completed_result, self._completed_error = literal, None
                    self._completed_mode, self._completed_key = 'keyword', key
                    self._pending = False
                    self.controller.search(self.submitted_query, filters=filters,
                                           sort=None if self.sort == 'auto' else self.sort)
                    self._render_result(literal)
                    return
                self._request_generation += 1
                self._pending = True
                self._preliminary_result = literal
                self._requested_key = key
                self._requested_snapshot = state.search_snapshot
                self._completed_result = self._completed_error = None
                background_tasks.create(self._compute(key, self._request_generation, filters))
            self._render_result(self._preliminary_result, preliminary=True)
            return
        if self._completed_error is not None:
            ui.label(self._completed_error).props('role=alert').classes('search-error')
            return
        self._render_result(self._completed_result)

    def _render_result(self, result, preliminary=False):
        state = self.controller.state
        if preliminary:
            ui.label('Searching…').classes('search-preliminary').props('role=status')
        else:
            if self._completed_mode == 'fallback':
                ui.label('Search could not complete. Showing available results.' if result.hits
                         else 'Search could not complete. Try again.').classes('search-error').props('role=alert')
                if not result.hits:
                    return
            ui.label(f"{len(result.hits)} tasks · {SORT_OPTIONS[result.sort]}").classes("search-count")
        if not result.hits:
            if not preliminary:
                ui.label('No matching tasks').props('role=status')
            return
        with ui.column().classes("search-results w-full"):
            for record in result.hits:
                selected = record.key == state.selected_search_key
                with ui.button(on_click=lambda event, key=record.key, session=self.controller.selection_session:
                               self.select(key, session, event.sender), color="positive").props(
                    f'flat no-caps align=left data-search-key="{record.scope}:{record.id}" '
                    f'aria-pressed="{str(selected).lower()}" data-search-request="{self._request_generation}"'
                ).classes(f"search-result {'selected' if selected else ''}") as button:
                    button.on('pointerdown.capture', js_handler="""event => {
                        const element = event.currentTarget;
                        element.__searchScroll = {
                            list: element.closest('.search-results')?.scrollTop || 0,
                            menu: element.closest('.task-search-popover')?.scrollTop || 0,
                            page: window.scrollY
                        };
                    }""")
                    button.on('keydown.capture', js_handler="""event => {
                        if (event.key !== 'Enter' && event.key !== ' ') return;
                        const element = event.currentTarget;
                        element.dataset.detailRestored = 'false';
                        element.__searchScroll = {
                            list: element.closest('.search-results')?.scrollTop || 0,
                            menu: element.closest('.task-search-popover')?.scrollTop || 0,
                            page: window.scrollY
                        };
                    }""")
                    button.on('click.capture', js_handler="""event => {
                        const element = event.currentTarget;
                        element.dataset.detailRestored = 'false';
                        if (!element.__searchScroll) element.__searchScroll = {
                            list: element.closest('.search-results')?.scrollTop || 0,
                            menu: element.closest('.task-search-popover')?.scrollTop || 0,
                            page: window.scrollY
                        };
                        const menu = element.closest('.task-search-popover');
                        menu.__detailAnchor = {key: element.dataset.searchKey,
                            request: element.dataset.searchRequest, scroll: element.__searchScroll};
                    }""")
                    self._result_buttons[record.key] = button
                    with ui.column().classes("gap-1 items-start"):
                        ui.label(record.title).classes("search-result-title")
                        with ui.row().classes('search-result-meta items-center gap-2'):
                            ui.label(TYPE_LABELS[record.type]).classes(f'type-badge solid-kind-{record.type}')
                            ui.label(record_date(record))
                        if record.training_points is not None and record.training_points > 0:
                            ui.label(f"{record.training_points} training point" + ("s" if record.training_points != 1 else "")).classes("search-result-points")


SORT_OPTIONS = {
    "auto": "Default",
    "best_match": "Best match",
    "soonest_deadline": "Soonest deadline",
    "latest_deadline": "Latest deadline",
    "title": "Title A–Z",
}


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

TYPE_LABELS = {"class":"Class", "assignment":"Assignment", "event":"Event", "announcement":"Notice", "personal":"Personal"}

def render_calendar_filters(controller, on_filter, on_view, search_panel, on_search_clear):
    with ui.row().classes("compact-calendar-toolbar w-full"):
        with ui.row().classes("filter-group"):
            for value, label in FILTERS:
                ui.button(label, on_click=lambda kind=value: on_filter(kind)).props("flat no-caps").classes("filter-button active" if controller.state.filters.kind == value else "filter-button")
        ui.space()
        search_panel.render(on_filter=on_search_clear, on_view=on_view)
        with ui.row().classes("view-switch"):
            for view, label in (("calendar", "Calendar"), ("schedule", "Schedule"), ("agenda", "Agenda")):
                ui.button(label, on_click=lambda value=view: on_view(value)).props("flat no-caps").classes("active" if controller.state.view == view else "")
