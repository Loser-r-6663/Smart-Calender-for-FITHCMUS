from datetime import datetime, timezone
import requests

from Backend.Regulation.BaseTask import DateDayTime
from Backend.Regulation.ExtractedTask import ExtractedTask
from Database.Repository.base import BaseSupabaseClient


class TaskRepository(BaseSupabaseClient):
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/tasks"

    @staticmethod
    def serialize_time(value: DateDayTime | None, prefix: str):
        if value is None:
            return {
                f"{prefix}_at": None,
                f"{prefix}_weekly_day": None,
                f"{prefix}_weekly_time": None,
            }
        if value.date is not None:
            timestamp = datetime.combine(
                value.date,
                value.time or datetime.min.time(),
                tzinfo=timezone.utc,
            )
            return {
                f"{prefix}_at": timestamp.isoformat(),
                f"{prefix}_weekly_day": None,
                f"{prefix}_weekly_time": None,
            }
        return {
            f"{prefix}_at": None,
            f"{prefix}_weekly_day": value.day,
            f"{prefix}_weekly_time": value.time.isoformat() if value.time is not None else None,
        }

    @staticmethod
    def deserialize_time(row: dict, prefix: str):
        timestamp: str = row.get(f"{prefix}_at")
        if timestamp is not None:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_value = None if parsed.time() == datetime.min.time() else parsed.time()
            return DateDayTime(date=parsed.date(), time=time_value)

        weekly_day = row.get(f"{prefix}_weekly_day")
        weekly_time = row.get(f"{prefix}_weekly_time")
        if weekly_day is not None or weekly_time is not None:
            return DateDayTime(day=weekly_day, time=weekly_time)
        return None

    @classmethod
    def task_to_row(cls, task: ExtractedTask) -> dict:
        if not isinstance(task, ExtractedTask):
            raise TypeError("task must be an instance of ExtractedTask")

        target_audience = task.target_audience
        location = task.location
        row = {
            "title": task.title,
            "type": task.type,
            "course": task.course,
            "description": task.description,
            "target_audience_year": (
                target_audience.year if target_audience else None
            ),
            "target_audience_program": (
                target_audience.program if target_audience else None
            ),
            "target_audience_faculty": (
                target_audience.faculty if target_audience else None
            ),
            "target_audience_other": (
                target_audience.other if target_audience else None
            ),
            "location_room": location.room if location else None,
            "location_campus": location.campus if location else None,
            "location_detail": location.detail if location else None,
            "registration_start": (
                task.registration_start.isoformat()
                if task.registration_start else None
            ),
            "registration_end": (
                task.registration_end.isoformat()
                if task.registration_end else None
            ),
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "training_points": task.training_points,
            "training_point_category": task.training_point_category,
            "estimated_hours": task.estimated_hours,
            "source_url": task.source_url,
            "source_platform": task.source_platform,
            "updated_at": task.updated_at.isoformat(),
        }
        row.update(cls.serialize_time(task.start_time, "start"))
        row.update(cls.serialize_time(task.end_time, "end"))
        return row

    @classmethod
    def row_to_task(cls, row: dict) -> ExtractedTask:
        target_audience = {
            "year": row.get("target_audience_year"),
            "program": row.get("target_audience_program"),
            "faculty": row.get("target_audience_faculty"),
            "other": row.get("target_audience_other"),
        }
        location = {
            "room": row.get("location_room"),
            "campus": row.get("location_campus"),
            "detail": row.get("location_detail"),
        }

        return ExtractedTask.model_validate({
            **row,
            "target_audience": (
                target_audience
                if any(value is not None for value in target_audience.values())
                else None
            ),
            "location": (
                location
                if any(value is not None for value in location.values())
                else None
            ),
            "start_time": cls.deserialize_time(row, "start"),
            "end_time": cls.deserialize_time(row, "end"),
        })

    def save_tasks(self, tasks: list[ExtractedTask]):
        rows = [self.task_to_row(task) for task in tasks]
        if not rows:
            return []

        response = requests.post(
            self.table_url,
            headers=self.headers,
            json=rows,
            timeout=30,
        )
        self._raise(response)
        return response

    def delete_tasks(self, tasks: list[ExtractedTask]):
        ids = [task.id for task in tasks if task.id is not None]
        if not ids:
            return

        response = requests.delete(
            self.table_url,
            params={"id": f"in.({','.join(ids)})"},
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return response

    def get_tasks(self, limit: int = 100) -> list[ExtractedTask]:
        response = requests.get(
            self.table_url,
            params={
                "select": "*",
                "limit": limit,
            },
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return [self.row_to_task(row) for row in response.json()]

    def update_task(self, task_id: str, data: ExtractedTask | dict):
        if isinstance(data, ExtractedTask):
            payload = self.task_to_row(data)
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            raise TypeError("update_task needs an ExtractedTask or a dict as the second argument")

        response = requests.patch(
            self.table_url,
            params={"id": f"eq.{task_id}"},
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        self._raise(response)
        return response
