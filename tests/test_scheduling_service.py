import sys
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Backend.Scheduling.service import (
    GMT_PLUS_7,
    SchedulePersistenceSummary,
    SchedulingService,
    UserNotFoundError,
    current_week_bounds,
    parse_recurrence,
    prepare_tasks_for_scheduler,
)
from Database.task_config import TASK_DEFAULTS
from Database.task_objects import TaskObject
from Database.user_objects import UserDRLScoresObject, UserObject, UserTaskObject


def make_task_object(**overrides: object) -> TaskObject:
    payload: dict[str, object] = {
        "id": "task-1",
        "title": "Sample Task",
        "type": "personal",
        **TASK_DEFAULTS,
        "updated_at": datetime(2026, 11, 9, 0, 0, tzinfo=GMT_PLUS_7),
    }
    payload.update(overrides)
    return TaskObject.model_validate(payload)


class SchedulingServiceTests(unittest.TestCase):
    def test_parse_recurrence_handles_valid_and_invalid_values(self) -> None:
        self.assertEqual(parse_recurrence("T2 07:30-09:30"), (0, time(7, 30), time(9, 30)))
        self.assertEqual(parse_recurrence("CN 18:00-20:00"), (6, time(18, 0), time(20, 0)))
        self.assertIsNone(parse_recurrence(None))
        self.assertIsNone(parse_recurrence("T8 08:00-10:00"))
        self.assertIsNone(parse_recurrence("T2 10:00-09:00"))
        self.assertIsNone(parse_recurrence("invalid"))

    def test_current_week_bounds_returns_monday_to_sunday(self) -> None:
        monday, sunday = current_week_bounds(date(2026, 11, 11))
        self.assertEqual(monday, date(2026, 11, 9))
        self.assertEqual(sunday, date(2026, 11, 15))

    def test_prepare_tasks_expands_recurrence_across_candidate_weeks_and_filters_unassigned_zero_point_events(
        self,
    ) -> None:
        portal_class = make_task_object(
            id="portal-csc10006",
            title="CSC10006 - Co so du lieu",
            type="class",
            location="CS1",
            recurrence="T3 07:30-09:30",
            source_platform="portal",
        )
        next_week_event_utc = make_task_object(
            id="drl-next-week",
            title="Hoi thao AI tuan sau",
            type="event",
            location="CS1",
            # 01:00 UTC == 08:00 GMT+7 on Tuesday 2026-11-17
            start_time=datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc),
            training_points=5,
            drl_category="dieu_1",
        )
        unassigned_public_news = make_task_object(
            id="osa-news-1",
            title="Ngay hoi doc sach",
            type="event",
            start_time=datetime(2026, 11, 11, 14, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 11, 16, 0, tzinfo=GMT_PLUS_7),
            training_points=0,
        )
        assigned_zero_point_event = make_task_object(
            id="assigned-event",
            title="Su kien da dang ky",
            type="event",
            start_time=datetime(2026, 11, 12, 14, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 12, 16, 0, tzinfo=GMT_PLUS_7),
            training_points=0,
        )

        prepared = prepare_tasks_for_scheduler(
            [
                portal_class,
                next_week_event_utc,
                unassigned_public_news,
                assigned_zero_point_event,
            ],
            week_start=date(2026, 11, 9),
            assigned_task_ids={"assigned-event"},
        )

        class_occurrences = [t for t in prepared if t["id"] == "portal-csc10006"]
        self.assertEqual(len(class_occurrences), 2)
        self.assertEqual(
            [occ["start_time"] for occ in class_occurrences],
            [
                datetime(2026, 11, 10, 7, 30, tzinfo=GMT_PLUS_7),
                datetime(2026, 11, 17, 7, 30, tzinfo=GMT_PLUS_7),
            ],
        )

        prepared_ids = {t["id"] for t in prepared}
        self.assertIn("drl-next-week", prepared_ids)
        self.assertIn("assigned-event", prepared_ids)
        self.assertNotIn("osa-news-1", prepared_ids)

        event_dict = next(t for t in prepared if t["id"] == "drl-next-week")
        self.assertEqual(event_dict["start_time"], datetime(2026, 11, 17, 8, 0, tzinfo=GMT_PLUS_7))

    def test_prepare_tasks_restrict_to_window_filters_other_weeks(self) -> None:
        this_week = make_task_object(
            id="ev-this-week",
            title="Su kien tuan nay",
            type="event",
            start_time=datetime(2026, 11, 12, 9, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 12, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=4,
            drl_category="dieu_3",
        )
        next_week = make_task_object(
            id="ev-next-week",
            title="Su kien tuan sau",
            type="event",
            start_time=datetime(2026, 11, 19, 9, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 19, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=8,
            drl_category="dieu_3",
        )

        prepared = prepare_tasks_for_scheduler(
            [this_week, next_week],
            week_start=date(2026, 11, 9),
            restrict_to_window=True,
        )

        self.assertEqual([item["id"] for item in prepared], ["ev-this-week"])

    def test_service_run_dry_run_blocks_drl_event_overlapping_portal_class(self) -> None:
        portal_class = make_task_object(
            id="portal-tue",
            title="Lap trinh mang",
            type="class",
            location="CS1",
            recurrence="T3 07:30-09:30",
        )
        conflicting_event = make_task_object(
            id="ev-conflict",
            title="Workshop trung gio hoc",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 10, 8, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 10, 10, 0, tzinfo=GMT_PLUS_7),
            training_points=10,
            drl_category="dieu_1",
        )
        valid_event = make_task_object(
            id="ev-valid",
            title="Hien mau tinh nguyen",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 11, 8, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 11, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=7,
            drl_category="dieu_4",
        )

        database = Mock()
        database.list_tasks.return_value = [portal_class, conflicting_event, valid_event]

        service = SchedulingService(database=database)
        run_result = service.run(
            week_start=date(2026, 11, 9),
            initial_drl={"dieu_1": 10, "dieu_4": 5},
            persist=False,
        )

        self.assertIsNone(run_result.persistence)
        self.assertEqual(run_result.total_tasks_loaded, 3)
        self.assertEqual(
            [ev.task_id for ev in run_result.schedule.selected_events],
            ["ev-valid"],
        )
        self.assertEqual(run_result.schedule.total_drl_gained, 7)
        database.assign_task.assert_not_called()
        database.set_daily_task.assert_not_called()

    def test_service_run_persist_assigns_tasks_and_saves_daily_tasks_in_gmt7(self) -> None:
        # 2026-11-11 17:30 UTC == 2026-11-12 00:30 GMT+7 (work_date must be 2026-11-12)
        late_night_event = make_task_object(
            id="ev-gmt7-boundary",
            title="Trac nghiem online",
            type="event",
            location="ONLINE",
            start_time=datetime(2026, 11, 11, 17, 30, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
            training_points=3,
            drl_category="dieu_2",
        )
        day_event = make_task_object(
            id="ev-already-assigned",
            title="Hoat dong cong dong",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 13, 14, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 13, 16, 0, tzinfo=GMT_PLUS_7),
            training_points=5,
            drl_category="dieu_4",
        )

        database = Mock()
        database.get_user.return_value = UserObject(
            id=1, username="sv01", email="sv01@example.edu", full_name="Nguyen Van A"
        )
        database.get_user_tasks.return_value = [
            UserTaskObject(
                user_id=1,
                task_id="ev-already-assigned",
                assigned_at=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
            )
        ]
        database.list_tasks.return_value = [late_night_event, day_event]
        database.assign_task.side_effect = [True, False]
        database.set_daily_task.side_effect = [
            {"work_date": date(2026, 11, 12), "task_id": "ev-gmt7-boundary", "is_completed_today": False},
            {"work_date": date(2026, 11, 13), "task_id": "ev-already-assigned", "is_completed_today": False},
        ]

        service = SchedulingService(database=database)
        run_result = service.run(
            user_id=1,
            week_start=date(2026, 11, 9),
            persist=True,
        )

        self.assertIsInstance(run_result.persistence, SchedulePersistenceSummary)
        assert run_result.persistence is not None
        self.assertEqual(run_result.persistence.user_id, 1)
        self.assertEqual(run_result.persistence.newly_assigned_count, 1)
        self.assertEqual(
            run_result.persistence.assigned_task_ids,
            ("ev-gmt7-boundary", "ev-already-assigned"),
        )
        database.set_daily_task.assert_any_call(
            date(2026, 11, 12), "ev-gmt7-boundary", is_completed_today=False
        )
        database.set_daily_task.assert_any_call(
            date(2026, 11, 13), "ev-already-assigned", is_completed_today=False
        )

    def test_service_run_rejects_missing_user_or_invalid_args(self) -> None:
        database = Mock()
        service = SchedulingService(database=database)

        with self.assertRaises(ValueError):
            service.run(persist=True)

        database.get_user.return_value = None
        with self.assertRaises(UserNotFoundError):
            service.run(user_id=999, persist=True)

        with self.assertRaises(ValueError):
            prepare_tasks_for_scheduler(
                [],
                week_start=date(2026, 11, 15),
                week_end=date(2026, 11, 9),
            )

    def test_service_run_loads_stored_user_drl_scores_when_initial_drl_omitted(
        self,
    ) -> None:
        # User already has 27/30 in dieu_1 stored in user_drl_scores; event gives 8 pts -> gain capped at 3
        event_dieu_1 = make_task_object(
            id="ev-d1",
            title="Hoi thao NCKH",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 12, 9, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 12, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=8,
            drl_category="dieu_1",
        )
        database = Mock()
        database.get_user.return_value = UserObject(
            id=1, username="sv01", email="sv01@example.edu"
        )
        database.get_user_tasks.return_value = []
        database.get_user_drl_scores.return_value = UserDRLScoresObject(
            user_id=1, dieu_1=27, dieu_2=10
        )
        database.list_tasks.return_value = [event_dieu_1]

        service = SchedulingService(database=database)
        res = service.run(user_id=1, week_start=date(2026, 11, 9), persist=False)

        self.assertEqual(res.schedule.initial_drl["dieu_1"], 27)
        self.assertEqual(res.schedule.initial_drl["dieu_2"], 10)
        self.assertEqual(res.schedule.total_drl_gained, 3)
        self.assertEqual(res.schedule.final_drl["dieu_1"], 30)
        database.get_user_drl_scores.assert_called_once_with(1)

        override_res = service.run(
            user_id=1,
            initial_drl={"dieu_1": 20},
            week_start=date(2026, 11, 9),
            persist=False,
        )
        self.assertEqual(override_res.schedule.total_drl_gained, 8)
        self.assertEqual(override_res.schedule.final_drl["dieu_1"], 28)

    def test_flexible_workload_reserves_study_slack(self) -> None:
        from Backend.Scheduling.branch_and_bound_scheduler import BranchAndBoundScheduler

        scheduler = BranchAndBoundScheduler()
        tasks = [
            {
                "id": "class-morning",
                "title": "Lop hoc buoi sang",
                "type": "class",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 10, 0, tzinfo=GMT_PLUS_7),
                "training_points": 0,
            },
            # Assignment window 08:00 - 13:00 (5h), needs 2.5h
            {
                "id": "assign-due-13",
                "title": "Bai tap can nop 13h",
                "type": "assignment",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                "deadline": datetime(2026, 11, 9, 13, 0, tzinfo=GMT_PLUS_7),
                "estimated_hours": 2.5,
                "training_points": 0,
            },
            # Workshop A: 10:30 - 12:30 (2h overlap > 0.5h slack) -> must be pruned
            {
                "id": "ws-A",
                "title": "Workshop A (Chiem het gio lam bai)",
                "type": "event",
                "start_time": datetime(2026, 11, 9, 10, 30, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 12, 30, tzinfo=GMT_PLUS_7),
                "training_points": 10,
                "drl_category": "dieu_3",
            },
            # Workshop B: 14:00 - 16:00 (outside window) -> can be selected
            {
                "id": "ws-B",
                "title": "Workshop B (Sau deadline)",
                "type": "event",
                "start_time": datetime(2026, 11, 9, 14, 0, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 16, 0, tzinfo=GMT_PLUS_7),
                "training_points": 8,
                "drl_category": "dieu_3",
            },
        ]
        res = scheduler.schedule(tasks)
        selected_ids = [ev.task_id for ev in res.selected_events]
        self.assertNotIn("ws-A", selected_ids)
        self.assertIn("ws-B", selected_ids)
        self.assertEqual(res.total_drl_gained, 8)

    def test_class_room_auto_tags_cs1_for_travel_buffer(self) -> None:
        from Backend.Scheduling.branch_and_bound_scheduler import BranchAndBoundScheduler

        scheduler = BranchAndBoundScheduler()
        tasks = [
            # Lớp học chỉ ghi tên phòng 'Phòng F.102' (không có chữ cơ sở 1)
            {
                "id": "class-room-only",
                "title": "Co So Du Lieu",
                "type": "class",
                "location": "Phòng F.102",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 10, 0, tzinfo=GMT_PLUS_7),
                "training_points": 0,
            },
            # Sự kiện CS2 bắt đầu lúc 10:30 (cách 30m sau khi tan học CS1, thiếu buffer 60m) -> Phải bị loại
            {
                "id": "ev-cs2-too-close",
                "title": "Hoi thao CS2 qua gan",
                "type": "event",
                "location": "Hội trường CS2, Linh Trung, Thủ Đức",
                "start_time": datetime(2026, 11, 9, 10, 30, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 12, 0, tzinfo=GMT_PLUS_7),
                "training_points": 10,
                "drl_category": "dieu_3",
            },
            # Sự kiện CS2 bắt đầu lúc 11:30 (cách 90m sau khi tan học CS1, đủ buffer 60m) -> Được chọn
            {
                "id": "ev-cs2-safe",
                "title": "Hoi thao CS2 du gio di chuyen",
                "type": "event",
                "location": "Hội trường CS2, Linh Trung, Thủ Đức",
                "start_time": datetime(2026, 11, 9, 11, 30, tzinfo=GMT_PLUS_7),
                "end_time": datetime(2026, 11, 9, 13, 0, tzinfo=GMT_PLUS_7),
                "training_points": 8,
                "drl_category": "dieu_3",
            },
        ]
        res = scheduler.schedule(tasks)
        selected_ids = [ev.task_id for ev in res.selected_events]
        self.assertNotIn("ev-cs2-too-close", selected_ids)
        self.assertIn("ev-cs2-safe", selected_ids)
        self.assertEqual(res.total_drl_gained, 8)

    def test_personal_task_scoped_to_assigned_user_only(self) -> None:
        user_personal = make_task_object(
            id="personal-u1",
            title="Lich kham rang cua User 1",
            type="personal",
            start_time=datetime(2026, 11, 10, 14, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 10, 16, 0, tzinfo=GMT_PLUS_7),
            is_manual=True,
        )
        other_personal = make_task_object(
            id="personal-u2",
            title="Lich ca nhan cua User khac",
            type="personal",
            start_time=datetime(2026, 11, 11, 14, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 11, 16, 0, tzinfo=GMT_PLUS_7),
            is_manual=True,
        )
        ev_conflict_u1 = make_task_object(
            id="ev-tue",
            title="Workshop chieu T3",
            type="event",
            start_time=datetime(2026, 11, 10, 14, 30, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 10, 15, 30, tzinfo=GMT_PLUS_7),
            training_points=10,
            drl_category="dieu_3",
        )
        ev_during_u2_personal = make_task_object(
            id="ev-wed",
            title="Workshop chieu T4",
            type="event",
            start_time=datetime(2026, 11, 11, 14, 30, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 11, 15, 30, tzinfo=GMT_PLUS_7),
            training_points=6,
            drl_category="dieu_3",
        )

        database = Mock()
        database.get_user.return_value = UserObject(id=1, username="sv01", email="sv01@example.edu")
        database.get_user_tasks.return_value = [
            UserTaskObject(
                user_id=1,
                task_id="personal-u1",
                assigned_at=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
            )
        ]
        database.get_user_drl_scores.return_value = UserDRLScoresObject(user_id=1)
        database.list_tasks.return_value = [
            user_personal,
            other_personal,
            ev_conflict_u1,
            ev_during_u2_personal,
        ]

        res = SchedulingService(database=database).run(user_id=1, week_start=date(2026, 11, 9), persist=False)
        selected_ids = [ev.task_id for ev in res.schedule.selected_events]
        self.assertNotIn("ev-tue", selected_ids)
        self.assertIn("ev-wed", selected_ids)
        self.assertEqual(res.schedule.total_drl_gained, 6)

    def test_user_task_pin_reject_and_custom_reschedule(self) -> None:
        pinned_low_pts = make_task_object(
            id="ev-pinned",
            title="Hoi thao da danh dau",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 12, 9, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 12, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=4,
            drl_category="dieu_3",
        )
        higher_conflicting = make_task_object(
            id="ev-conflict-high",
            title="Hoi thao trung gio diem cao hon",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 12, 9, 30, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 12, 10, 30, tzinfo=GMT_PLUS_7),
            training_points=12,
            drl_category="dieu_3",
        )
        rejected_high = make_task_object(
            id="ev-rejected",
            title="Su kien user khong thich",
            type="event",
            location="CS1",
            start_time=datetime(2026, 11, 13, 9, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 13, 11, 0, tzinfo=GMT_PLUS_7),
            training_points=15,
            drl_category="dieu_3",
        )
        flexible_rescheduled = make_task_object(
            id="ev-flex-custom",
            title="Khao sat online doi gio",
            type="event",
            location="ONLINE",
            start_time=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
            end_time=datetime(2026, 11, 15, 23, 0, tzinfo=GMT_PLUS_7),
            training_points=5,
            drl_category="dieu_4",
        )

        custom_start = datetime(2026, 11, 14, 19, 0, tzinfo=GMT_PLUS_7)
        custom_end = datetime(2026, 11, 14, 19, 30, tzinfo=GMT_PLUS_7)

        database = Mock()
        database.get_user.return_value = UserObject(id=1, username="sv01", email="sv01@example.edu")
        database.get_user_tasks.return_value = [
            UserTaskObject(
                user_id=1,
                task_id="ev-pinned",
                assigned_at=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                pin_status="pinned",
            ),
            UserTaskObject(
                user_id=1,
                task_id="ev-rejected",
                assigned_at=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                pin_status="rejected",
            ),
            UserTaskObject(
                user_id=1,
                task_id="ev-flex-custom",
                assigned_at=datetime(2026, 11, 9, 8, 0, tzinfo=GMT_PLUS_7),
                pin_status="pinned",
                custom_start_time=custom_start,
                custom_end_time=custom_end,
            ),
        ]
        database.get_user_drl_scores.return_value = UserDRLScoresObject(user_id=1)
        database.list_tasks.return_value = [
            pinned_low_pts,
            higher_conflicting,
            rejected_high,
            flexible_rescheduled,
        ]

        res = SchedulingService(database=database).run(user_id=1, week_start=date(2026, 11, 9), persist=False)
        selected_map = {ev.task_id: ev for ev in res.schedule.selected_events}
        self.assertIn("ev-pinned", selected_map)
        self.assertNotIn("ev-conflict-high", selected_map)
        self.assertNotIn("ev-rejected", selected_map)
        self.assertIn("ev-flex-custom", selected_map)
        self.assertEqual(selected_map["ev-flex-custom"].start_time, custom_start)
        self.assertEqual(selected_map["ev-flex-custom"].end_time, custom_end)
        self.assertEqual(res.schedule.total_drl_gained, 9)


if __name__ == "__main__":
    unittest.main()

