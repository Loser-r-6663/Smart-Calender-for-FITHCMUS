from datetime import date
from typing import Any

from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection


class DailyTaskRepository:
    def set_for_date(
        self,
        db_connection: connection,
        user_id: int,
        work_date: date,
        task_id: str,
        is_completed_today: bool = False,
    ) -> dict[str, Any]:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO daily_tasks (
                    user_id, work_date, task_id, is_completed_today
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, work_date, task_id)
                DO UPDATE SET is_completed_today = EXCLUDED.is_completed_today
                RETURNING user_id, work_date, task_id, is_completed_today
                """,
                (user_id, work_date, task_id, is_completed_today),
            )
            return dict(cursor.fetchone())

    def get_for_user_date(
        self, db_connection: connection, user_id: int, work_date: date
    ) -> list[dict[str, Any]]:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT tasks.*, daily_tasks.work_date,
                       daily_tasks.user_id,
                       daily_tasks.is_completed_today
                FROM daily_tasks
                JOIN tasks ON tasks.id = daily_tasks.task_id
                WHERE daily_tasks.user_id = %s AND daily_tasks.work_date = %s
                ORDER BY tasks.start_time NULLS LAST, tasks.deadline NULLS LAST
                """,
                (user_id, work_date),
            )
            return [dict(row) for row in cursor.fetchall()]

    def set_completion(
        self,
        db_connection: connection,
        user_id: int,
        work_date: date,
        task_id: str,
        is_completed: bool,
    ) -> dict[str, Any] | None:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE daily_tasks
                SET is_completed_today = %s
                WHERE user_id = %s AND work_date = %s AND task_id = %s
                RETURNING user_id, work_date, task_id, is_completed_today
                """,
                (is_completed, user_id, work_date, task_id),
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def remove(
        self,
        db_connection: connection,
        user_id: int,
        work_date: date,
        task_id: str,
    ) -> bool:
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM daily_tasks
                WHERE user_id = %s AND work_date = %s AND task_id = %s
                """,
                (user_id, work_date, task_id),
            )
            return cursor.rowcount > 0
