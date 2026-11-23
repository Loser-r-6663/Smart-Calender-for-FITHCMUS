from datetime import datetime, timezone
from typing import Any
import requests

from DataProcessor.Standardization.UserTaskPreference import UserTaskPreference
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

    @classmethod
    def row_to_model(cls, row: dict[str, Any]) -> UserTaskPreference:
        return UserTaskPreference.model_validate(row)

    @classmethod
    def model_to_row(cls, pref: UserTaskPreference, user_id: str | None = None) -> dict[str, Any]:
        resolved_user_id = str(user_id or pref.user_id or "")
        if not resolved_user_id:
            raise ValueError("user_id is required for user_task_preferences")
        return {
            "user_id": resolved_user_id,
            "task_id": str(pref.task_id),
            "pin_status": str(pref.pin_status or "default").lower(),
            "custom_start_at": cls._serialize_dt(pref.custom_start_time),
            "custom_end_at": cls._serialize_dt(pref.custom_end_time),
            "travel_buffer_minutes": pref.travel_buffer_minutes,
            "is_scheduled": bool(pref.is_scheduled),
            "scheduled_start_at": cls._serialize_dt(pref.scheduled_start_time),
            "scheduled_end_at": cls._serialize_dt(pref.scheduled_end_time),
            "points_gained": pref.points_gained,
            "updated_at": cls._serialize_dt(pref.updated_at) or datetime.now(timezone.utc).isoformat(),
        }

    def get_preference_models(self, limit: int = 500) -> list[UserTaskPreference]:
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
        return [self.row_to_model(row) for row in response.json()]

    @staticmethod
    def row_to_pref(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "pin_status": str(row.get("pin_status") or "default").lower(),
            "custom_start_time": row.get("custom_start_at"),
            "custom_end_time": row.get("custom_end_at"),
            "travel_buffer_minutes": row.get("travel_buffer_minutes"),
            "is_scheduled": bool(row.get("is_scheduled", False)),
            "scheduled_start_time": row.get("scheduled_start_at"),
            "scheduled_end_time": row.get("scheduled_end_at"),
            "points_gained": row.get("points_gained"),
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
        travel_buffer_minutes: int | dict[str, int] | None = None,
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

    @classmethod
    def build_schedule_outcome_rows(
        cls,
        selected_events: list[Any],
        *,
        user_id: str,
        existing_prefs: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Tạo danh sách payload để lưu kết quả các sự kiện được Scheduler chọn vào
        bảng 'user_task_preferences' mà vẫn giữ nguyên ý định của user (pin_status, custom_start/end).
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = existing_prefs or {}
        selected_ids: set[str] = set()
        rows: list[dict[str, Any]] = []

        for ev in selected_events:
            task_id = str(getattr(ev, "task_id", None) or (ev.get("task_id") if isinstance(ev, dict) else "") or "")
            if not task_id:
                continue
            selected_ids.add(task_id)
            prev = existing.get(task_id, {})
            st = getattr(ev, "start_time", None) if not isinstance(ev, dict) else ev.get("start_time")
            et = getattr(ev, "end_time", None) if not isinstance(ev, dict) else ev.get("end_time")
            pts = getattr(ev, "points_gained", None) if not isinstance(ev, dict) else ev.get("points_gained")
            rows.append({
                "user_id": str(user_id),
                "task_id": task_id,
                "pin_status": str(prev.get("pin_status") or "default").lower(),
                "custom_start_at": cls._serialize_dt(prev.get("custom_start_time")),
                "custom_end_at": cls._serialize_dt(prev.get("custom_end_time")),
                "travel_buffer_minutes": prev.get("travel_buffer_minutes"),
                "is_scheduled": True,
                "scheduled_start_at": cls._serialize_dt(st),
                "scheduled_end_at": cls._serialize_dt(et),
                "points_gained": int(pts) if pts is not None else None,
                "updated_at": now_iso,
            })

        # Bỏ đánh dấu is_scheduled cho những sự kiện cũ không còn trong lịch mới
        for task_id, prev in existing.items():
            if task_id not in selected_ids and prev.get("is_scheduled"):
                rows.append({
                    "user_id": str(user_id),
                    "task_id": str(task_id),
                    "pin_status": str(prev.get("pin_status") or "default").lower(),
                    "custom_start_at": cls._serialize_dt(prev.get("custom_start_time")),
                    "custom_end_at": cls._serialize_dt(prev.get("custom_end_time")),
                    "travel_buffer_minutes": prev.get("travel_buffer_minutes"),
                    "is_scheduled": False,
                    "scheduled_start_at": None,
                    "scheduled_end_at": None,
                    "points_gained": None,
                    "updated_at": now_iso,
                })

        return rows

    def save_schedule_outcome(
        self,
        selected_events: list[Any],
        *,
        user_id: str | None = None,
        existing_prefs: dict[str, dict[str, Any]] | None = None,
    ):
        resolved_user_id = str(user_id or self.user_id or "")
        if not resolved_user_id:
            raise ValueError("user_id is required for user_task_preferences")

        if existing_prefs is None:
            existing_prefs = self.get_preferences()

        rows = self.build_schedule_outcome_rows(
            selected_events,
            user_id=resolved_user_id,
            existing_prefs=existing_prefs,
        )
        if not rows:
            return []

        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        response = requests.post(
            self.table_url,
            params={"on_conflict": "user_id,task_id"},
            headers=headers,
            json=rows,
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
