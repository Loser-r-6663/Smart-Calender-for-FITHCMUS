"""Deterministic fictional rows, loaded only by explicit sample seeding."""
from datetime import datetime

from .support import adapt_task, read_fixture

OWNER = "sample_owner"
OTHER = "sample_other"
CLOCK = datetime.fromisoformat("2026-10-30T12:00:00+07:00")
WORK_DATE = "2026-10-30"


def sample_tasks():
    tasks = [adapt_task(task) for task in read_fixture("tasks")]
    personal = next(task for task in tasks if task["id"] == "personal-study")
    event = next(task for task in tasks if task["id"] == "evt-green")
    extras = [
        {**personal, "id": "sample-title-only", "title": "Tình nguyện mùa hè", "description": None},
        {**event, "id": "sample-description-only", "title": "Bản tin sinh viên",
         "description": "Tham gia tình nguyện cùng bạn bè.", "training_points": 5},
        {**event, "id": "sample-cross-field", "title": "Tình yêu cộng đồng",
         "description": "Nguyện đóng góp một ngày xanh.",
         "start_time": datetime.fromisoformat("2026-10-30T05:00:00+00:00"),
         "end_time": datetime.fromisoformat("2026-10-30T06:00:00+00:00")},
        {**personal, "id": "sample-literal", "title": "Mẫu 50%_! O'Reilly \\ ghi chú", "description": None},
        {**personal, "id": "sample-other-private", "title": "Tình nguyện riêng", "description": None},
    ]
    for task in extras:
        task.update(updated_at=CLOCK, source_url=f"https://fixtures.example.invalid/{task['id']}")
    return tasks + extras


def owner_for(task_id):
    return OTHER if task_id == "sample-other-private" else OWNER
