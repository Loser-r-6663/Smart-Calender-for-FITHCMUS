import hashlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from DataProcessor.Standardization.Task import Task


class LocalTaskRepository:
    """SQLite repository for a single user's Task objects and schedule state."""

    JSON_COLUMNS = ("target_audience", "location", "start_time", "end_time")

    COLUMNS = {
        "id": "TEXT PRIMARY KEY",
        "title": "TEXT NOT NULL",
        "type": "TEXT NOT NULL",
        "course": "TEXT",
        "description": "TEXT",
        "target_audience": "TEXT",
        "location": "TEXT",
        "registration_start": "TEXT",
        "registration_end": "TEXT",
        "start_time": "TEXT",
        "end_time": "TEXT",
        "deadline": "TEXT",
        "training_points": "INTEGER",
        "training_point_category": "TEXT",
        "estimated_hours": "REAL",
        "source_url": "TEXT NOT NULL",
        "source_platform": "TEXT NOT NULL",
        "updated_at": "TEXT NOT NULL",
        "recurrence": "INTEGER NOT NULL",
        "status": "TEXT NOT NULL",
        "compulsory": "INTEGER NOT NULL",
        "flexible": "INTEGER NOT NULL",
        "user_modified": "INTEGER NOT NULL",
    }

    def __init__(self, user_id: str, database_dir: str | Path | None = None):
        if not user_id:
            raise ValueError("user_id is required")

        root = Path(database_dir or os.getenv("LOCAL_TASK_DB_DIR", "Database/data"))
        root.mkdir(parents=True, exist_ok=True)
        safe_user_id = hashlib.sha256(user_id.encode()).hexdigest()
        self.database_path = root / f"{safe_user_id}.sqlite3"
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            + ", ".join(f"{name} {definition}" for name, definition in self.COLUMNS.items())
            + ")"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS deleted_tasks (id TEXT PRIMARY KEY)"
        )
        self._migrate()

    def _migrate(self):
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(tasks)")
        }
        for name, definition in self.COLUMNS.items():
            if name not in existing:
                clean_def = definition.replace(" PRIMARY KEY", "").replace(" NOT NULL", "")
                default_clause = " DEFAULT 0" if name == "user_modified" else ""
                self.connection.execute(
                    f"ALTER TABLE tasks ADD COLUMN {name} {clean_def}{default_clause}"
                )
        # Clean up any legacy split-session copies stored with '#s' suffix
        self.connection.execute("DELETE FROM tasks WHERE id LIKE '%#s%'")
        self.connection.commit()

    @staticmethod
    def compute_task_id(task: Task) -> str:
        if task.id:
            return task.id
        return str(uuid5(NAMESPACE_URL, f"{task.source_url}|{task.title}"))

    @classmethod
    def _ensure_task(cls, task: Task) -> Task:
        if not isinstance(task, Task):
            raise TypeError("LocalTaskRepository only accepts Task instances")
        task = task.model_copy(deep=True)
        if task.id is None:
            task.id = cls.compute_task_id(task)
        return task

    def save_tasks(self, tasks: list[Task]) -> list[Task]:
        if not tasks:
            return []

        prepared_tasks = [
            self._ensure_task(t)
            for t in tasks
            if "#s" not in (t.id or "")
        ]
        if not prepared_tasks:
            return []

        rows: list[dict] = []
        for task in prepared_tasks:
            data = task.model_dump(mode="json")
            values = {"id": task.id}
            for name in self.COLUMNS:
                if name == "id":
                    continue
                value = data.get(name)
                if name in ("recurrence", "compulsory", "flexible", "user_modified"):
                    values[name] = int(bool(value))
                elif name in self.JSON_COLUMNS:
                    values[name] = json.dumps(value, ensure_ascii=False) if value is not None else None
                else:
                    values[name] = value
            rows.append(values)

        names = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in names)
        updates = ", ".join(
            f"{name} = excluded.{name}" for name in names if name != "id"
        )
        self.connection.executemany(
            f"INSERT INTO tasks ({', '.join(names)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            [tuple(row[name] for name in names) for row in rows],
        )
        self.connection.commit()
        return prepared_tasks

    def get_tasks(self, limit: int | None = 1000) -> list[Task]:
        if limit is None:
            rows = self.connection.execute(
                "SELECT * FROM tasks WHERE id NOT LIKE '%#s%' ORDER BY updated_at DESC"
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM tasks WHERE id NOT LIKE '%#s%' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        tasks = []
        for row in rows:
            data = dict(row)
            data.pop("payload", None)
            data["user_modified"] = bool(data.get("user_modified") or 0)
            for field in self.JSON_COLUMNS:
                raw_val = data.get(field)
                if raw_val and isinstance(raw_val, str):
                    try:
                        data[field] = json.loads(raw_val)
                    except (ValueError, TypeError):
                        pass
            tasks.append(Task.model_validate(data))
        return tasks

    def get_task(self, task_id: str) -> Task | None:
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data.pop("payload", None)
        data["user_modified"] = bool(data.get("user_modified") or 0)
        for field in self.JSON_COLUMNS:
            raw_val = data.get(field)
            if raw_val and isinstance(raw_val, str):
                try:
                    data[field] = json.loads(raw_val)
                except (ValueError, TypeError):
                    pass
        return Task.model_validate(data)

    def get_deleted_ids(self) -> set[str]:
        return {
            row["id"]
            for row in self.connection.execute("SELECT id FROM deleted_tasks")
        }

    def mark_deleted(self, task_id: str) -> bool:
        existed = self.get_task(task_id) is not None
        self.connection.execute(
            "INSERT OR IGNORE INTO deleted_tasks (id) VALUES (?)",
            (task_id,),
        )
        self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.connection.commit()
        return existed

    def sync_external_tasks(self, external_tasks: list[Task]) -> list[Task]:
        """Merge cloud/fixture tasks with local user edits, status, and deletions."""
        deleted_ids = self.get_deleted_ids()
        existing_by_id = {task.id: task for task in self.get_tasks(limit=None) if task.id}
        to_save: list[Task] = []

        for incoming in external_tasks:
            prepared = self._ensure_task(incoming)
            if prepared.id in deleted_ids:
                continue
            existing = existing_by_id.get(prepared.id)
            if existing is not None:
                if existing.user_modified:
                    continue
                prepared.status = existing.status
                prepared.compulsory = existing.compulsory
                prepared.flexible = existing.flexible
            to_save.append(prepared)

        if to_save:
            self.save_tasks(to_save)

        return [
            task
            for task in self.get_tasks(limit=None)
            if task.id not in deleted_ids
        ]

    def delete_tasks(self, tasks: list[Task]):
        ids = [task.id for task in tasks if isinstance(task, Task) and task.id]
        self.connection.executemany(
            "DELETE FROM tasks WHERE id = ?", ((task_id,) for task_id in ids)
        )
        self.connection.commit()

    def update_task(self, task_id: str, data: Task | dict) -> Task:
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(f"Task not found: {task_id}")
        if isinstance(data, Task):
            updated = data.model_copy(deep=True)
        elif isinstance(data, dict):
            updated = Task.model_validate(current.model_dump() | data)
        else:
            raise TypeError("update_task needs a Task or a dict")
        updated.id = task_id
        return self.save_tasks([updated])[0]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
