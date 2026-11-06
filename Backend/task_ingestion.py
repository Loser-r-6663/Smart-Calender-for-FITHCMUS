"""Prepare parser candidates for the database validation boundary."""

import json
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from Database.validation import validate_task_data
from Parser.models import TaskCandidate


def prepare_task_for_database(
    candidate: TaskCandidate,
    *,
    id_factory: Callable[[], str] = lambda: uuid4().hex,
) -> dict[str, Any]:
    """Convert a task candidate into the database validator's input shape."""

    data = {
        "title": candidate.title,
        "type": candidate.type,
        "course_code": candidate.course_code,
        "description": candidate.description,
        "target_audience": candidate.target_audience,
        "location": candidate.location,
        "registration_start": candidate.registration_start,
        "registration_end": candidate.registration_end,
        "start_time": candidate.start_time,
        "end_time": candidate.end_time,
        "deadline": candidate.deadline,
        "estimated_hours": candidate.estimated_hours,
        "training_points": candidate.training_points,
        "drl_category": candidate.drl_category,
        "recurrence": candidate.recurrence,
        "status": candidate.status,
        "is_manual": candidate.is_manual,
        "source_url": candidate.source_url,
        "source_platform": candidate.source_platform,
        "embedding": (
            json.dumps(candidate.embedding, separators=(",", ":"))
            if candidate.embedding is not None
            else None
        ),
        "updated_at": candidate.updated_at,
        "id": candidate.id if candidate.id is not None else id_factory(),
    }
    data = {
        key: value.value if isinstance(value, Enum) else value
        for key, value in data.items()
        if value is not None
    }
    return validate_task_data(data)
