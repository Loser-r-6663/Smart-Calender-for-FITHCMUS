from collections.abc import Mapping
from typing import Any

from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection

from Database.task_config import TASK_FIELDS, current_task_timestamp
from Database.task_validation import TaskData, validate_task_data


_TASK_COLUMNS = TASK_FIELDS


class TaskRepository:
    def create(
        self, db_connection: connection, task_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not task_data:
            raise ValueError("task_data cannot be empty")
        self._validate_columns(task_data)
        task_data = validate_task_data(task_data)

        columns = tuple(task_data)
        query = sql.SQL("INSERT INTO tasks ({}) VALUES ({}) RETURNING *").format(
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, tuple(task_data[column] for column in columns))
            return dict(cursor.fetchone())

    def get_by_id(
        self, db_connection: connection, task_id: str
    ) -> dict[str, Any] | None:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def update(
        self,
        db_connection: connection,
        task_id: str,
        updates: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_by_id(db_connection, task_id)
        if "id" in updates:
            raise ValueError("A task id cannot be changed")
        self._validate_columns(updates)

        existing_task = self.get_by_id(db_connection, task_id)
        if existing_task is None:
            return None
        validated_task = TaskData.model_validate({**existing_task, **updates})
        updates = {
            column: getattr(validated_task, column)
            for column in updates
        }
        if updates.get("source_url") is not None:
            updates["source_url"] = str(updates["source_url"])
        if validated_task.drl_category != existing_task["drl_category"]:
            updates["drl_category"] = validated_task.drl_category
        updates["updated_at"] = current_task_timestamp()

        assignments = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder())
            for column in updates
        )
        query = sql.SQL("UPDATE tasks SET {} WHERE id = {} RETURNING *").format(
            assignments, sql.Placeholder()
        )
        values = tuple(updates.values()) + (task_id,)
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, values)
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def delete(self, db_connection: connection, task_id: str) -> bool:
        with db_connection.cursor() as cursor:
            cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _validate_columns(values: Mapping[str, Any]) -> None:
        invalid_columns = set(values) - _TASK_COLUMNS
        if invalid_columns:
            raise ValueError(
                "Unsupported task fields: " + ", ".join(sorted(invalid_columns))
            )
