from collections.abc import Mapping
from typing import Any

from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection

from Database.validation import UserData, validate_user_data


class UserRepository:
    def create(
        self,
        db_connection: connection,
        username: str,
        email: str,
        full_name: str | None = None,
    ) -> dict[str, Any]:
        user_data = validate_user_data(
            {"username": username, "email": email, "full_name": full_name}
        )
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, email, full_name)
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (
                    user_data["username"],
                    user_data["email"],
                    user_data["full_name"],
                ),
            )
            return dict(cursor.fetchone())

    def get_by_id(
        self, db_connection: connection, user_id: int
    ) -> dict[str, Any] | None:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def update(
        self,
        db_connection: connection,
        user_id: int,
        updates: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        allowed_columns = {"username", "email", "full_name"}
        invalid_columns = set(updates) - allowed_columns
        if invalid_columns:
            raise ValueError(
                "Unsupported user fields: " + ", ".join(sorted(invalid_columns))
            )
        if not updates:
            return self.get_by_id(db_connection, user_id)

        existing_user = self.get_by_id(db_connection, user_id)
        if existing_user is None:
            return None
        current_data = {
            field: existing_user[field] for field in ("username", "email", "full_name")
        }
        validated_user = UserData.model_validate({**current_data, **updates})
        updates = {column: getattr(validated_user, column) for column in updates}

        assignments = ", ".join(f"{column} = %s" for column in updates)
        values = tuple(updates.values()) + (user_id,)
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"UPDATE users SET {assignments} WHERE id = %s RETURNING *",
                values,
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def delete(self, db_connection: connection, user_id: int) -> bool:
        with db_connection.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return cursor.rowcount > 0
