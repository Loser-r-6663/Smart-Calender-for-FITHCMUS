import os
import base64
import hashlib
import hmac
import secrets
from datetime import datetime

import requests
from dotenv import load_dotenv
from cryptography.fernet import Fernet

from Backend.Regulation.BaseTask import DayTime
from Backend.Regulation.ExtractedTask import ExtractedTask
from Backend.Regulation.User import User

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_ENCRYPTION_KEY = os.getenv("SUPABASE_ENCRYPTION_KEY")


class Database():
    def __init__(self):
        self.TASKS_TABLE_URL = f"{SUPABASE_URL}/rest/v1/tasks"
        self.USERS_TABLE_URL = f"{SUPABASE_URL}/rest/v1/users"
        self.HEADERS = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    @staticmethod
    def _get_fernet() -> Fernet:
        key = SUPABASE_ENCRYPTION_KEY or os.getenv("SUPABASE_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "SUPABASE_ENCRYPTION_KEY must be configured to handle "
                "encrypted user credentials"
            )
        return Fernet(key.encode("ascii"))

    @classmethod
    def _encrypt(cls, value: str | None):
        if value is None: return
        return cls._get_fernet().encrypt(value.encode("utf-8")).decode("ascii")

    @classmethod
    def _decrypt(cls, value: str | None):
        if value is None: return
        return cls._get_fernet().decrypt(value.encode("ascii")).decode("utf-8")

    @staticmethod
    def _hash_password(password: str):
        if not password:
            raise ValueError("password must not be empty")

        salt = secrets.token_bytes(16)
        password_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )
        encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
        return f"scrypt$16384$8$1${encode(salt)}${encode(password_hash)}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            algorithm, n, r, p, encoded_salt, encoded_hash = stored_hash.split("$")
            if algorithm != "scrypt":
                return False
            salt = base64.urlsafe_b64decode(encoded_salt)
            expected_hash = base64.urlsafe_b64decode(encoded_hash)
            actual_hash = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual_hash, expected_hash)

    @classmethod
    def _user_to_row(cls, user: User) -> dict:
        if not isinstance(user, User):
            raise TypeError("user must be an instance of User")

        if not user.username:
            raise ValueError("username must not be empty")

        if user.password:
            password_hash = cls._hash_password(user.password)
        elif user.password_hash:
            password_hash = user.password_hash
        else:
            raise ValueError("password must not be empty")

        return {
            "username": user.username,
            "password_hash": password_hash,
            "portal_username": cls._encrypt(user.portal_username),
            "portal_password": cls._encrypt(user.portal_password),
            "moodle_session": cls._encrypt(user.moodle_session),
            "moodle_status": bool(user.moodle_status),
            "portal_session": cls._encrypt(user.portal_session),
            "portal_status": bool(user.portal_status),
        }

    @classmethod
    def _row_to_user(cls, row: dict, include_password_hash: bool = False) -> User:
        user_data = {
            "id": row.get("id"),
            "username": row.get("username"),
            "portal_username": cls._decrypt(row.get("portal_username")),
            "portal_password": cls._decrypt(row.get("portal_password")),
            "moodle_session": cls._decrypt(row.get("moodle_session")),
            "moodle_status": bool(row.get("moodle_status", False)),
            "portal_session": cls._decrypt(row.get("portal_session")),
            "portal_status": bool(row.get("portal_status", False)),
        }
        if include_password_hash and "password_hash" in row:
            user_data["password_hash"] = row["password_hash"]
        return User.model_validate(user_data)
    
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
            self.TASKS_TABLE_URL,
            headers=self.HEADERS,
            json=rows,
            timeout=30
        )
        
        response.raise_for_status()
        return response
    
    def delete_tasks(self, tasks: list[ExtractedTask]):
        ids = [task.id for task in tasks if task.id is not None]
        if not ids: return
        
        response = requests.delete(
            self.TASKS_TABLE_URL,
            params={"id": f"in.({','.join(ids)})"},
            headers=self.HEADERS,
            timeout=30
        )
        
        response.raise_for_status()
        return response
    
    def get_tasks(self, limit: int = 100) -> list[ExtractedTask]:
        response = requests.get(
            self.TASKS_TABLE_URL,
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
            self.TASKS_TABLE_URL,
            params={"id": f"eq.{task_id}"},
            headers=self.HEADERS,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        return response

    def save_user(self, user: User) -> User:
        if not isinstance(user, User):
            raise TypeError("save_user requires a User")

        response = requests.post(
            self.USERS_TABLE_URL,
            headers=self.HEADERS,
            json=self._user_to_row(user),
            timeout=30
        )
        response.raise_for_status()
        return self._row_to_user(response.json()[0])

    def get_user(self, username: str, password: str | None = None):
        response = requests.get(
            self.USERS_TABLE_URL,
            params={
                "select": (
                    "id,username,password_hash,portal_username,"
                    "portal_password,moodle_session,moodle_status,"
                    "portal_session,portal_status"
                ),
                "username": f"eq.{username}",
                "limit": 1
            },
            headers=self.HEADERS,
            timeout=30
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None

        row = rows[0]
        if password is not None and not self._verify_password(
            password, row["password_hash"]
        ):
            return None
        return self._row_to_user(row)

    def get_users(self, page_size: int = 1000):
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")

        select = (
            "id,username,portal_username,portal_password,"
            "moodle_session,moodle_status,portal_session,portal_status"
        )
        users: list[User] = []
        offset = 0

        while True:
            response = requests.get(
                self.USERS_TABLE_URL,
                params={
                    "select": select,
                    "limit": page_size,
                    "offset": offset,
                    "order": "id.asc",
                },
                headers=self.HEADERS,
                timeout=30
            )
            response.raise_for_status()
            rows = response.json()
            users.extend(self._row_to_user(row) for row in rows)

            if len(rows) < page_size:
                return users
            offset += page_size

    def update_user(self, user_or_id: str | User, data: User | dict | None = None):
        if isinstance(user_or_id, User):
            id = user_or_id.id
            if not id:
                raise ValueError("id must not be empty when passing a User object as first argument")
            update_data = data if data is not None else user_or_id
        elif isinstance(user_or_id, str):
            id = user_or_id
            if data is None:
                raise ValueError("data must be provided when id is a string")
            update_data = data
        else:
            raise TypeError("First argument must be a id (str) or a User object")

        if isinstance(update_data, User):
            payload = {}
            if update_data.username is not None:
                payload["username"] = update_data.username
            if update_data.password:
                payload["password_hash"] = self._hash_password(update_data.password)
            elif update_data.password_hash:
                payload["password_hash"] = update_data.password_hash
            if update_data.portal_username is not None:
                payload["portal_username"] = self._encrypt(update_data.portal_username)
            if update_data.portal_password is not None:
                payload["portal_password"] = self._encrypt(update_data.portal_password)
            if update_data.moodle_session is not None:
                payload["moodle_session"] = self._encrypt(update_data.moodle_session)
            payload["moodle_status"] = bool(update_data.moodle_status)
            if update_data.portal_session is not None:
                payload["portal_session"] = self._encrypt(update_data.portal_session)
            payload["portal_status"] = bool(update_data.portal_status)
        elif isinstance(update_data, dict):
            payload = dict(update_data)
            if "password" in payload:
                payload["password_hash"] = self._hash_password(payload.pop("password"))

            for field in (
                "portal_username",
                "portal_password",
                "moodle_session",
                "portal_session",
            ):
                if field in payload:
                    payload[field] = self._encrypt(payload[field])
        else:
            raise TypeError("update_user data needs a User or a dict")

        response = requests.patch(
            self.USERS_TABLE_URL,
            params={"id": f"eq.{id}"},
            headers=self.HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return self._row_to_user(response.json()[0])

    def delete_user(self, user: User | str):
        id = user.id if isinstance(user, User) else user
        if not id:
            raise ValueError("id must not be empty")

        response = requests.delete(
            self.USERS_TABLE_URL,
            params={"id": f"eq.{id}"},
            headers=self.HEADERS,
            timeout=30
        )
        response.raise_for_status()
        return response

    def delete_users(self, users: list[User]):
        ids = [user.id for user in users if user.id is not None]
        if not ids:
            return

        response = requests.delete(
            self.USERS_TABLE_URL,
            params={"id": f"in.({','.join(ids)})"},
            headers=self.HEADERS,
            timeout=30
        )
        response.raise_for_status()
        return response
