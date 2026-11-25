import requests

from DataProcessor.Standardization.User import User
from Database.Repository.base import BaseSupabaseClient
from Database import crypto


class UserRepository(BaseSupabaseClient):
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        access_token: str | None = None,
    ):
        super().__init__(supabase_url, supabase_key, access_token)
        self.table_url = f"{self.supabase_url}/rest/v1/users"

    @classmethod
    def user_to_row(cls, user: User) -> dict:
        if not isinstance(user, User):
            raise TypeError("user must be an instance of User")

        if not user.username:
            raise ValueError("username must not be empty")
        if not user.id:
            raise ValueError("id (auth_id) must not be empty")

        return {
            "id": user.id,
            "username": user.username,
            "portal_username": crypto.encrypt(user.portal_username),
            "portal_password": crypto.encrypt(user.portal_password),
            "moodle_session": crypto.encrypt(user.moodle_session),
            "moodle_status": bool(user.moodle_status),
            "portal_session": crypto.encrypt(user.portal_session),
            "portal_status": bool(user.portal_status),
            "training_points": user.training_points,
        }

    @classmethod
    def row_to_user(cls, row: dict) -> User:
        user_data = {
            "id": row.get("id"),
            "username": row.get("username"),
            "portal_username": crypto.decrypt(row.get("portal_username")),
            "portal_password": crypto.decrypt(row.get("portal_password")),
            "moodle_session": crypto.decrypt(row.get("moodle_session")),
            "moodle_status": bool(row.get("moodle_status", False)),
            "portal_session": crypto.decrypt(row.get("portal_session")),
            "portal_status": bool(row.get("portal_status", False)),
            "training_points": row.get("training_points", {}),
        }
        return User.model_validate(user_data)

    def save_user(self, user: User) -> User:
        if not isinstance(user, User):
            raise TypeError("save_user requires a User")

        response = requests.post(
            self.table_url,
            headers=self.headers,
            json=self.user_to_row(user),
            timeout=30,
        )
        self._raise(response)
        return self.row_to_user(response.json()[0])

    def get_user(self, user_id: str) -> User | None:
        response = requests.get(
            self.table_url,
            params={
                "select": "*",
                "id": f"eq.{user_id}",
                "limit": 1,
            },
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        rows = response.json()
        return self.row_to_user(rows[0]) if rows else None

    def get_all_users(self, page_size: int = 100) -> list[User]:
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")

        users: list[User] = []
        offset = 0

        while True:
            response = requests.get(
                self.table_url,
                params={
                    "select": "*",
                    "limit": page_size,
                    "offset": offset,
                    "order": "id.asc",
                },
                headers=self.headers,
                timeout=30,
            )
            self._raise(response)
            rows = response.json()
            users.extend(self.row_to_user(row) for row in rows)

            if len(rows) < page_size:
                return users
            offset += page_size

    def update_user(self, user_or_id: str | User, data: User | dict | None = None) -> User:
        if isinstance(user_or_id, User):
            id_ = user_or_id.id
            if not id_:
                raise ValueError("id must not be empty when passing a User object as first argument")
            update_data = data if data is not None else user_or_id
        elif isinstance(user_or_id, str):
            id_ = user_or_id
            if data is None:
                raise ValueError("data must be provided when id is a string")
            update_data = data
        else:
            raise TypeError("First argument must be a id (str) or a User object")

        if isinstance(update_data, User):
            payload = {}
            if update_data.username is not None:
                payload["username"] = update_data.username
            if update_data.portal_username is not None:
                payload["portal_username"] = crypto.encrypt(update_data.portal_username)
            if update_data.portal_password is not None:
                payload["portal_password"] = crypto.encrypt(update_data.portal_password)
            if update_data.moodle_session is not None:
                payload["moodle_session"] = crypto.encrypt(update_data.moodle_session)
            payload["moodle_status"] = bool(update_data.moodle_status)
            if update_data.portal_session is not None:
                payload["portal_session"] = crypto.encrypt(update_data.portal_session)
            payload["portal_status"] = bool(update_data.portal_status)
            payload["training_points"] = update_data.training_points
        elif isinstance(update_data, dict):
            payload = dict(update_data)

            for field in (
                "portal_username",
                "portal_password",
                "moodle_session",
                "portal_session",
            ):
                if field in payload:
                    payload[field] = crypto.encrypt(payload[field])
        else:
            raise TypeError("update_user data needs a User or a dict")

        response = requests.patch(
            self.table_url,
            params={"id": f"eq.{id_}"},
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        self._raise(response)
        return self.row_to_user(response.json()[0])

    def delete_user(self, user: User | str):
        id_ = user.id if isinstance(user, User) else user
        if not id_:
            raise ValueError("id must not be empty")

        response = requests.delete(
            self.table_url,
            params={"id": f"eq.{id_}"},
            headers=self.headers,
            timeout=30,
        )
        self._raise(response)
        return response

    def delete_many_users(self, users: list[User]):
        ids = [user.id for user in users if user.id is not None]
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
