"""Offline mapping checks using valid tasks and fictional persisted UUIDs."""

import unittest
from datetime import date, datetime, time

from academic_search import map_task
from DataProcessor.Standardization.ExtractedTask import ExtractedTask, VN_TZ

SHARED_ID = "11111111-1111-4111-8111-111111111111"
CLASS_ID = "22222222-2222-4222-8222-222222222222"
NOTICE_ID = "33333333-3333-4333-8333-333333333333"
UPDATED = datetime(2026, 11, 23, 9, tzinfo=VN_TZ)


def task(**values):
    return ExtractedTask(
        **{
            "id": SHARED_ID,
            "title": "Sinh hoạt sinh viên",
            "type": "announcement",
            "source_platform": "Khoa Công nghệ thông tin",
            "source_url": "https://example.invalid/notices/1",
            "updated_at": UPDATED,
            **values,
        }
    )


class SearchRecordTests(unittest.TestCase):
    def test_public_event_preserves_absolute_times_and_zero_points(self):
        original = task(
            type="event", description="Hoạt động cộng đồng", course="CSC10004",
            training_points=0, estimated_hours=2,
            start_time={"date": "2026-11-25", "time": "08:30:15"},
            end_time={"date": "2026-11-25", "time": "10:30:15"},
        )
        result = map_task(original, scope="public")
        self.assertEqual(result.key, ("public", SHARED_ID))
        self.assertEqual(result.title, "Sinh hoạt sinh viên")
        self.assertEqual(result.description, "Hoạt động cộng đồng")
        self.assertEqual(result.course, "CSC10004")
        self.assertEqual(result.type, "event")
        self.assertEqual(result.publisher, "Khoa Công nghệ thông tin")
        self.assertEqual(result.source_url, "https://example.invalid/notices/1")
        self.assertEqual(result.training_points, 0)
        self.assertIsNone(result.deadline)
        self.assertEqual(result.start_time.date, date(2026, 11, 25))
        self.assertEqual(result.start_time.time, time(8, 30, 15))
        self.assertIsNone(result.start_time.day)
        self.assertEqual(result.end_time.date, date(2026, 11, 25))
        self.assertEqual(result.end_time.time, time(10, 30, 15))
        self.assertIsNone(result.end_time.day)
        original.start_time.date = date(2026, 12, 1)
        self.assertEqual(result.start_time.date, date(2026, 11, 25))

    def test_personal_assignment_preserves_deadline_and_missing_points(self):
        deadline = datetime(2026, 11, 30, 23, 59, 58, 123456, tzinfo=VN_TZ)
        original = task(
            type="assignment", title="Nộp bài tập", course="CSC10004",
            source_platform="Moodle", source_url="https://example.invalid/assignments/1",
            deadline=deadline,
        )
        result = map_task(original, scope="personal")
        self.assertEqual(result.key, ("personal", SHARED_ID))
        self.assertEqual(result.title, "Nộp bài tập")
        self.assertEqual(result.type, "assignment")
        self.assertEqual(result.course, "CSC10004")
        self.assertEqual(result.publisher, "Moodle")
        self.assertEqual(result.source_url, "https://example.invalid/assignments/1")
        self.assertEqual(result.deadline.isoformat(), "2026-11-30T23:59:58.123456+07:00")
        self.assertIsNone(result.training_points)
        self.assertIsNone(result.description)
        self.assertIsNone(result.start_time)
        self.assertIsNone(result.end_time)

    def test_weekly_class_retains_weekdays_and_times_without_dates(self):
        result = map_task(task(
            id=CLASS_ID, type="class", title="Lịch học", source_platform="Portal",
            start_time={"day": "T2", "time": "07:30:00"},
            end_time={"day": "T2", "time": "11:00:00"},
        ), scope="personal")
        self.assertEqual(result.key, ("personal", CLASS_ID))
        self.assertEqual(result.type, "class")
        self.assertEqual(result.publisher, "Portal")
        self.assertEqual(result.source_url, "https://example.invalid/notices/1")
        self.assertEqual(result.start_time.day, "T2")
        self.assertEqual(result.start_time.time, time(7, 30))
        self.assertEqual(result.end_time.day, "T2")
        self.assertEqual(result.end_time.time, time(11))
        self.assertIsNone(result.start_time.date)
        self.assertIsNone(result.end_time.date)
        self.assertIsNone(result.deadline)

    def test_undated_announcement_retains_stored_type_and_optional_values(self):
        result = map_task(task(id=NOTICE_ID), scope="public")
        self.assertEqual(result.key, ("public", NOTICE_ID))
        self.assertEqual(result.type, "announcement")
        self.assertEqual(result.title, "Sinh hoạt sinh viên")
        self.assertEqual(result.publisher, "Khoa Công nghệ thông tin")
        self.assertEqual(result.source_url, "https://example.invalid/notices/1")
        for field in ("description", "course", "training_points", "deadline", "start_time", "end_time"):
            with self.subTest(field=field):
                self.assertIsNone(getattr(result, field))

    def test_same_uuid_in_two_repository_scopes_remains_addressable(self):
        public = map_task(task(title="Public notice", user_id="fictional-owner"), scope="public")
        personal = map_task(task(title="Personal notice"), scope="personal")
        index = {record.key: record for record in (public, personal)}
        self.assertEqual(len(index), 2)
        self.assertIs(index[("public", SHARED_ID)], public)
        self.assertIs(index[("personal", SHARED_ID)], personal)
        self.assertEqual(index[("public", SHARED_ID)].title, "Public notice")
        self.assertEqual(index[("personal", SHARED_ID)].title, "Personal notice")

    def test_rejects_unpersisted_task_and_unknown_scope(self):
        for task_id in (None, "", "not-a-uuid"):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                map_task(task(id=task_id), scope="public")
        with self.assertRaises(ValueError):
            map_task(task(), scope="private")
        with self.assertRaises(TypeError):
            map_task({}, scope="public")


if __name__ == "__main__":
    unittest.main()
