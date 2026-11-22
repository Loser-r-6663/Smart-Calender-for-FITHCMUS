from datetime import datetime, timezone
from typing import Any
import requests

from Database.Repository.base import BaseSupabaseClient


class UserTaskPreferenceRepository(BaseSupabaseClient):
    """
    Repository quản lý tùy chỉnh lịch của từng user (Pin / Reject / Reschedule / Travel Buffer)
    trên bảng 'user_task_preferences' của Supabase.
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
        user_id: str | None = None,
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/user_task_preferences"
        self.user_id = str(user_id) if user_id is not None else None

    @staticmethod
    def _serialize_dt(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None

    @staticmethod
    def row_to_pref(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "pin_status": str(row.get("pin_status") or "default").lower(),
            "custom_start_time": row.get("custom_start_at"),
            "custom_end_time": row.get("custom_end_at"),
            "travel_buffer_minutes": row.get("travel_buffer_minutes"),
        }

    def get_preferences(self, limit: int = 500) -> dict[str, dict[str, Any]]:
        params: dict[str, Any] = {
            "select": "*",
            "limit": limit,
        }
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.get(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        prefs: dict[str, dict[str, Any]] = {}
        for row in response.json():
            task_id = row.get("task_id")
            if task_id:
                prefs[str(task_id)] = self.row_to_pref(row)
        return prefs

    def upsert_preference(
        self,
        task_id: str,
        *,
        pin_status: str = "default",
        custom_start_time: datetime | str | None = None,
        custom_end_time: datetime | str | None = None,
        travel_buffer_minutes: int | None = None,
        user_id: str | None = None,
    ):
        resolved_user_id = str(user_id or self.user_id or "")
        if not resolved_user_id:
            raise ValueError("user_id is required for user_task_preferences")

        payload = {
            "user_id": resolved_user_id,
            "task_id": str(task_id),
            "pin_status": str(pin_status or "default").lower(),
            "custom_start_at": self._serialize_dt(custom_start_time),
            "custom_end_at": self._serialize_dt(custom_end_time),
            "travel_buffer_minutes": travel_buffer_minutes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"

        response = requests.post(
            self.table_url,
            params={"on_conflict": "user_id,task_id"},
            headers=headers,
            json=payload,
            timeout=30,
        )
        self._raise(response)
        return response

    def delete_preference(self, task_id: str, user_id: str | None = None):
        resolved_user_id = str(user_id or self.user_id or "")
        params: dict[str, Any] = {"task_id": f"eq.{task_id}"}
        if resolved_user_id:
            params["user_id"] = f"eq.{resolved_user_id}"

        response = requests.delete(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return response
