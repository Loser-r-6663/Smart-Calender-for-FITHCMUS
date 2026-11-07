from datetime import datetime, timezone


TASK_REQUIRED_FIELDS = frozenset({"id", "title", "type"})

TASK_DEFAULTS = {
    "course": None,
    "description": None,
    "target_audience": None,
    "location": None,
    "registration_start": None,
    "registration_end": None,
    "start_time": None,
    "end_time": None,
    "deadline": None,
    "estimated_hours": None,
    "training_points": 0,
    "drl_category": None,
    "recurrence": None,
    "status": "active",
    "is_manual": False,
    "source_url": None,
    "source_platform": "custom",
}

TASK_FIELDS = TASK_REQUIRED_FIELDS | TASK_DEFAULTS.keys() | {"updated_at"}


def current_task_timestamp() -> datetime:
    return datetime.now(timezone.utc)
