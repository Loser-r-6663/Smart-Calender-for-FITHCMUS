from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from nicegui import ui

from client.core.controller import ClientController
from client.core.models import CalendarItem, ScheduleProposal


ARTICLE_LABELS = (
    ("Articles 1", "Điều 1 · Học tập"),
    ("Articles 2", "Điều 2 · Nội quy"),
    ("Articles 3", "Điều 3 · Đoàn - Hội"),
    ("Articles 4", "Điều 4 · Tình nguyện"),
    ("Articles 5", "Điều 5 · Khuyến khích"),
)

VN_DAY_SHORT = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


def render_schedule_view(
    controller: ClientController,
    *,
    on_run_schedule: Callable[[], Any],
    on_shift_week: Callable[[int], Any],
    on_this_week: Callable[[], Any],
    on_open_drl_dialog: Callable[[], Any],
    on_select_item: Callable[[str], Any],
    on_edit_task: Callable[[str], Any],
    on_remove_from_schedule: Callable[[str], Any],
    on_restore_to_schedule: Callable[[str], Any],
    on_pin_to_schedule: Callable[[str], Any],
    on_delete_task: Callable[[str], Any],
    on_switch_tab: Callable[[str], Any],
) -> None:
    sched = controller.state.schedule
    selected = controller.selected_item

    with ui.column().classes("schedule-workspace w-full gap-0"):
        if sched is None:
            with ui.column().classes("empty-state items-center gap-3 w-full"):
                ui.icon("auto_awesome", size="36px")
                ui.label("No weekly schedule generated yet").classes("empty-title")
                ui.button(
                    "Generate weekly schedule",
                    icon="auto_awesome",
                    on_click=on_run_schedule,
                ).props("unelevated no-caps color=positive")
            return

        week_label = (
            f"{sched.week_start:%d %b} – {sched.week_end:%d %b %Y}"
        )
        base_total = min(100, sum(sched.initial_drl.values()))
        final_total = min(100, sum(sched.final_drl.values()))
        gain_total = max(0, final_total - base_total)

        # 1. DRL & Week Header Strip
        with ui.element("section").classes("schedule-drl-strip"):
            with ui.row().classes("items-center justify-between w-full gap-3 wrap"):
                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        icon="chevron_left",
                        on_click=lambda: on_shift_week(-1),
                    ).props("round flat dense")
                    with ui.column().classes("gap-0"):
                        ui.label("Weekly Optimized Timetable").classes("eyebrow")
                        ui.label(week_label).classes("schedule-week-title")
                    ui.button(
                        icon="chevron_right",
                        on_click=lambda: on_shift_week(1),
                    ).props("round flat dense")
                    if controller.state.schedule_week_offset != 0:
                        ui.button("This week", on_click=on_this_week).props(
                            "flat dense no-caps"
                        ).classes("today-button")

                with ui.row().classes("items-center gap-2"):
                    with ui.element("div").classes("drl-total-pill"):
                        ui.icon("workspace_premium", size="18px")
                        ui.label(f"{final_total} / 100 DRL").classes("drl-total-num")
                        if gain_total > 0:
                            ui.label(f"+{gain_total} this week").classes("drl-gain-tag")
                    ui.button(
                        "Current DRL",
                        icon="tune",
                        on_click=on_open_drl_dialog,
                    ).props("outline dense no-caps").classes("drl-edit-btn")
                    ui.button(
                        "Re-optimize",
                        icon="auto_awesome",
                        on_click=on_run_schedule,
                    ).props("unelevated dense no-caps color=positive")

            with ui.element("div").classes("drl-articles-grid"):
                for cat_key, cat_label in ARTICLE_LABELS:
                    cap = sched.drl_caps.get(cat_key, 25)
                    base_val = sched.initial_drl.get(cat_key, 0)
                    final_val = sched.final_drl.get(cat_key, 0)
                    gain_val = max(0, final_val - base_val)
                    pct = min(100.0, (final_val / cap) * 100.0) if cap else 0.0
                    with ui.element("div").classes("drl-article-card"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(cat_label).classes("drl-article-name")
                            ui.label(
                                f"{final_val}/{cap}"
                                + (f" (+{gain_val})" if gain_val > 0 else "")
                            ).classes("drl-article-score")
                        with ui.element("div").classes("drl-bar-track"):
                            ui.element("div").classes("drl-bar-fill").style(
                                f"width: {pct:.1f}%"
                            )

        # 2. 7-Day Weekly Schedule Board (Mon -> Sun)
        kind_filter = controller.state.filters.kind
        query = controller.state.filters.query.strip().casefold()

        def _matches(item: CalendarItem) -> bool:
            if kind_filter != "all" and item.kind != kind_filter:
                return False
            if query:
                haystack = " ".join(
                    v for v in (item.title, item.course or "", item.source or "") if v
                ).casefold()
                if query not in haystack:
                    return False
            return True

        visible_scheduled = [it for it in sched.scheduled_items if _matches(it)]

        with ui.element("section").classes("week-board-wrap"):
            with ui.element("div").classes("week-board"):
                for day_idx in range(7):
                    day = sched.week_start + timedelta(days=day_idx)
                    day_blocks = [
                        it for it in visible_scheduled if it.day == day
                    ]
                    col_classes = ["week-col"]
                    if day == date.today():
                        col_classes.append("is-today")
                    if day == controller.state.selected_date:
                        col_classes.append("is-selected")

                    with ui.element("div").classes(" ".join(col_classes)):
                        with ui.element("div").classes("week-col-header"):
                            ui.label(VN_DAY_SHORT[day_idx]).classes("week-day-code")
                            ui.label(f"{day.day:02d}/{day.month:02d}").classes(
                                "week-day-date"
                            )

                        with ui.column().classes("week-col-body gap-2 w-full"):
                            if not day_blocks:
                                ui.label("Free").classes("week-empty-slot")
                            for block in day_blocks:
                                block_classes = [
                                    "sched-block",
                                    f"kind-{block.kind}",
                                ]
                                if block.is_allocated_session or block.flexible:
                                    block_classes.append("is-flexible")
                                if selected and selected.id == block.id:
                                    block_classes.append("active")

                                with ui.element("div").classes(
                                    " ".join(block_classes)
                                ).on(
                                    "click",
                                    lambda chosen=block: on_select_item(chosen.id),
                                ):
                                    with ui.row().classes(
                                        "items-center justify-between w-full no-wrap gap-1"
                                    ):
                                        with ui.row().classes("items-center gap-1 no-wrap"):
                                            if block.is_allocated_session:
                                                ui.icon("schedule_send", size="13px")
                                            ui.label(block.time_label).classes(
                                                "sched-block-time"
                                            )
                                        ui.button(
                                            icon="close",
                                            on_click=lambda tid=block.task_id: on_remove_from_schedule(
                                                tid
                                            ),
                                        ).props(
                                            "flat round dense size=xs"
                                        ).classes("sched-remove-btn").tooltip(
                                            "Remove from schedule"
                                        )

                                    ui.label(block.title).classes("sched-block-title")

                                    meta_bits = [
                                        bit
                                        for bit in (block.room or block.location, block.course)
                                        if bit
                                    ]
                                    if meta_bits:
                                        ui.label(" · ".join(meta_bits)).classes(
                                            "sched-block-meta"
                                        )
                                    if block.points:
                                        ui.label(
                                            f"+{block.points} pts"
                                        ).classes("sched-block-pts")

        # 3. Review & Triage Tabs (Needs Info / Suggestions / Removed)
        active_tab = controller.state.schedule_tab
        tabs = (
            (
                "needs_info",
                "Needs Info",
                len(sched.unschedulable),
                "warning_amber",
            ),
            (
                "suggestions",
                "Unselected Events",
                len(sched.unselected),
                "lightbulb_outline",
            ),
            (
                "removed",
                "Removed from Schedule",
                len(sched.rejected_items),
                "visibility_off",
            ),
        )

        with ui.element("section").classes("schedule-queues"):
            with ui.row().classes("queue-tabs items-center gap-2 wrap"):
                for tab_key, tab_label, count, icon_name in tabs:
                    tab_cls = ["queue-tab-btn"]
                    if active_tab == tab_key:
                        tab_cls.append("active")
                    if tab_key == "needs_info" and count > 0:
                        tab_cls.append("has-warning")
                    with ui.button(
                        on_click=lambda k=tab_key: on_switch_tab(k)
                    ).props("flat no-caps").classes(" ".join(tab_cls)):
                        ui.icon(icon_name, size="16px")
                        ui.label(tab_label)
                        ui.label(str(count)).classes("queue-count-pill")

            with ui.column().classes("queue-list w-full gap-2"):
                if active_tab == "needs_info":
                    _render_proposal_rows(
                        sched.unschedulable,
                        empty_text="All active tasks have complete scheduling information.",
                        primary_label="Complete info",
                        primary_icon="edit_calendar",
                        on_primary=on_edit_task,
                        secondary_label="Remove",
                        secondary_icon="visibility_off",
                        on_secondary=on_remove_from_schedule,
                        on_select_item=on_select_item,
                        on_delete_task=on_delete_task,
                        is_warning=True,
                    )
                elif active_tab == "suggestions":
                    _render_proposal_rows(
                        sched.unselected,
                        empty_text="No unselected DRL events for this week.",
                        primary_label="Pin to schedule",
                        primary_icon="push_pin",
                        on_primary=on_pin_to_schedule,
                        secondary_label="Dismiss",
                        secondary_icon="visibility_off",
                        on_secondary=on_remove_from_schedule,
                        on_select_item=on_select_item,
                        on_delete_task=on_delete_task,
                        on_edit_extra=on_edit_task,
                        is_warning=False,
                    )
                else:
                    _render_removed_rows(
                        sched.rejected_items,
                        on_select_item=on_select_item,
                        on_restore=on_restore_to_schedule,
                        on_edit_task=on_edit_task,
                        on_delete_task=on_delete_task,
                    )


def _render_proposal_rows(
    proposals: list[ScheduleProposal],
    *,
    empty_text: str,
    primary_label: str,
    primary_icon: str,
    on_primary: Callable[[str], Any],
    secondary_label: str,
    secondary_icon: str,
    on_secondary: Callable[[str], Any],
    on_select_item: Callable[[str], Any],
    on_delete_task: Callable[[str], Any],
    on_edit_extra: Callable[[str], Any] | None = None,
    is_warning: bool = False,
) -> None:
    if not proposals:
        with ui.row().classes("queue-empty items-center gap-2"):
            ui.icon("check_circle_outline", size="18px")
            ui.label(empty_text)
        return

    for prop in proposals:
        item = prop.item
        with ui.element("div").classes("queue-row"):
            with ui.column().classes("gap-1 flex-1 min-w-0 cursor-pointer").on(
                "click", lambda chosen=item: on_select_item(chosen.id)
            ):
                with ui.row().classes("items-center gap-2 wrap"):
                    ui.label(item.kind.title()).classes(
                        f"type-badge solid-kind-{item.kind}"
                    )
                    ui.label(item.title).classes("queue-item-title")
                    if item.points:
                        ui.label(
                            f"+{item.points} pts"
                            + (
                                f" · {item.training_point_category}"
                                if item.training_point_category
                                else ""
                            )
                        ).classes("points-label")
                ui.label(prop.reason).classes(
                    f"reason-pill {'warning' if is_warning else 'neutral'}"
                )

            with ui.row().classes("items-center gap-1 no-wrap"):
                ui.button(
                    primary_label,
                    icon=primary_icon,
                    on_click=lambda tid=item.task_id: on_primary(tid),
                ).props("unelevated dense no-caps color=positive")
                if on_edit_extra is not None:
                    ui.button(
                        icon="edit",
                        on_click=lambda tid=item.task_id: on_edit_extra(tid),
                    ).props("flat round dense").tooltip("Edit task")
                ui.button(
                    secondary_label,
                    icon=secondary_icon,
                    on_click=lambda tid=item.task_id: on_secondary(tid),
                ).props("outline dense no-caps")
                ui.button(
                    icon="delete_outline",
                    on_click=lambda tid=item.task_id: on_delete_task(tid),
                ).props("flat round dense color=negative").tooltip("Delete permanently")


def _render_removed_rows(
    items: list[CalendarItem],
    *,
    on_select_item: Callable[[str], Any],
    on_restore: Callable[[str], Any],
    on_edit_task: Callable[[str], Any],
    on_delete_task: Callable[[str], Any],
) -> None:
    if not items:
        with ui.row().classes("queue-empty items-center gap-2"):
            ui.icon("inbox", size="18px")
            ui.label("No tasks have been removed from your schedule.")
        return

    for item in items:
        with ui.element("div").classes("queue-row"):
            with ui.column().classes("gap-1 flex-1 min-w-0 cursor-pointer").on(
                "click", lambda chosen=item: on_select_item(chosen.id)
            ):
                with ui.row().classes("items-center gap-2 wrap"):
                    ui.label(item.kind.title()).classes(
                        f"type-badge solid-kind-{item.kind}"
                    )
                    ui.label(item.title).classes("queue-item-title")
                ui.label(
                    " · ".join(
                        p for p in (item.time_label, item.source) if p
                    )
                ).classes("agenda-meta")

            with ui.row().classes("items-center gap-1 no-wrap"):
                ui.button(
                    "Restore",
                    icon="restore",
                    on_click=lambda tid=item.task_id: on_restore(tid),
                ).props("outline dense no-caps color=positive")
                ui.button(
                    icon="edit",
                    on_click=lambda tid=item.task_id: on_edit_task(tid),
                ).props("flat round dense").tooltip("Edit task")
                ui.button(
                    icon="delete_outline",
                    on_click=lambda tid=item.task_id: on_delete_task(tid),
                ).props("flat round dense color=negative").tooltip("Delete permanently")
