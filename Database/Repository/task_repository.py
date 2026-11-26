from datetime import datetime, timezone
from typing import Any
import requests

from DataProcessor.Standardization.BaseTask import DateDayTime
from DataProcessor.Standardization.ExtractedTask import ExtractedTask, VN_TZ
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
                tzinfo=VN_TZ,
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
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(VN_TZ)
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
            "registration_start": ExtractedTask._to_vn_time(row.get("registration_start")),
            "registration_end": ExtractedTask._to_vn_time(row.get("registration_end")),
            "deadline": ExtractedTask._to_vn_time(row.get("deadline")),
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

    def _get_task_rows(
        self, params: dict[str, Any], limit: int | None
    ) -> list[dict]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")

        page_size = 1000
        rows: list[dict] = []
        offset = 0
        seen = set()
        while limit is None or len(rows) < limit:
            request_limit = (
                page_size
                if limit is None
                else min(page_size, limit - len(rows))
            )
            response = requests.get(
                self.table_url,
                params={
                    **params,
                    "limit": request_limit,
                    "offset": offset,
                },
                headers=self.headers,
                timeout=30,
            )
            self._raise(response)
            page = response.json()
            if not isinstance(page, list):
                raise ValueError("Task response must contain a page of rows")
            for row in page:
                if not isinstance(row, dict) or not row.get("id"):
                    raise ValueError("Task rows require an ID")
                if row["id"] in seen:
                    raise ValueError("Duplicate task UUID in paginated response")
                seen.add(row["id"])
            rows.extend(page)
            if len(page) < request_limit:
                break
            offset += len(page)
        return rows

    def get_tasks(self, limit: int | None = 100) -> list[ExtractedTask]:
        rows = self._get_task_rows(
            {"select": "*", "order": "id.asc"},
            limit,
        )
        return [self.row_to_task(row) for row in rows]

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
