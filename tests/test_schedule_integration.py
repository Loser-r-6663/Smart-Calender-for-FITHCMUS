from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

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
        event_day = next_monday + timedelta(days=2)
        due_day = next_monday + timedelta(days=4)

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

        scheduled_titles = [it.title for it in sched.scheduled_items]
        assert "CSC10001 · Computational Thinking" in scheduled_titles
        assert "Write CT report" in scheduled_titles

        unsched_map = {p.item.title: p for p in sched.unschedulable}
        assert "AI Seminar without category" in unsched_map
        seminar_id = unsched_map["AI Seminar without category"].item.task_id

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

        await backend.save_initial_drl(user, {"Articles 1": 28})
        await controller.load_schedule(week_offset=1)
        assert controller.state.schedule is not None
        assert controller.state.schedule.final_drl["Articles 1"] == 30
        assert controller.scheduled_drl_gain == 2

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


def test_live_backend_uses_user_task_state_and_supabase_overrides(
    monkeypatch,
) -> None:
    from DataProcessor.Standardization.User import User

    next_monday = _next_week_anchor()
    due_day = next_monday + timedelta(days=3)

    backend_user = User(
        id="live-user-1",
        username="student@hcmus.edu.vn",
        training_points={"Articles 3": 10},
    )
    personal_store: dict[str, ExtractedTask] = {
        "moodle-hw-1": ExtractedTask(
            id="moodle-hw-1",
            user_id="live-user-1",
            title="Moodle Homework Missing Hours",
            type="assignment",
            deadline=datetime.combine(due_day, time(23, 0), tzinfo=VN_TZ),
            estimated_hours=None,
            source_url="https://courses.ctda.hcmus.edu.vn/mod/assign/1",
            source_platform="Moodle",
            updated_at=datetime.now(VN_TZ),
        ),
        "null-custom-1": ExtractedTask(
            id="null-custom-1",
            user_id="live-user-1",
            title="Migrated personal task",
            type="personal",
            start_time=DateDayTime(date=next_monday, time=time(15, 0)),
            end_time=DateDayTime(date=next_monday, time=time(16, 30)),
            source_url="",
            source_platform=None,
            updated_at=datetime.now(VN_TZ),
        ),
    }
    public_store: dict[str, ExtractedTask] = {
        "osa-ev-1": ExtractedTask(
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
    }
    state_store: dict[str, dict[str, bool | str]] = {}

    monkeypatch.setattr(
        "Database.auth.sign_in",
        lambda u, p: ("token-abc", backend_user),
    )
    monkeypatch.setattr(
        "Database.Repository.task_repository.TaskRepository.get_tasks",
        lambda self, limit=None: list(public_store.values()),
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
        lambda self, limit=None: list(personal_store.values()),
    )

    def update_owned(self, task_id: str, task: ExtractedTask) -> bool:
        if task_id not in personal_store:
            return False
        task.id = task_id
        personal_store[task_id] = task
        return True

    def delete_owned(self, task_id: str) -> bool:
        return personal_store.pop(task_id, None) is not None

    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.update_owned_task",
        update_owned,
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.delete_owned_task",
        delete_owned,
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_state_repository.UserTaskStateRepository.get_task_states",
        lambda self, tasks: {
            t.id: dict(state_store[t.id])
            for t in tasks
            if getattr(t, "id", None) in state_store
        },
    )

    def upsert_states(self, tasks):
        for t in tasks:
            state_store[t.id] = {
                "recurrence": t.recurrence,
                "status": t.status,
                "compulsory": t.compulsory,
                "flexible": t.flexible,
            }

    monkeypatch.setattr(
        "Database.Repository.user_task_state_repository.UserTaskStateRepository.update_tasks",
        upsert_states,
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_state_repository.UserTaskStateRepository.delete_task_states",
        lambda self, ids: [state_store.pop(i, None) for i in ids],
    )

    async def scenario() -> None:
        backend = LiveBackend()
        user = await backend.login("student@hcmus.edu.vn", "secret123")

        # 1. Initial schedule: Moodle homework lacks estimated_hours -> unschedulable;
        # migrated null-source 'personal' task & OSA event are scheduled!
        sched1 = await backend.run_schedule(user, week_anchor=next_monday)
        assert any(p.item.task_id == "moodle-hw-1" for p in sched1.unschedulable)
        assert any(it.task_id == "null-custom-1" for it in sched1.scheduled_items)
        assert any(it.task_id == "osa-ev-1" for it in sched1.scheduled_items)
        assert sched1.final_drl["Articles 3"] == 15
        assert state_store["osa-ev-1"]["status"] == "scheduled"
        assert state_store["moodle-hw-1"]["status"] == "proposed"

        # 2. Complete missing estimated_hours on personal Moodle task in user_task
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

        sched2 = await backend.run_schedule(user, week_anchor=next_monday)
        assert not any(p.item.task_id == "moodle-hw-1" for p in sched2.unschedulable)
        assert any(it.task_id == "moodle-hw-1" for it in sched2.scheduled_items)

        # 3. Remove public event from schedule via user_task_state ('rejected')
        rem = await backend.set_task_schedule_state(
            user, "osa-ev-1", status="rejected"
        )
        assert rem.ok is True
        assert state_store["osa-ev-1"]["status"] == "rejected"

        sched3 = await backend.run_schedule(user, week_anchor=next_monday)
        assert not any(it.task_id == "osa-ev-1" for it in sched3.scheduled_items)
        assert any(it.task_id == "osa-ev-1" for it in sched3.rejected_items)

        # 4. Delete owned Moodle task -> removed from user_task & user_task_state
        deleted = await backend.delete_task(user, "moodle-hw-1")
        assert deleted.ok is True
        assert "moodle-hw-1" not in personal_store
        assert "moodle-hw-1" not in state_store

    asyncio.run(scenario())
