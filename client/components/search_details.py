from __future__ import annotations

import json

from nicegui import ui

from client.components.task_panel import render_record_details


class SearchDetailsDialog:
    """Present only the current session's selected snapshot record."""

    def __init__(self, controller):
        self.controller = controller
        self._session = None
        self._opener = None
        self._opener_key = None
        self._rendered = None
        with ui.dialog().props('no-refocus') as self.dialog:
            with ui.card().classes('search-detail-dialog'):
                ui.label('Task details').classes('text-h6').props('role=heading aria-level=2')
                self.content = ui.column().classes('search-detail-content w-full')
                ui.button('Close', on_click=self.dialog.close, color='positive').props('flat no-caps')
        self.dialog.on('hide', self._closed)
        ui.timer(0.1, self.sync)

    def open(self, opener) -> None:
        if opener is None or self.controller.selected_search_record is None:
            self.dismiss()
            return
        self._session = self.controller.selection_session
        self._opener = f'c{opener.id}'
        self._opener_key = ':'.join(self.controller.state.selected_search_key)
        self._rendered = None
        self.dialog.open()
        self.sync()

    def dismiss(self) -> None:
        self._opener = None
        self.content.clear()
        self.dialog.close()
        self._rendered = None

    def sync(self) -> None:
        if not self.dialog.value:
            return
        state = self.controller.state
        if (self._session != self.controller.selection_session or state.user is None
                or state.session_expired or state.error):
            self.dismiss()
            return
        record = self.controller.selected_search_record
        if not state.loading and record is None:
            self.dismiss()
            return
        current = (state.loading, record)
        if current == self._rendered:
            return
        self._rendered = current
        self.content.clear()
        with self.content:
            if state.loading:
                ui.label('Refreshing task details…').props('role=status')
            else:
                render_record_details(record)

    async def _closed(self) -> None:
        if self.dialog.value:
            return
        opener, self._opener = self._opener, None
        self.content.clear()
        self._rendered = None
        if opener is None or self._session != self.controller.selection_session:
            return
        await ui.run_javascript(f'''
            const key = {json.dumps(self._opener_key)};
            const element = document.getElementById({json.dumps(opener)}) ||
                [...document.querySelectorAll('.search-result')].find(e => e.dataset.searchKey === key);
            if (element && element.checkVisibility()) {{
                const menu = element.closest('.task-search-popover');
                const anchor = menu?.__detailAnchor;
                const saved = element.__searchScroll || (anchor?.key === key &&
                    anchor.request === element.dataset.searchRequest ? anchor.scroll : null);
                if (saved) {{
                    element.closest('.search-results').scrollTop = saved.list;
                    menu.scrollTop = saved.menu;
                }}
                const bounds = element.getBoundingClientRect();
                const list = element.closest('.search-results')?.getBoundingClientRect();
                if (list && bounds.bottom > Math.max(0, list.top)
                    && bounds.top < Math.min(innerHeight, list.bottom)) {{
                    if (saved) {{
                        const restore = () => {{
                            element.closest('.search-results').scrollTop = saved.list;
                            element.closest('.task-search-popover').scrollTop = saved.menu;
                            window.scrollTo({{top: saved.page, behavior: 'instant'}});
                        }};
                        restore();
                        await new Promise(requestAnimationFrame);
                        restore();
                    }}
                    element.focus({{preventScroll: true}});
                    delete element.__searchScroll;
                    element.dataset.detailRestored = 'true';
                }}
            }}
        ''')
