from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path

from DataProcessor.Standardization.BaseTask import DateDayTime
from DataProcessor.Standardization.ExtractedTask import ExtractedTask, VN_TZ
from client.core.controller import ClientController
from client.core.live_backend import LiveBackend
from client.core.mock_backend import MockBackend
from client.core.models import TaskDraft


def _next_week_anchor() -> date:
    today = date.today()
    next_monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
    return next_monday


def test_mock_schedule_complete_info_remove_restore_and_delete() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        controller = ClientController(backend)
        user = await controller.login("student", "demo")

        next_monday = _next_week_anchor()
        event_day = next_monday + timedelta(days=2)  # Wednesday next week
        due_day = next_monday + timedelta(days=4)    # Friday next week

        # 1. Create an incomplete event (missing DRL category) -> lands in Needs Info
        await backend.create_task(
            user,
            TaskDraft(
                title="AI Seminar without category",
                kind="event",
                scheduled_date=event_day,
                start_time=time(9, 0),
                end_time=time(11, 0),
                training_points=6,
            ),
        )
        # 2. Create a flexible assignment -> auto-allocated into daytime slots
        await backend.create_task(
            user,
            TaskDraft(
                title="Write CT report",
                kind="assignment",
                deadline=datetime.combine(due_day, time(20, 0), tzinfo=VN_TZ),
                estimated_hours=2.5,
                flexible=True,
                compulsory=True,
            ),
        )

        await controller.load_month(next_monday)
        await controller.load_schedule(week_offset=1)
        sched = controller.state.schedule
        assert sched is not None

        # Recurring classes + allocated assignment should be scheduled
        scheduled_titles = [it.title for it in sched.scheduled_items]
        assert "CSC10001 · Computational Thinking" in scheduled_titles
        assert "Write CT report" in scheduled_titles

        # Incomplete seminar is flagged in unschedulable (Needs Info)
        unsched_map = {p.item.title: p for p in sched.unschedulable}
        assert "AI Seminar without category" in unsched_map
        seminar_id = unsched_map["AI Seminar without category"].item.task_id

        # 3. Complete missing info (add Articles 1 + estimated_hours)
        upd = await backend.update_task(
            user,
            seminar_id,
            TaskDraft(
                title="AI Seminar without category",
                kind="event",
                scheduled_date=event_day,
                start_time=time(9, 0),
                end_time=time(11, 0),
                training_points=6,
                training_point_category="Articles 1",
                estimated_hours=2.0,
            ),
        )
        assert upd.ok is True

        await controller.load_schedule(week_offset=1)
        sched = controller.state.schedule
        assert sched is not None
        assert any(it.task_id == seminar_id for it in sched.scheduled_items)
        assert sched.final_drl["Articles 1"] == 6

        # 4. Baseline DRL caps gain accurately (28 existing + 6 event -> capped at 30)
        await backend.save_initial_drl(user, {"Articles 1": 28})
        await controller.load_schedule(week_offset=1)
        assert controller.state.schedule is not None
        assert controller.state.schedule.final_drl["Articles 1"] == 30
        assert controller.scheduled_drl_gain == 2

        # 5. Remove task from schedule (status='rejected') without deleting
        rem = await backend.set_task_schedule_state(
            user, seminar_id, status="rejected"
        )
        assert rem.ok is True
        await controller.load_month(next_monday)
        await controller.load_schedule(week_offset=1)
        sched = controller.state.schedule
        assert sched is not None
        assert not any(it.task_id == seminar_id for it in sched.scheduled_items)
        assert any(it.task_id == seminar_id for it in sched.rejected_items)
        assert not any(it.task_id == seminar_id for it in controller.active_items)

        # 6. Restore task back to schedule
        res = await backend.set_task_schedule_state(
            user, seminar_id, status="proposed"
        )
        assert res.ok is True
        await controller.load_schedule(week_offset=1)
        assert controller.state.schedule is not None
        assert any(
            it.task_id == seminar_id
            for it in controller.state.schedule.scheduled_items
        )

        # 7. Permanently delete crawled fixture task ('class-ct')
        del_res = await backend.delete_task(user, "class-ct")
        assert del_res.ok is True
        await controller.load_month(next_monday)
        await controller.load_schedule(week_offset=1)
        assert not any(it.task_id == "class-ct" for it in controller.state.items)
        assert not any(
            it.task_id == "class-ct"
            for it in controller.state.schedule.scheduled_items
        )

    asyncio.run(scenario())


