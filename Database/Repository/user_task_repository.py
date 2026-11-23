from datetime import datetime, timezone
import requests

from DataProcessor.Standardization.BaseTask import DateDayTime
from DataProcessor.Standardization.ExtractedTask import ExtractedTask
from Database.Repository.task_repository import TaskRepository


_DIEU_TO_ARTICLE = {
    "dieu_1": "Articles 1",
    "dieu_2": "Articles 2",
    "dieu_3": "Articles 3",
    "dieu_4": "Articles 4",
    "dieu_5": "Articles 5",
}


class UserTaskRepository(TaskRepository):
    """
    Repository for personal/user-specific tasks stored in the 'user_task' table.
    Requires user_id to associate tasks with specific users.
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
        user_id: str | None = None
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/user_task"
        self.user_id = user_id

    @classmethod
    def task_to_row(cls, task: ExtractedTask | dict, user_id: str | None = None) -> dict:
        if isinstance(task, ExtractedTask):
            row = super().task_to_row(task)
            resolved_user_id = user_id or getattr(task, "user_id", None)
        elif isinstance(task, dict):
            resolved_user_id = user_id or task.get("user_id")
            st = task.get("start_time")
            et = task.get("end_time")
            dl = task.get("deadline")
            loc_raw = task.get("location")
            loc_room = loc_raw.get("room") if isinstance(loc_raw, dict) else (str(loc_raw) if loc_raw else None)
            loc_campus = loc_raw.get("campus") if isinstance(loc_raw, dict) else None
            loc_detail = loc_raw.get("detail") if isinstance(loc_raw, dict) else None
            raw_type = str(task.get("type") or "personal").lower()
            db_type = "class" if raw_type == "personal" else raw_type
            t_pts = int(task.get("training_points") or 0)
            raw_cat = task.get("training_point_category") or task.get("drl_category")
            db_cat = None
            if db_type == "event" and t_pts > 0:
                db_cat = _DIEU_TO_ARTICLE.get(str(raw_cat or "").lower(), raw_cat or "Articles 3")
            est_h = task.get("estimated_hours")
            if db_type == "event" and (est_h is None or float(est_h) <= 0):
                est_h = 1.0
            row = {
                "title": task.get("title") or "Công việc cá nhân",
                "type": db_type,
                "course": task.get("course"),
                "description": task.get("description"),
                "location_room": loc_room,
                "location_campus": loc_campus,
                "location_detail": loc_detail,
                "deadline": dl.isoformat() if isinstance(dl, datetime) else dl,
                "training_points": t_pts if db_type == "event" else None,
                "training_point_category": db_cat,
                "estimated_hours": est_h,
                "source_url": task.get("source_url") or "manual://user",
                "source_platform": task.get("source_platform") or "Portal",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            st_ddt = DateDayTime(date=st.date(), time=st.time()) if isinstance(st, datetime) else st
            et_ddt = DateDayTime(date=et.date(), time=et.time()) if isinstance(et, datetime) else et
            row.update(cls.serialize_time(st_ddt, "start"))
            row.update(cls.serialize_time(et_ddt, "end"))
        else:
            raise TypeError("task must be an ExtractedTask or dict")

        if not resolved_user_id:
            raise ValueError("user_id is required for user_task")
        row["user_id"] = str(resolved_user_id)
        return row

    @classmethod
    def row_to_task(cls, row: dict) -> ExtractedTask:
        normalized_row = dict(row)
        if normalized_row.get("type") == "personal":
            normalized_row["type"] = "class"
        if not normalized_row.get("source_url"):
            normalized_row["source_url"] = "manual://user"
        if not normalized_row.get("source_platform"):
            normalized_row["source_platform"] = "Portal"
        if not normalized_row.get("updated_at"):
            normalized_row["updated_at"] = datetime.now(timezone.utc).isoformat()
        return super().row_to_task(normalized_row)

    def save_tasks(self, tasks: list[ExtractedTask | dict]):
        rows = [self.task_to_row(task, user_id=self.user_id) for task in tasks]
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

    def get_tasks(self, limit: int = 100) -> list[ExtractedTask]:
        params = {
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
        return [self.row_to_task(row) for row in response.json()]

    def delete_tasks(self, tasks: list[ExtractedTask]):
        ids = [task.id for task in tasks if task.id is not None]
        if not ids:
            return

        params = {"id": f"in.({','.join(ids)})"}
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.delete(
            self.table_url,
            params=params,
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return response

    def update_task(self, task_id: str, data: ExtractedTask | dict):
        if isinstance(data, ExtractedTask):
            payload = self.task_to_row(data, user_id=self.user_id)
        elif isinstance(data, dict):
            payload = dict(data)
            resolved_user_id = self.user_id or payload.get("user_id")
            if resolved_user_id is not None:
                payload["user_id"] = str(resolved_user_id)
        else:
            raise TypeError("update needs an ExtractedTask or a dict as the second argument")

        params = {"id": f"eq.{task_id}"}
        if self.user_id is not None:
            params["user_id"] = f"eq.{self.user_id}"

        response = requests.patch(
            self.table_url,
            params=params,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        self._raise(response)
        return response
