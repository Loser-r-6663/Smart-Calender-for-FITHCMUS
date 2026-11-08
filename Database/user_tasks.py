from typing import Any

from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection


class UserTaskRepository:
    def assign(
        self, db_connection: connection, user_id: int, task_id: str
    ) -> bool:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO user_tasks (user_id, task_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, task_id) DO NOTHING
                RETURNING user_id, task_id, assigned_at
                """,
                (user_id, task_id),
            )
            return cursor.fetchone() is not None

    def get_for_user(
        self, db_connection: connection, user_id: int
    ) -> list[dict[str, Any]]:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT user_id, task_id, assigned_at
                FROM user_tasks
                WHERE user_id = %s
                ORDER BY assigned_at
                """,
                (user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_for_task(
        self, db_connection: connection, task_id: str
    ) -> list[dict[str, Any]]:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT user_id, task_id, assigned_at
                FROM user_tasks
                WHERE task_id = %s
                ORDER BY assigned_at
                """,
                (task_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def unassign(
        self, db_connection: connection, user_id: int, task_id: str
    ) -> bool:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_tasks WHERE user_id = %s AND task_id = %s",
                (user_id, task_id),
            )
            return cursor.rowcount > 0