def test_live_backend_persists_crawled_task_edits_and_deletions_across_syncs(
    monkeypatch, tmp_path: Path
) -> None:
    from DataProcessor.Standardization.User import User

    next_monday = _next_week_anchor()
    due_day = next_monday + timedelta(days=3)

    backend_user = User(
        id="live-user-1",
        username="student@hcmus.edu.vn",
        training_points={"Articles 3": 10},
    )
    crawled_assignment = ExtractedTask(
        id="moodle-hw-1",
        user_id="live-user-1",
        title="Moodle Homework Missing Hours",
        type="assignment",
        deadline=datetime.combine(due_day, time(23, 0), tzinfo=VN_TZ),
        estimated_hours=None,
        source_url="https://courses.ctda.hcmus.edu.vn/mod/assign/1",
        source_platform="Moodle",
        updated_at=datetime.now(VN_TZ),
    )
    public_event = ExtractedTask(
        id="osa-ev-1",
        title="OSA Youth Seminar",
        type="event",
        start_time=DateDayTime(date=next_monday + timedelta(days=1), time=time(14, 0)),
        end_time=DateDayTime(date=next_monday + timedelta(days=1), time=time(16, 0)),
        training_points=5,
        training_point_category="Articles 3",
        estimated_hours=2.0,
        source_url="https://ctsv.hcmus.edu.vn/ev1",
        source_platform="Phòng Công tác sinh viên",
        updated_at=datetime.now(VN_TZ),
    )

    monkeypatch.setattr(
        "Database.auth.sign_in",
        lambda u, p: ("token-abc", backend_user),
    )
    monkeypatch.setattr(
        "Database.Repository.task_repository.TaskRepository.get_tasks",
        lambda self, limit=None: [public_event],
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
        lambda self, limit=None: [crawled_assignment],
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.delete_tasks",
        lambda self, tasks: None,
    )

    async def scenario() -> None:
        backend = LiveBackend(local_db_dir=tmp_path)
        user = await backend.login("student@hcmus.edu.vn", "secret123")

        # Initial schedule: Moodle homework lacks estimated_hours -> unschedulable
        sched1 = await backend.run_schedule(user, week_anchor=next_monday)
        assert any(p.item.task_id == "moodle-hw-1" for p in sched1.unschedulable)
        assert any(it.task_id == "osa-ev-1" for it in sched1.scheduled_items)
        assert sched1.final_drl["Articles 3"] == 15  # 10 baseline + 5 event

        # User completes missing estimated_hours on crawled Moodle task
        upd = await backend.update_task(
            user,
            "moodle-hw-1",
            TaskDraft(
                title="Moodle Homework Missing Hours",
                kind="assignment",
                deadline=datetime.combine(due_day, time(23, 0), tzinfo=VN_TZ),
                estimated_hours=3.0,
                flexible=True,
                compulsory=True,
            ),
        )
        assert upd.ok is True

        # Re-run schedule: cloud still returns estimated_hours=None, but user_modified wins!
        sched2 = await backend.run_schedule(user, week_anchor=next_monday)
        assert not any(p.item.task_id == "moodle-hw-1" for p in sched2.unschedulable)
        assert any(it.task_id == "moodle-hw-1" for it in sched2.scheduled_items)

        # Permanently delete public crawled event -> stays deleted on next sync
        deleted = await backend.delete_task(user, "osa-ev-1")
        assert deleted.ok is True
        sched3 = await backend.run_schedule(user, week_anchor=next_monday)
        assert not any(it.task_id == "osa-ev-1" for it in sched3.scheduled_items)

    asyncio.run(scenario())
