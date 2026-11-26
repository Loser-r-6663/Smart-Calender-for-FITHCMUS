from datetime import date

from Database.Repository.task_repository import TaskRepository
from client.core.controller import TaskMapper


def test_maps_exact_event() -> None:
    task = {
        "id": "event-1",
        "title": "Workshop",
        "type": "event",
        "start_time": "2026-11-23T14:00:00+07:00",
        "end_time": "2026-11-23T16:00:00+07:00",
        "source_url": "https://example.com",
    }

    items = TaskMapper.map_range(task, date(2026, 11, 1), date(2026, 11, 30))

    assert len(items) == 1
    assert items[0].day == date(2026, 11, 23)
    assert items[0].time_label == "14:00–16:00"


def test_expands_weekly_class_inside_visible_range() -> None:
    task = {
        "id": "class-1",
        "user_id": "student-1",
        "title": "Weekly class",
        "type": "class",
        "start_time": {"day": "T2", "time_": "08:00:00"},
        "end_time": {"day": "T2", "time_": "10:00:00"},
    }

    items = TaskMapper.map_range(task, date(2026, 11, 1), date(2026, 11, 30))

    assert [item.day.day for item in items] == [2, 9, 16, 23, 30]
    assert all(item.is_personal for item in items)


def test_maps_deadline_and_undated_notice() -> None:
    deadline = TaskMapper.map_range(
        {
            "id": "assignment-1",
            "title": "Submit report",
            "type": "assignment",
            "deadline": "2026-11-24T23:59:00+07:00",
        },
        date(2026, 11, 1),
        date(2026, 11, 30),
    )[0]
    notice = TaskMapper.map_range(
        {"id": "notice-1", "title": "Notice", "type": "announcement"},
        date(2026, 11, 1),
        date(2026, 11, 30),
    )[0]

    assert deadline.day == date(2026, 11, 24)
    assert deadline.time_label == "Due 23:59"
    assert notice.day is None


def test_maps_exact_database_datetime_values() -> None:
    task = TaskRepository.row_to_task(
        {
            "id": "db-event",
            "title": "Database event",
            "type": "event",
            "start_at": "2026-11-23T14:00:00+07:00",
            "end_at": "2026-11-23T16:00:00+07:00",
            "training_points": 5,
            "training_point_category": "Articles 1",
            "estimated_hours": 2,
            "source_url": "https://example.com",
            "source_platform": "Portal",
            "updated_at": "2026-11-23T12:00:00+07:00",
        }
    )

    items = TaskMapper.map_range(task, date(2026, 11, 1), date(2026, 11, 30))

    assert len(items) == 1
    assert items[0].day == date(2026, 11, 23)
    assert items[0].time_label == "14:00–16:00"


def test_expands_weekly_database_datetime_values() -> None:
    task = TaskRepository.row_to_task(
        {
            "id": "db-class",
            "title": "Database weekly class",
            "type": "class",
            "start_weekly_day": "T2",
            "start_weekly_time": "08:00:00",
            "end_weekly_day": "T2",
            "end_weekly_time": "10:00:00",
            "source_url": "https://example.com",
            "source_platform": "Portal",
            "updated_at": "2026-11-23T12:00:00+07:00",
        }
    )

    items = TaskMapper.map_range(task, date(2026, 11, 1), date(2026, 11, 30))

    assert [item.day.day for item in items] == [2, 9, 16, 23, 30]
    assert all(item.time_label == "08:00–10:00" for item in items)
