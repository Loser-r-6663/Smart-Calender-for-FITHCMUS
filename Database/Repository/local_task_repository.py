import json
import os
import sqlite3
import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from DataProcessor.Standardization.Task import Task


class LocalTaskRepository:
    """SQLite repository for a single user's Task objects."""

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
    }

    def __init__(self, user_id: str, database_dir: str | None = None):
        if not user_id:
            raise ValueError("user_id is required")

        root = Path(database_dir or os.getenv("LOCAL_TASK_DB_DIR", "Database/data"))
        root.mkdir(parents=True, exist_ok=True)
        safe_user_id = hashlib.sha256(user_id.encode()).hexdigest()
        self.database_path = root / f"{safe_user_id}.sqlite3"
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks (" +
            ", ".join(f"{name} {definition}" for name, definition in self.COLUMNS.items()) +
            ")"
        )
        self._migrate()

    def _migrate(self):
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(tasks)")
        }
        for name, definition in self.COLUMNS.items():
            if name not in existing:
                definition = definition.replace(" PRIMARY KEY", "").replace(" NOT NULL", "")
                self.connection.execute(
                    f"ALTER TABLE tasks ADD COLUMN {name} {definition}"
                )
        self.connection.commit()

    @staticmethod
    def _ensure_task(task: Task) -> Task:
        if not isinstance(task, Task):
            raise TypeError("LocalTaskRepository only accepts Task instances")
        task = task.model_copy(deep=True)
        if task.id is None:
            task.id = str(uuid5(NAMESPACE_URL, f"{task.source_url}|{task.title}"))
        return task

    def save_tasks(self, tasks: list[Task]) -> list[Task]:
        if not tasks:
            return []

        prepared_tasks = [self._ensure_task(t) for t in tasks]
        rows = []
        for task in prepared_tasks:
            data = task.model_dump(mode="json")
            values = {"id": task.id}
            for name in self.COLUMNS:
                if name == "id":
                    continue
                value = data.get(name)
                if name in ("recurrence", "compulsory", "flexible"):
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

    def get_tasks(self, limit: int = 100) -> list[Task]:
        rows = self.connection.execute(
            "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        tasks = []
        for row in rows:
            data = dict(row)
            data.pop("payload", None)  # Bỏ qua trường payload cũ nếu database đã tồn tại cột này
            for field in self.JSON_COLUMNS:
                raw_val = data.get(field)
                if raw_val and isinstance(raw_val, str):
                    try:
                        data[field] = json.loads(raw_val)
                    except (ValueError, TypeError):
                        pass
            tasks.append(Task.model_validate(data))
        return tasks

    def delete_tasks(self, tasks: list[Task]):
        ids = [task.id for task in tasks if isinstance(task, Task) and task.id]
        self.connection.executemany(
            "DELETE FROM tasks WHERE id = ?", ((task_id,) for task_id in ids)
        )
        self.connection.commit()

    def update_task(self, task_id: str, data: Task | dict):
        current = next((task for task in self.get_tasks() if task.id == task_id), None)
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
