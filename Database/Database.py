import os
from datetime import datetime

import requests
from dotenv import load_dotenv

from Backend.Regulation.BaseTask import DayTime
from Backend.Regulation.ExtractedTask import ExtractedTask

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


class Database():
    def __init__(self):
        self.TABLE_URL = f"{SUPABASE_URL}/rest/v1/extracted_tasks"
        self.HEADERS = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    @staticmethod
    def _serialize_time(value: datetime | DayTime | None, prefix: str):
        if isinstance(value, datetime):
            return {
                f"{prefix}_at": value.isoformat(),
                f"{prefix}_weekly_day": None,
                f"{prefix}_weekly_time": None,
            }
        if isinstance(value, DayTime):
            return {
                f"{prefix}_at": None,
                f"{prefix}_weekly_day": value.day,
                f"{prefix}_weekly_time": value.time_.isoformat(),
            }
        return {
            f"{prefix}_at": None,
            f"{prefix}_weekly_day": None,
            f"{prefix}_weekly_time": None,
        }
    
    @staticmethod
    def _deserialize_time(row: dict, prefix: str):
        timestamp = row.get(f"{prefix}_at")
        if timestamp is not None:
            return timestamp
        
        weekly_day = row.get(f"{prefix}_weekly_day")
        weekly_time = row.get(f"{prefix}_weekly_time")
        if weekly_day is not None or weekly_time is not None:
            return DayTime(day=weekly_day, time_=weekly_time)
        return None
    
    @classmethod
    def _task_to_row(cls, task: ExtractedTask):
        if not isinstance(task, ExtractedTask):
            raise TypeError("save_tasks only receives ExtractedTask objects")
        
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
        row.update(cls._serialize_time(task.start_time, "start"))
        row.update(cls._serialize_time(task.end_time, "end"))
        return row
    
    @classmethod
    def _row_to_task(cls, row: dict) -> ExtractedTask:
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
            "start_time": cls._deserialize_time(row, "start"),
            "end_time": cls._deserialize_time(row, "end"),
        })
    
    def save_tasks(self, tasks: list[ExtractedTask]):
        rows = [self._task_to_row(task) for task in tasks]
        if not rows:
            return []
        
        response = requests.post(
            self.TABLE_URL,
            headers=self.HEADERS,
            json=rows,
            timeout=30
        )
        
        response.raise_for_status()
        return response
    
    def get_tasks(self, limit: int = 100) -> list[ExtractedTask]:
        response = requests.get(
            self.TABLE_URL,
            params={
                "select": "*",
                "limit": limit
            },
            headers=self.HEADERS,
            timeout=30
        )
        
        response.raise_for_status()
        return [self._row_to_task(row) for row in response.json()]
    
    def update_task(self, task_id: str, data: ExtractedTask | dict):
        if isinstance(data, ExtractedTask):
            payload = self._task_to_row(data)
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            raise TypeError("update_task needs an ExtractedTask or a dict as the second argument")
        
        response = requests.patch(
            self.TABLE_URL,
            params={"id": f"eq.{task_id}"},
            headers=self.HEADERS,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        return response
