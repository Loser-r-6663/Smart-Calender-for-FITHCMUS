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


if __name__ == "__main__":
    unittest.main()

