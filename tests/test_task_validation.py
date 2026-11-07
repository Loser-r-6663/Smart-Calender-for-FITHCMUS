import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.api import TaskUpdate
from Database.objects import DailyTaskObject, TaskObject, UserObject, UserTaskObject
from Database.task_config import TASK_DEFAULTS, TASK_FIELDS, TASK_REQUIRED_FIELDS
from Database.tasks import TaskRepository
from Database.validation import TaskData, validate_task_data
from Database.user_validation import UserData


class TaskValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_task = {
            "id": "task-001",
            "title": "Database homework",
            "type": "assignment",
            "deadline": "2026-11-10T23:59:00+07:00",
        }

    def test_defaults_are_applied_from_task_config(self) -> None:
        validated = validate_task_data(self.valid_task)

        self.assertEqual(TASK_REQUIRED_FIELDS, {"id", "title", "type"})
        self.assertTrue(TASK_DEFAULTS.keys() <= validated.keys())
        self.assertEqual(TASK_FIELDS, validated.keys())
        self.assertEqual(validated["status"], "active")
        self.assertEqual(validated["source_platform"], "custom")
        self.assertIsNone(validated["course"])
        self.assertNotIn("embedding", validated)

    def test_course_and_optional_fields_are_normalized(self) -> None:
        validated = validate_task_data(
            {
                **self.valid_task,
                "course": "  Computer Science  ",
                "location": "  Campus  ",
                "recurrence": "WEEKLY:MON,FRI",
                "source_url": "https://example.edu/tasks/1",
            }
        )

        self.assertEqual(validated["course"], "Computer Science")
        self.assertEqual(validated["location"], "Campus")
        self.assertEqual(validated["source_url"], "https://example.edu/tasks/1")

    def test_text_fields_accept_values_longer_than_100_characters(self) -> None:
        long_text = "x" * 150
        task = TaskData.model_validate(
            {
                **self.valid_task,
                "course": long_text,
                "target_audience": long_text,
                "location": long_text,
            }
        )
        user = UserData.model_validate(
            {
                "username": "student",
                "email": f"{'a' * 110}@example.edu",
                "full_name": long_text,
            }
        )
        task_update = TaskUpdate.model_validate(
            {
                "course": long_text,
                "target_audience": long_text,
                "location": long_text,
            }
        )

        self.assertEqual(task.course, long_text)
        self.assertEqual(task.target_audience, long_text)
        self.assertEqual(task.location, long_text)
        self.assertEqual(user.full_name, long_text)
        self.assertEqual(len(user.email), 122)
        self.assertEqual(task_update.course, long_text)

    def test_rejects_removed_or_unknown_fields(self) -> None:
        for field in ("course_code", "embedding", "unexpected"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    TaskData.model_validate({**self.valid_task, field: "value"})

    def test_repository_rejects_invalid_data_before_database_write(self) -> None:
        with self.assertRaises(ValidationError):
            TaskRepository().create(
                None,
                {
                    "id": "task-004",
                    "title": "Bad URL",
                    "type": "personal",
                    "source_url": "not-a-url",
                },
            )

    def test_rejects_invalid_formats_and_ranges(self) -> None:
        invalid_values = (
            {"course": "   "},
            {"location": "   "},
            {"source_url": "not-a-url"},
            {"recurrence": "WEEKLY:MON,MON"},
            {"recurrence": "WEEKLY:FUNDAY"},
            {"registration_start": "2026-11-01T10:00:00"},
            {"registration_start": 1793523600},
            {"estimated_hours": float("inf")},
            {"estimated_hours": 0.0},
            {"training_points": 101},
            {"is_manual": "true"},
            {"type": "unknown"},
            {"id": "   "},
            {"title": "   "},
        )
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    TaskData.model_validate({**self.valid_task, **invalid_value})

    def test_rejects_invalid_time_ranges(self) -> None:
        invalid_ranges = (
            {
                "registration_start": "2026-11-02T10:00:00+07:00",
                "registration_end": "2026-11-02T10:00:00+07:00",
            },
            {
                "start_time": "2026-11-02T12:00:00+07:00",
                "end_time": "2026-11-02T11:00:00+07:00",
            },
        )
        for invalid_range in invalid_ranges:
            with self.subTest(invalid_range=invalid_range):
                with self.assertRaises(ValidationError):
                    TaskData.model_validate({**self.valid_task, **invalid_range})

    def test_assignment_requires_deadline_and_defaults_drl_category(self) -> None:
        with self.assertRaises(ValidationError):
            TaskData.model_validate(
                {"id": "task-002", "title": "Homework", "type": "assignment"}
            )
        with self.assertRaises(ValidationError):
            TaskData.model_validate(
                {"id": "task-003", "title": "Tuition", "type": "tuition"}
            )

        validated = TaskData.model_validate(
            {
                "id": "event-001",
                "title": "Volunteer event",
                "type": "event",
                "training_points": 5,
            }
        )
        self.assertEqual(validated.drl_category, "dieu_3")

    def test_preserves_explicit_drl_category(self) -> None:
        validated = TaskData.model_validate(
            {
                "id": "event-002",
                "title": "Volunteer event",
                "type": "event",
                "training_points": 5,
                "drl_category": "dieu_2",
            }
        )

        self.assertEqual(validated.drl_category, "dieu_2")


class DatabaseObjectTests(unittest.TestCase):
    def test_get_records_convert_to_typed_objects(self) -> None:
        task_record = {
            **validate_task_data(
                {
                    "id": "task-003",
                    "title": "Read task",
                    "type": "personal",
                }
            ),
            "updated_at": datetime.now(timezone.utc),
        }
        task = TaskObject.from_record(task_record)
        daily_task = DailyTaskObject.from_record(
            {
                **task_record,
                "work_date": date(2026, 11, 7),
                "is_completed_today": False,
            }
        )
        user = UserObject.from_record(
            {"id": 1, "username": "student", "email": "student@example.edu"}
        )
        assignment = UserTaskObject.from_record(
            {
                "user_id": 1,
                "task_id": "task-003",
                "assigned_at": datetime.now(timezone.utc),
            }
        )

        self.assertIsInstance(task, TaskObject)
        self.assertIsInstance(daily_task, DailyTaskObject)
        self.assertIsInstance(user, UserObject)
        self.assertIsInstance(assignment, UserTaskObject)
        self.assertEqual(daily_task.work_date, date(2026, 11, 7))


class TaskPatchValidationTests(unittest.TestCase):
    def test_patch_rejects_coerced_numeric_and_boolean_values(self) -> None:
        for invalid_value in (
            {"is_manual": "true"},
            {"training_points": True},
            {"estimated_hours": True},
            {"deadline": 1793523600},
        ):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    TaskUpdate.model_validate(invalid_value)


if __name__ == "__main__":
    unittest.main()
